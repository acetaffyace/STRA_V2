"""Review classification helpers."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import contextvars
import types
from datetime import datetime, timezone
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from string import Template
import textwrap
from textwrap import dedent
from typing import Any, Callable, Dict, List, Literal, Mapping, Optional, Sequence, Tuple

import pandas as pd
from pydantic import BaseModel, Field

import requests

from . import storage
from . import review_preprocessor
from . import batch_planner
from .providers.errors import ProviderFailure

logger = logging.getLogger(__name__)

# Legacy model IDs kept for cache backward-compatibility (accepting old labels)
GEMINI_MODEL = os.getenv("SENTINEXT_GEMINI_MODEL", "gemini-flash-lite-latest")

# xAI (Grok) configuration for review classification
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_MODEL = os.getenv("SENTINEXT_XAI_MODEL", "grok-4-1-fast-non-reasoning")
XAI_MODEL_REASONING = os.getenv("SENTINEXT_XAI_MODEL_REASONING", "grok-4-1-fast-reasoning")

# Timeout and retry configuration
LLM_TIMEOUT_SECONDS = int(os.getenv("SENTINEXT_LLM_TIMEOUT", "30"))
LLM_MAX_RETRIES = int(os.getenv("SENTINEXT_LLM_MAX_RETRIES", "3"))
LLM_BASE_RETRY_DELAY = float(os.getenv("SENTINEXT_LLM_RETRY_DELAY", "2.0"))

# Context for logging LLM usage (propagated via contextvars)
_LLM_USAGE_CONTEXT: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "llm_usage_context",
    default={},
)


@contextmanager
def llm_usage_context(
    *,
    operation: Optional[str] = None,
    app_id: Optional[int] = None,
    session_id: Optional[str] = None,
    run_id: Optional[str] = None,
    phase: Optional[str] = None,
    prompt_version: Optional[str] = None,
    taxonomy_version: Optional[str] = None,
    workload_type: Optional[str] = None,
    requested_review_count: Optional[int] = None,
    operation_id: Optional[str] = None,
    attempt_number: Optional[int] = None,
    batch_id: Optional[str] = None,
    parent_batch_id: Optional[str] = None,
    review_count: Optional[int] = None,
    is_retry: Optional[bool] = None,
    retry_reason: Optional[str] = None,
    split_depth: Optional[int] = None,
) -> Any:
    """Attach context for LLM usage logging within the current task."""
    current = _LLM_USAGE_CONTEXT.get() or {}
    updates: Dict[str, Any] = {k: v for k, v in {
        "operation": operation,
        "app_id": app_id,
        "session_id": session_id,
        "run_id": run_id,
        "phase": phase,
        "prompt_version": prompt_version,
        "taxonomy_version": taxonomy_version,
        "workload_type": workload_type,
        "requested_review_count": requested_review_count,
        "operation_id": operation_id,
        "attempt_number": attempt_number,
        "batch_id": batch_id,
        "parent_batch_id": parent_batch_id,
        "review_count": review_count,
        "is_retry": is_retry,
        "retry_reason": retry_reason,
        "split_depth": split_depth,
    }.items() if v is not None}
    merged = {**current, **updates}
    token = _LLM_USAGE_CONTEXT.set(types.MappingProxyType(merged))
    try:
        yield
    finally:
        _LLM_USAGE_CONTEXT.reset(token)


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _record_llm_usage(
    response: Any,
    model_name: str,
    *,
    provider: str = "google",
    prompt_tokens: Optional[int] = None,
    response_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> None:
    """Record token usage metadata if available (best-effort)."""
    try:
        usage = getattr(response, "usage_metadata", None)
        if usage is None and prompt_tokens is None and response_tokens is None and total_tokens is None:
            return

        ctx = _LLM_USAGE_CONTEXT.get() or {}

        storage.log_llm_usage(
            operation=str(ctx.get("operation") or "unknown"),
            model=_model_id(provider, model_name),
            prompt_tokens=prompt_tokens if prompt_tokens is not None else _safe_int(getattr(usage, "prompt_token_count", None)),
            response_tokens=response_tokens if response_tokens is not None else _safe_int(getattr(usage, "response_token_count", None)),
            total_tokens=total_tokens if total_tokens is not None else _safe_int(getattr(usage, "total_token_count", None)),
            cached_tokens=_safe_int(getattr(usage, "cached_content_token_count", None)) if usage is not None else None,
            tool_use_prompt_tokens=_safe_int(getattr(usage, "tool_use_prompt_token_count", None)) if usage is not None else None,
            thoughts_tokens=_safe_int(getattr(usage, "thoughts_token_count", None)) if usage is not None else None,
            traffic_type=str(getattr(usage, "traffic_type", None)) if usage is not None and getattr(usage, "traffic_type", None) else None,
            app_id=ctx.get("app_id"),
            session_id=ctx.get("session_id"),
        )
    except Exception as exc:
        logger.debug("Failed to record LLM usage: %s", exc)


class LLMErrorType(Enum):
    """Classification of LLM errors for retry decisions."""
    BAD_REQUEST = "bad_request"  # 400 - don't retry
    RATE_LIMITED = "rate_limited"  # 429 - retry with longer delay
    SERVER_ERROR = "server_error"  # 500-504 - retry with backoff
    TIMEOUT = "timeout"  # Request timeout - retry
    UNKNOWN = "unknown"  # Unknown error - limited retry


class LLMError(Exception):
    """Exception for LLM API errors with classification."""

    def __init__(self, message: str, error_type: LLMErrorType, status_code: Optional[int] = None, retryable: bool = True):
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code
        self.retryable = retryable


def _classify_error(status_code: Optional[int], error_message: str = "") -> Tuple[LLMErrorType, bool]:
    """Classify an error and determine if it's retryable.

    Returns:
        Tuple of (error_type, is_retryable)
    """
    if status_code == 400:
        return LLMErrorType.BAD_REQUEST, False
    elif status_code == 429:
        return LLMErrorType.RATE_LIMITED, True
    elif status_code is not None and 500 <= status_code <= 504:
        return LLMErrorType.SERVER_ERROR, True
    elif "timeout" in error_message.lower() or "timed out" in error_message.lower():
        return LLMErrorType.TIMEOUT, True
    return LLMErrorType.UNKNOWN, True


def _calculate_retry_delay(attempt: int, error_type: LLMErrorType, extracted_delay: Optional[float] = None) -> float:
    """Calculate retry delay with exponential backoff.

    Args:
        attempt: Current attempt number (1-indexed)
        error_type: Type of error encountered
        extracted_delay: Delay extracted from error message (e.g., rate limit retry-after)

    Returns:
        Delay in seconds before next retry
    """
    if extracted_delay is not None:
        return extracted_delay + 1  # Add buffer

    base_delay = LLM_BASE_RETRY_DELAY

    if error_type == LLMErrorType.RATE_LIMITED:
        # Longer base delay for rate limits
        base_delay = 20.0
    elif error_type == LLMErrorType.SERVER_ERROR:
        base_delay = 5.0

    # Exponential backoff with jitter
    delay = base_delay * (2 ** (attempt - 1))
    jitter = random.uniform(0, delay * 0.1)
    return min(delay + jitter, 60.0)  # Cap at 60 seconds
PROMPT_VERSION_V1 = "steam_review_insights_v13_subcategories_primary_json"
PROMPT_VERSION = "steam_review_insights_v16_basic_labels"
PROMPT_VERSION_V3 = "steam_review_classifier_v3_compact"
PROMPT_VERSION_V3_1 = "steam_review_classifier_v3_1_request_strict"
ACTIVE_PROMPT_VERSION = PROMPT_VERSION
ACCEPTED_PROMPT_VERSIONS = {ACTIVE_PROMPT_VERSION, PROMPT_VERSION, PROMPT_VERSION_V1, PROMPT_VERSION_V3, PROMPT_VERSION_V3_1, "steam_review_insights_v15_aspect_sentiment_json"}
TAXONOMY_VERSION = "sentinext-taxonomy-v1"
CLASSIFICATION_SCHEMA_VERSION = "review-classification-schema-v1"

# Batch size configuration (lower = faster individual responses, higher = fewer API calls)
# Gemini works well with 3-5 reviews per batch
BATCH_SIZE = int(os.getenv("SENTINEXT_BATCH_SIZE", "3"))

_WORD_RE = re.compile(r"\w+", flags=re.UNICODE)


_dotenv_loaded = False


def _maybe_load_dotenv() -> None:
    global _dotenv_loaded
    if _dotenv_loaded:
        return
    if os.getenv("DEEPSEEK_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("OPENAI_API_KEY") or os.getenv("XAI_API_KEY"):
        _dotenv_loaded = True
        return

    try:
        cwd = Path.cwd().resolve()
    except Exception:
        return

    for candidate in [cwd, *cwd.parents]:
        env_path = candidate / ".env"
        if not env_path.is_file():
            continue
        try:
            content = env_path.read_text(encoding="utf-8")
        except Exception:
            _dotenv_loaded = True
            return

        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if not key or key in os.environ:
                continue
            value = value.strip()
            if value and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            os.environ[key] = value
        _dotenv_loaded = True
        return

    _dotenv_loaded = True

_PROMPT_TEMPLATE = Template(
    dedent(
        """Extract actionable developer insights from a Steam review by labeling it with the taxonomy below.

        Reply with STRICT JSON only (a single JSON object). No prose, no markdown, no code fences.

        GAME CONTEXT:
        Name: $game_name
        Type: $game_type
        Genres: $game_genres
        Categories: $game_categories
        Description: $game_description

        REVIEWER CONTEXT:
        Review Language: $review_language
        Playtime: $reviewer_playtime hours
        Recommendation: $reviewer_recommendation

        OUTPUT JSON SCHEMA (use these exact keys; no extras):
        {
          "subcategories": ["<main>/<sub>", "..."],
          "issue_subcategories": ["<main>/<sub>", "..."],
          "request_subcategories": ["<main>/<sub>", "..."],
          "evidence": { "<main>/<sub>": ["<verbatim quote>", "..."] },
          "aspects": [
            {"aspect": "<main>/<sub>", "subtopic": "<optional detail>", "sentiment": -2, "evidence_span": "<verbatim quote>", "confidence": 0.0}
          ]
        }

        FIELD CONSTRAINTS:
        - subcategories: 1-6 unique items
        - subcategories[0]: primary label (dominant theme)
        - issue_subcategories: subset of subcategories
        - request_subcategories: subset of subcategories
        - evidence: keys must match subcategories
        - aspects: one entry per mentioned aspect; sentiment is an integer from -2 to +2,
          evidence_span must be a verbatim substring, confidence is between 0 and 1.

        RULES:
        - Choose 1-6 unique subcategories from the taxonomy below, each formatted as "<main>/<sub>".
        - Put the primary label first: subcategories[0] MUST be the dominant theme of the review.
        - issue_subcategories: only problems/complaints (subset of subcategories).
        - request_subcategories: only explicit requests (subset of subcategories; e.g., "please add", "can you", "I wish").
        - evidence: for EVERY tag in subcategories, include 1-3 EXACT COPY-PASTE quotes from the review (<=160 chars each).
          Each quote MUST be a character-for-character substring of the review. Do NOT rephrase, reorder words, or change punctuation.
          If a quote exceeds 160 characters, extract a shorter fragment that is still verbatim.
        - For non-English reviews: quote in the ORIGINAL language exactly as written. Do NOT translate quotes to English.
        - If review is vague/generic: subcategories=["other/general"], issue_subcategories=[], request_subcategories=[],
          evidence={"other/general":["short quote from review"]}.
        - JSON MUST be valid: double quotes only, no trailing commas, no comments, no code fences.
        - Fill with real values only. Do not output placeholders like "<main>/<sub>", "<verbatim quote>", or "...".

        EXAMPLES (for format only; do not copy; do not output examples):
        Example 1 (Issues only):
        {
          "subcategories": ["technical/performance", "technical/bugs"],
          "issue_subcategories": ["technical/performance", "technical/bugs"],
          "request_subcategories": [],
          "evidence": {
            "technical/performance": ["FPS drops"],
            "technical/bugs": ["Quest breaks"]
          }
        }

        Example 2 (Issue + request):
        {
          "subcategories": ["gameplay/difficulty", "ui_ux_accessibility/quality_of_life"],
          "issue_subcategories": ["gameplay/difficulty"],
          "request_subcategories": ["ui_ux_accessibility/quality_of_life"],
          "evidence": {
            "gameplay/difficulty": ["Too hard"],
            "ui_ux_accessibility/quality_of_life": ["Add FOV slider"]
          }
        }

        TAXONOMY (use only these main/subcategory paths):
        gameplay={mechanics,controls,balance,difficulty,progression,ai}; technical={performance,bugs,stability_crashes,compatibility,networking,installation,save_data};
        content_design={amount_variety,level_design,quests_modes,narrative_characters,replayability,pacing,customization}; ui_ux_accessibility={menus_hud,readability,quality_of_life,controller_support,accessibility_options};
        onboarding={tutorial,learning_curve,clarity,tooltips}; presentation={visuals_art_style,animation,audio_music,voice_acting,atmosphere,localization};
        online_community={multiplayer_experience,matchmaking,social_features,toxicity_moderation,mods_ugc,cheating_anti_cheat};
        developer_updates={patch_quality,update_frequency,roadmap_events,communication,customer_support,response_time};
        monetization_value={pricing,regional_pricing,dlc,microtransactions,battle_pass_fomo,pay_to_win_grind,value_for_money};
        other={general,mixed,meta,unclear,off_topic,meme}.
        Map DLC pricing→monetization_value/dlc, patch quality→developer_updates/patch_quality, saves→technical/save_data, multiplayer→online_community/multiplayer_experience, localization→presentation/localization.

        REVIEW TEXT (verbatim):
        <<<BEGIN REVIEW>>>
        $review_text
        <<<END REVIEW>>>
        """
    )
)

_BATCH_PROMPT_TEMPLATE_LEGACY = Template(
    dedent(
        """Extract actionable developer insights from Steam reviews by labeling each review with the taxonomy below.

        Reply with STRICT JSON only (a single JSON object). No prose, no markdown, no code fences.

        GAME CONTEXT:
        Name: $game_name
        Type: $game_type
        Genres: $game_genres
        Categories: $game_categories
        Description: $game_description

        OUTPUT JSON SCHEMA (first-pass labels only):
        - The top-level JSON MUST be an object.
        - Each key MUST be a review_id from the input (as a string).
        - Each value MUST be an object with these exact keys (no extras):
        {
          "<review_id>": {
            "subcategories": ["<main>/<sub>", "..."],
            "issue_subcategories": ["<main>/<sub>", "..."],
            "request_subcategories": ["<main>/<sub>", "..."]
          }
        }

        FIELD CONSTRAINTS (apply per review):
        - subcategories: 1-6 unique items
        - subcategories[0]: primary label (dominant theme)
        - issue_subcategories: subset of subcategories
        - request_subcategories: subset of subcategories

        RULES:
        - For EVERY review_id provided, include EXACTLY one output entry.
        - Do not add any top-level keys besides the review_id keys.
        - Choose 1-6 unique subcategories from the taxonomy below, each formatted as "<main>/<sub>".
        - Put the primary label first: subcategories[0] MUST be the dominant theme of the review.
        - issue_subcategories: only problems/complaints (subset of subcategories).
        - request_subcategories: only explicit requests (subset of subcategories; e.g., "please add", "can you", "I wish").
        - Do not output evidence, aspects, sentiment scores, confidence, or explanations in this first pass.
        - If review is vague/generic: subcategories=["other/general"], issue_subcategories=[], request_subcategories=[].
        - JSON MUST be valid: double quotes only, no trailing commas, no comments, no code fences.
        - Fill with real values only. Do not output placeholders like "<main>/<sub>", "<verbatim quote>", or "...".

        TAXONOMY (use only these main/subcategory paths):
        gameplay={mechanics,controls,balance,difficulty,progression,ai}; technical={performance,bugs,stability_crashes,compatibility,networking,installation,save_data};
        content_design={amount_variety,level_design,quests_modes,narrative_characters,replayability,pacing,customization}; ui_ux_accessibility={menus_hud,readability,quality_of_life,controller_support,accessibility_options};
        onboarding={tutorial,learning_curve,clarity,tooltips}; presentation={visuals_art_style,animation,audio_music,voice_acting,atmosphere,localization};
        online_community={multiplayer_experience,matchmaking,social_features,toxicity_moderation,mods_ugc,cheating_anti_cheat};
        developer_updates={patch_quality,update_frequency,roadmap_events,communication,customer_support,response_time};
        monetization_value={pricing,regional_pricing,dlc,microtransactions,battle_pass_fomo,pay_to_win_grind,value_for_money};
        other={general,mixed,meta,unclear,off_topic,meme}.
        Map DLC pricing→monetization_value/dlc, patch quality→developer_updates/patch_quality, saves→technical/save_data, multiplayer→online_community/multiplayer_experience, localization→presentation/localization.

        REVIEWS (each block is independent; do not mix evidence across blocks):
        <<<BEGIN REVIEWS>>>
        $reviews_text
        <<<END REVIEWS>>>
        """
    )
)

_BATCH_PROMPT_TEMPLATE_V3 = Template(
    dedent(
        """Classify each Steam review using the taxonomy below.

        Return one JSON object keyed by review_id.

        OUTPUT PER REVIEW: {"subcategories":["<main>/<sub>"],"issue_subcategories":[],"request_subcategories":[]}

        RULES:
        - One entry per review_id; use only the taxonomy labels below.
        - Choose 1-6 unique labels; subcategories[0] is the dominant / primary topic.
        - Prefer a few labels; add one only for a distinct meaningful topic explicitly discussed.
        - issue_subcategories must be a subset of subcategories: current problem, defect, failure, limitation, or explicit dissatisfaction; negative sentiment alone is not an issue.
        - request_subcategories must be a subset of subcategories: explicit ask, proposal, wish, or clear desire for change, fix, addition, removal, support, investigation, or improvement. Detect this semantically across languages.
        - Generic opinions without a specific topic use other/general.

        BOUNDARIES:
        - crash/startup crash/freeze/hard lock → technical/stability_crashes
        - FPS/stutter/frame pacing/frame-time → technical/performance
        - general broken behavior/malfunction → technical/bugs
        - disconnect/latency/NAT/P2P/netcode → technical/networking
        - Steam Deck/Linux/Proton/HDR/ultrawide/platform support → technical/compatibility
        - save loss/corruption/cloud-sync save problems → technical/save_data
        - install/launcher/patch installation failure → technical/installation
        - gameplay input/control feel → gameplay/controls
        - controller/device support → ui_ux_accessibility/controller_support
        - multiplayer experience → online_community/multiplayer_experience
        - queues/finding players/matching → online_community/matchmaking
        - patch quality/regressions/fixes → developer_updates/patch_quality
        - update cadence → developer_updates/update_frequency
        - price → monetization_value/pricing
        - paid DLC/expansion → monetization_value/dlc
        - overall worth for price/content → monetization_value/value_for_money

        MEME: If a meme/joke/copypasta contains a real product topic, assign that topic and optionally other/meme; use other/meme alone only without a useful game-specific topic.

        TAXONOMY (use only these exact main/subcategory paths):
        gameplay={mechanics,controls,balance,difficulty,progression,ai}; technical={performance,bugs,stability_crashes,compatibility,networking,installation,save_data};
        content_design={amount_variety,level_design,quests_modes,narrative_characters,replayability,pacing,customization}; ui_ux_accessibility={menus_hud,readability,quality_of_life,controller_support,accessibility_options};
        onboarding={tutorial,learning_curve,clarity,tooltips}; presentation={visuals_art_style,animation,audio_music,voice_acting,atmosphere,localization};
        online_community={multiplayer_experience,matchmaking,social_features,toxicity_moderation,mods_ugc,cheating_anti_cheat};
        developer_updates={patch_quality,update_frequency,roadmap_events,communication,customer_support,response_time};
        monetization_value={pricing,regional_pricing,dlc,microtransactions,battle_pass_fomo,pay_to_win_grind,value_for_money};
        other={general,mixed,meta,unclear,off_topic,meme}.

        REVIEWS:
        <<<BEGIN REVIEWS>>>
        $reviews_text
        <<<END REVIEWS>>>
        """
    )
)

# V3.1 keeps the compact V3 prompt unchanged except for the request boundary:
# dissatisfaction, criticism, bug reports, and statements that something is
# bad/broken are not requests unless the review explicitly asks for a change.
_BATCH_PROMPT_TEMPLATE_V3_1 = Template(
    _BATCH_PROMPT_TEMPLATE_V3.template.replace(
        "request_subcategories must be a subset of subcategories: explicit ask, proposal, wish, or clear desire for change, fix, addition, removal, support, investigation, or improvement. Detect this semantically across languages.",
        "request_subcategories must be a subset of subcategories: labels where the player explicitly asks for, proposes, wishes for, recommends, or directly expresses a desired change, fix, addition, removal, support, investigation, or improvement. Do not infer a request from dissatisfaction, criticism, a bug report, or a statement that something is bad or broken. A complaint alone is not a request. Detect explicit requests semantically across languages.",
    )
)

_DEFAULT_LABEL = {
    "main_category": "other",
    "subcategory": "general",
    "subcategories": ["other/general"],
    "issue_subcategories": [],
    "request_subcategories": [],
    "evidence": {},
    "aspects": [],
}


_ALLOWED_MAIN_CATEGORIES = {
    "gameplay",
    "technical",
    "content_design",
    "ui_ux_accessibility",
    "onboarding",
    "presentation",
    "online_community",
    "developer_updates",
    "monetization_value",
    "other",
}
_ALLOWED_SUBCATEGORIES = {
    "gameplay": {"mechanics", "controls", "balance", "difficulty", "progression", "ai"},
    "technical": {"performance", "bugs", "stability_crashes", "compatibility", "networking", "installation", "save_data"},
    "content_design": {
        "amount_variety",
        "level_design",
        "quests_modes",
        "narrative_characters",
        "replayability",
        "pacing",
        "customization",
    },
    "ui_ux_accessibility": {"menus_hud", "readability", "quality_of_life", "controller_support", "accessibility_options"},
    "onboarding": {"tutorial", "learning_curve", "clarity", "tooltips"},
    "presentation": {"visuals_art_style", "animation", "audio_music", "voice_acting", "atmosphere", "localization"},
    "online_community": {
        "multiplayer_experience",
        "matchmaking",
        "social_features",
        "toxicity_moderation",
        "mods_ugc",
        "cheating_anti_cheat",
    },
    "developer_updates": {
        "patch_quality",
        "update_frequency",
        "roadmap_events",
        "communication",
        "customer_support",
        "response_time",
    },
    "monetization_value": {
        "pricing",
        "regional_pricing",
        "dlc",
        "microtransactions",
        "battle_pass_fomo",
        "pay_to_win_grind",
        "value_for_money",
    },
    "other": {"general", "mixed", "meta", "unclear", "off_topic", "meme"},
}
_ALLOWED_SUBCATEGORY_KEYS = {
    f"{main}/{sub}" for main, subs in _ALLOWED_SUBCATEGORIES.items() for sub in subs
}
_SUBCATEGORY_ENUM = sorted(_ALLOWED_SUBCATEGORY_KEYS)

# Literal type for Pydantic models — enables xAI chat.parse() to enforce valid subcategories.
_SubcategoryLiteral = Literal[tuple(_SUBCATEGORY_ENUM)]


class ReviewClassification(BaseModel):
    """Pydantic model for xAI structured output (chat.parse)."""
    subcategories: list[_SubcategoryLiteral] = Field(description="1-6 unique subcategory labels in 'main/sub' format")
    issue_subcategories: list[_SubcategoryLiteral] = Field(default_factory=list, description="Subset of subcategories that are issues/complaints")
    request_subcategories: list[_SubcategoryLiteral] = Field(default_factory=list, description="Subset of subcategories that are explicit requests")
    evidence: dict[str, list[str]] = Field(default_factory=dict, description="Verbatim quotes keyed by subcategory")
    aspects: list[dict[str, Any]] = Field(default_factory=list, description="Aspect sentiment entries with sentiment -2..2, evidence_span, and confidence")


class ReportSummary(BaseModel):
    """Structured output for monthly report and widget summaries."""
    summary: str = Field(description="Executive summary paragraph")
    key_points: list[str] = Field(default_factory=list, description="Top key points")
    actions: list[str] = Field(default_factory=list, description="Suggested actions")
    output_language: Optional[str] = Field(default=None, description="Requested analytical output language")


def _summary_language_name(output_language: str) -> str:
    return {"zh": "Simplified Chinese", "en": "English", "ja": "Japanese"}.get(
        (output_language or "zh").lower(), "Simplified Chinese"
    )


def _looks_like_requested_language(values: Sequence[str], output_language: str) -> bool:
    text = " ".join(str(value or "") for value in values)
    if not text.strip():
        return True
    if (output_language or "zh").lower() == "zh":
        return any("\u4e00" <= char <= "\u9fff" for char in text)
    if (output_language or "en").lower() == "en":
        return any("a" <= char.lower() <= "z" for char in text)
    return any("\u3040" <= char <= "\u30ff" for char in text)


class HealthOverview(BaseModel):
    """Structured output for persistent health overview card."""
    summary: str = Field(description="2-4 sentence executive recap")
    key_points: list[str] = Field(default_factory=list, description="Key facts or observations")
    actions: list[str] = Field(default_factory=list, description="Top 3 prioritized actions")
    health_score: int = Field(description="Overall health score from 1-10")
    sentiment_trend: str = Field(description="One of: improving, stable, declining")
    top_strengths: list[str] = Field(default_factory=list, description="Top 3 strengths")


class SubcategorySummary(BaseModel):
    """Structured output for subcategory review summaries."""
    summary: str = Field(description="Summary paragraph of reviews in this subcategory")
    pros: list[str] = Field(default_factory=list, description="Positive aspects mentioned")
    cons: list[str] = Field(default_factory=list, description="Negative aspects mentioned")


class GameComparison(BaseModel):
    """Structured output for game comparison."""
    summary: str = Field(description="Overview highlighting what makes each game unique")
    winners: dict[str, list[int]] = Field(default_factory=dict, description="Aspect to winning app_ids mapping")
    key_differences: list[str] = Field(default_factory=list, description="Specific comparison points with percentages")
    strengths_per_game: dict[str, list[str]] = Field(default_factory=dict, description="Per app_id strengths")
    weaknesses_per_game: dict[str, list[str]] = Field(default_factory=dict, description="Per app_id weaknesses")
    recommendations: dict[str, str] = Field(default_factory=dict, description="Per app_id target audience")


class NewsUpdateSummary(BaseModel):
    """Structured output for news/patch summary."""
    summary: str = Field(description="Brief 2-3 sentence overview of recent update activity")
    key_updates: list[str] = Field(default_factory=list, description="3-5 most important updates/changes")
    potential_impacts: list[str] = Field(default_factory=list, description="2-4 areas that might affect player experience")
    correlation_insights: Optional[str] = Field(default=None, description="Correlation between updates and sentiment, or null")

# JSON schema for a single review classification entry with enum-constrained subcategories.
_REVIEW_CLASSIFICATION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "subcategories": {"type": "array", "items": {"type": "string", "enum": _SUBCATEGORY_ENUM}},
        "issue_subcategories": {"type": "array", "items": {"type": "string", "enum": _SUBCATEGORY_ENUM}},
        "request_subcategories": {"type": "array", "items": {"type": "string", "enum": _SUBCATEGORY_ENUM}},
        "evidence": {
            "type": "object",
            "additionalProperties": {"type": "array", "items": {"type": "string"}},
        },
        "aspects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "aspect": {"type": "string", "enum": _SUBCATEGORY_ENUM},
                    "subtopic": {"type": "string"},
                    "sentiment": {"type": "integer", "minimum": -2, "maximum": 2},
                    "evidence_span": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["aspect", "sentiment", "evidence_span", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["subcategories", "issue_subcategories", "request_subcategories", "evidence"],
}


def _build_batch_json_schema(review_ids: list[str]) -> dict:
    """Build a JSON schema for batch classification with review IDs as fixed properties.

    Uses enum constraints on subcategory fields to prevent models from
    inventing invalid subcategory names.
    """
    return {
        "type": "object",
        "properties": {rid: _REVIEW_CLASSIFICATION_SCHEMA for rid in review_ids},
        "required": review_ids,
    }

_SUBCATEGORY_SEPARATORS = ("/", ":", ".")

_MAIN_CATEGORY_ALIASES: dict[str, str] = {
    "content_and_design": "content_design",
    "contentdesign": "content_design",
    "developer_and_updates": "developer_updates",
    "developerupdates": "developer_updates",
    "monetization_and_value": "monetization_value",
    "monetizationvalue": "monetization_value",
    "online_and_community": "online_community",
    "onlinecommunity": "online_community",
    "uiux_accessibility": "ui_ux_accessibility",
    "uiuxaccessibility": "ui_ux_accessibility",
    "ui_ux": "ui_ux_accessibility",
}

_SUBCATEGORY_ALIASES: dict[str, dict[str, str]] = {
    "technical": {
        "bug": "bugs",
        "crash": "stability_crashes",
        "crashes": "stability_crashes",
        "stability": "stability_crashes",
    },
    "gameplay": {
        "mechanic": "mechanics",
        "control": "controls",
    },
    "content_design": {
        "quest_mode": "quests_modes",
        "quest_modes": "quests_modes",
    },
    "ui_ux_accessibility": {
        "menu_hud": "menus_hud",
        "qol": "quality_of_life",
    },
    "developer_updates": {
        "support": "customer_support",
    },
    "monetization_value": {
        "microtransaction": "microtransactions",
        "dlcs": "dlc",
        "price": "pricing",
    },
    "presentation": {
        "audio_music_voice": "audio_music",
    },
}
MAX_EVIDENCE_SNIPPET_CHARS = 160
MAX_REVIEW_CHARS = 8000
REVIEW_HEAD_CHARS = 6000
REVIEW_TAIL_CHARS = 2000
BATCH_OUTPUT_BASE_TOKENS = 1024
BATCH_OUTPUT_TOKENS_PER_REVIEW = 128
BATCH_OUTPUT_SOFT_CAP = 32768
HYBRID_RULES_VERSION = "v2"


def _hybrid_rules_model_id() -> str:
    """Return a stable identifier for hybrid-rules labeling."""
    return f"rules:{HYBRID_RULES_VERSION}"


_DANGEROUS_PATTERNS = [
    re.compile(r"<<<\s*END\s*REVIEW", re.IGNORECASE),
    re.compile(r"<<<\s*BEGIN\s*REVIEW", re.IGNORECASE),
    re.compile(r"<<<\s*END\s*REVIEWS", re.IGNORECASE),
    re.compile(r"<<<\s*BEGIN\s*REVIEWS", re.IGNORECASE),
    re.compile(r"IGNORE\s+(?:PREVIOUS|ABOVE|ALL)\s+INSTRUCTIONS", re.IGNORECASE),
    re.compile(r"DISREGARD\s+(?:PREVIOUS|ABOVE|ALL)", re.IGNORECASE),
    re.compile(r"^SYSTEM\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^ASSISTANT\s*:", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^USER\s*:", re.IGNORECASE | re.MULTILINE),
]


def _sanitize_review_text(text: str) -> str:
    """Sanitize review text to prevent prompt injection attacks."""
    if not text:
        return ""
    sanitized = text
    for pattern in _DANGEROUS_PATTERNS:
        sanitized = pattern.sub("[FILTERED]", sanitized)
    # Remove excessive newlines that could break formatting
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    if len(sanitized) <= MAX_REVIEW_CHARS:
        return sanitized
    return (
        sanitized[:REVIEW_HEAD_CHARS]
        + "\n[... REVIEW TRUNCATED: middle omitted ...]\n"
        + sanitized[-REVIEW_TAIL_CHARS:]
    )


def estimate_batch_output_tokens(review_count: int) -> int:
    """Return a size-aware completion budget for one batch response."""
    count = max(1, int(review_count))
    return min(
        BATCH_OUTPUT_SOFT_CAP,
        BATCH_OUTPUT_BASE_TOKENS + count * BATCH_OUTPUT_TOKENS_PER_REVIEW,
    )


def _clean_snippet(value: Any, max_len: Optional[int] = None) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if not text:
        return ""
    width = max_len if isinstance(max_len, int) and max_len > 0 else MAX_EVIDENCE_SNIPPET_CHARS
    width = max(width, 4)
    return textwrap.shorten(text, width=width, placeholder="...")


def _review_word_count(text: str) -> int:
    if not text:
        return 0
    return len(_WORD_RE.findall(text))


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+", flags=re.UNICODE)




def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part and part.strip()]


_REQUEST_SIGNAL_PATTERNS = [
    re.compile(r"\b(please|pls)\s+(add|include|implement|support|allow|give)\b", flags=re.IGNORECASE),
    re.compile(r"\b(please|pls)\s+fix\b", flags=re.IGNORECASE),
    re.compile(r"\b(can|could)\s+you\b", flags=re.IGNORECASE),
    re.compile(r"\b(i\s+wish|i['’]?d\s+like|would\s+love|would\s+like)\b", flags=re.IGNORECASE),
    re.compile(r"\b(should|needs?|need)\s+(an?\s+)?(option|mode|feature)\b", flags=re.IGNORECASE),
    re.compile(r"\b(need|needs|should)\s+fix\b", flags=re.IGNORECASE),
]


def _has_request_signal(text: str) -> bool:
    if not text:
        return False
    for pattern in _REQUEST_SIGNAL_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _is_negated(sentence: str, match_start: int, match_text: str = "") -> bool:
    window = sentence[max(0, match_start - 32) : match_start].lower()
    if re.search(r"\b(no|without|never)\b", window):
        return True
    # e.g. "bug-free", "crash-free" (only relevant to bug/crash matches)
    if match_text:
        lowered = match_text.lower()
        if lowered.startswith(("bug", "crash")) and re.search(r"\b(bug|crash)[- ]?free\b", sentence.lower()):
            return True
    return False


def _compile_patterns(patterns: Sequence[str]) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns)


_HYBRID_RULES: list[dict[str, Any]] = [
    {
        "key": "technical/stability_crashes",
        "weight": 12,
        "patterns": _compile_patterns(
            [
                r"\bctd\b",
                r"\bcrash(?:es|ed|ing)?\b",
                r"\bcrash[- ]?to[- ]?desktop\b",
                r"\bcrash\s+on\s+launch\b",
                r"\bfreez(?:e|es|ing|en)\b",
                r"\bhang(?:s|ing)?\b",
                r"\bsoft[- ]?lock(?:ed|s)?\b",
            ]
        ),
    },
    {
        "key": "technical/save_data",
        "weight": 10,
        "patterns": _compile_patterns(
            [
                r"\bsteam\s+cloud\b",
                r"\bcloud\s+sync\b",
                r"\bcloud\s+saves?\b",
                r"\bsync\s+(?:conflict|issue|issues|problem|problems|fail|fails|failed)\b",
                r"\bcan['’]?t\s+save\b",
                r"\bcannot\s+save\b",
                r"\bwon['’]?t\s+save\b",
                r"\bsave\s+corrupt(?:ion|ed)?\b",
                r"\bcorrupt(?:ed)?\s+save\b",
                r"\bprogress\s+los(?:s|t)\b",
                r"\blost\s+(?:my\s+)?save\b",
                r"\bmissing\s+save\b",
                r"\bsave\s+file\b",
                r"\bsave\s*game\b",
                r"\bautosave\b.*\b(?:broken|not\s+work(?:ing)?|fail(?:s|ed)?)\b",
            ]
        ),
    },
    {
        "key": "technical/performance",
        "weight": 9,
        "patterns": _compile_patterns(
            [
                r"\bfps\b",
                r"\bframe\s*(?:rate|rates|time|times|pacing)\b",
                r"\bframe\s*drops?\b",
                r"\bfps\s*drops?\b",
                r"\bstutter(?:ing|s)?\b",
                r"\bmicro[- ]?stutter(?:ing|s)?\b",
                r"\binput\s+lag\b",
            ]
        ),
    },
    {
        "key": "technical/bugs",
        "weight": 9,
        "patterns": _compile_patterns(
            [
                r"\bbug(?:s|gy)?\b",
                r"\bglitch(?:es|y)?\b",
                r"\bbroken\b",
                r"\bdoesn['’]?t\s+work\b",
                r"\bnot\s+working\b",
                r"\bclipping\b",
            ]
        ),
    },
    {
        "key": "technical/networking",
        "weight": 8,
        "patterns": _compile_patterns(
            [
                r"\bdisconnect(?:s|ed|ing)?\b",
                r"\blatency\b",
                r"\bnetcode\b",
                r"\brubber[- ]?band(?:ing)?\b",
                r"\bserver\s+(?:issue|issues|problem|problems|down)\b",
            ]
        ),
    },
    {
        "key": "technical/compatibility",
        "weight": 8,
        "patterns": _compile_patterns(
            [
                r"\bsteam\s*deck\b",
                r"\bultra[- ]?wide\b",
                r"\bhdr\b",
                r"\bvr\b",
                r"\bproton\b",
                r"\blinux\b",
            ]
        ),
    },
    {
        "key": "technical/installation",
        "weight": 8,
        "patterns": _compile_patterns(
            [
                r"\blauncher\b",
                r"\binstall(?:ation)?\b.*\b(?:fail|fails|failed|stuck|issue|issues|problem|problems|error)\b",
                r"\bupdate\b.*\b(?:fail|fails|failed|stuck|loop|issue|issues|problem|problems|error)\b",
                r"\bpatch\b.*\b(?:fail|fails|failed|stuck|break|breaks|broke)\b",
                r"\baccount\s+link(?:ing|ed)?\b",
            ]
        ),
    },
    {
        "key": "ui_ux_accessibility/readability",
        "weight": 7,
        "patterns": _compile_patterns(
            [
                r"\btext\b.*\b(?:too\s+small|tiny|unreadable)\b",
                r"\bfont\b.*\b(?:too\s+small|tiny|unreadable)\b",
                r"\b(?:motion|sea)\s*sickness\b",
            ]
        ),
    },
    {
        "key": "ui_ux_accessibility/controller_support",
        "weight": 7,
        "patterns": _compile_patterns(
            [
                r"\b(no|missing)\s+controller\s+support\b",
                r"\bcontroller\b.*\b(?:not\s+work(?:ing)?|broken|unresponsive|doesn['’]?t\s+work)\b",
                r"\bgamepad\b.*\b(?:not\s+work(?:ing)?|broken|unresponsive|doesn['’]?t\s+work)\b",
                r"\b(keybind|rebind|remap)\w*\b.*\b(missing|can['’]?t|cannot|doesn['’]?t|won['’]?t)\b",
            ]
        ),
    },
]


def _rules_score(text: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}

    sentences = _split_sentences(text)
    if not sentences:
        sentences = [text.strip()]

    for rule in _HYBRID_RULES:
        key = str(rule.get("key") or "").strip().lower()
        patterns = rule.get("patterns") or ()
        try:
            weight = int(rule.get("weight") or 0)
        except Exception:
            weight = 0
        if not key or key not in _ALLOWED_SUBCATEGORY_KEYS or not weight:
            continue

        matched_sentence = ""
        matched_start = -1
        for sentence in sentences:
            for pattern in patterns:
                match = pattern.search(sentence)
                if not match:
                    continue
                if _is_negated(sentence, match.start(), match.group(0)):
                    continue
                matched_sentence = sentence
                matched_start = match.start()
                break
            if matched_sentence:
                break

        if not matched_sentence or matched_start < 0:
            continue

        scores[key] = scores.get(key, 0) + weight
        if key not in evidence:
            evidence[key] = [_clean_snippet(matched_sentence)]

    return scores, evidence


def _classify_review_rules(
    review_text: str,
    reviewer_voted_up: bool = True,
) -> Optional[Dict[str, Any]]:
    text = (review_text or "").strip()
    if not text:
        return None

    truncated = _sanitize_review_text(text)
    scores, evidence = _rules_score(truncated)
    if not scores:
        return None

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_key, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    # Conservative thresholds: accept only when a single topic clearly dominates.
    threshold = 9
    margin = 4
    if _review_word_count(truncated) <= 12:
        threshold = 7
        margin = 3

    if best_score < threshold or (best_score - second_score) < margin:
        return None

    best_main, best_sub = best_key.split("/", 1)

    # If another main category is also strongly indicated, fall back to the LLM.
    for key, score in ranked[1:]:
        main = key.split("/", 1)[0]
        if main != best_main and score >= threshold - 1:
            return None

    candidate_keys = [key for key, score in ranked if score >= max(3, best_score - 2)]
    candidate_keys = candidate_keys[:6] or [best_key]

    request_signal = _has_request_signal(truncated)
    issue_signal = True

    issue_subcategories = candidate_keys if issue_signal else []
    request_subcategories = candidate_keys if request_signal else []

    payload: Dict[str, Any] = {
        "main_category": best_main,
        "subcategory": best_sub,
        "subcategories": candidate_keys,
        "issue_subcategories": issue_subcategories,
        "request_subcategories": request_subcategories,
        "evidence": evidence,
        "_label_source": "rules",
        "_label_model": _hybrid_rules_model_id(),
    }
    return payload


def _normalize_subcategory_value(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        main = value.get("main_category") or value.get("main")
        sub = value.get("subcategory") or value.get("sub")
        if main and sub:
            value = f"{main}/{sub}"
        else:
            return None
    if not isinstance(value, str):
        return None
    raw = value.strip().lower()
    if not raw:
        return None

    def _sanitize_token(token: str) -> str:
        token = (token or "").strip().lower()
        if not token:
            return ""
        token = re.sub(r"[\s\-]+", "_", token)
        token = token.replace("&", "_")
        token = token.replace("+", "_")
        token = re.sub(r"[^a-z0-9_]", "", token)
        token = re.sub(r"_+", "_", token)
        return token.strip("_")

    for sep in _SUBCATEGORY_SEPARATORS:
        if sep not in raw:
            continue
        parts = [part.strip() for part in raw.split(sep) if part.strip()]
        if len(parts) < 2:
            continue

        for split_index in range(1, len(parts)):
            main_candidate = "_".join(filter(None, (_sanitize_token(part) for part in parts[:split_index])))
            sub_candidate = "_".join(filter(None, (_sanitize_token(part) for part in parts[split_index:])))
            if not main_candidate or not sub_candidate:
                continue

            main_candidate = _MAIN_CATEGORY_ALIASES.get(main_candidate, main_candidate)
            if main_candidate not in _ALLOWED_SUBCATEGORIES:
                continue

            sub_aliases = _SUBCATEGORY_ALIASES.get(main_candidate, {})
            sub_candidate = sub_aliases.get(sub_candidate, sub_candidate)
            if sub_candidate not in _ALLOWED_SUBCATEGORIES[main_candidate]:
                if sub_candidate.endswith("s"):
                    singular = sub_candidate[:-1]
                    singular = sub_aliases.get(singular, singular)
                    if singular in _ALLOWED_SUBCATEGORIES[main_candidate]:
                        sub_candidate = singular
                    else:
                        continue
                else:
                    plural = f"{sub_candidate}s"
                    plural = sub_aliases.get(plural, plural)
                    if plural in _ALLOWED_SUBCATEGORIES[main_candidate]:
                        sub_candidate = plural
                    else:
                        continue

            return f"{main_candidate}/{sub_candidate}"

    return None


def _parse_subcategory_list(value: Any) -> list[str]:
    results: list[str] = []
    if isinstance(value, dict):
        for main_key, subs in value.items():
            if not isinstance(subs, list):
                continue
            for sub in subs:
                normalized = _normalize_subcategory_value(f"{main_key}/{sub}")
                if normalized and normalized not in results:
                    results.append(normalized)
        return results
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = [value]
    else:
        return results
    for item in items:
        normalized = _normalize_subcategory_value(item)
        if normalized and normalized not in results:
            results.append(normalized)
    return results


def _parse_evidence(value: Any, allowed_subcategories: list[str]) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    allowed = set(allowed_subcategories)
    evidence: dict[str, list[str]] = {}
    for raw_key, raw_snippets in value.items():
        normalized_key = _normalize_subcategory_value(raw_key)
        if not normalized_key or (allowed and normalized_key not in allowed):
            continue
        if isinstance(raw_snippets, list):
            snippets = raw_snippets
        else:
            snippets = [raw_snippets]
        cleaned = []
        for snippet in snippets:
            text = _clean_snippet(snippet)
            if text and text not in cleaned:
                cleaned.append(text)
        if not cleaned:
            continue
        existing = evidence.get(normalized_key, [])
        for item in cleaned:
            if item in existing:
                continue
            if len(existing) >= 4:
                break
            existing.append(item)
        if existing:
            evidence[normalized_key] = existing
    return evidence


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", flags=re.IGNORECASE | re.DOTALL)


def _strip_code_fences(raw: str) -> str:
    if not raw:
        return ""
    match = _CODE_FENCE_RE.search(raw)
    if match:
        return match.group(1).strip()
    return raw.strip()


def _load_json_mapping(raw: str) -> Dict[str, Any]:
    cleaned = _strip_code_fences(raw)
    if not cleaned:
        raise ValueError("Empty response from LLM")

    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(cleaned)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict):
        return obj

    start = cleaned.find("{")
    if start >= 0:
        try:
            obj, _ = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from LLM: {exc}") from exc
        if isinstance(obj, dict):
            return obj

    raise ValueError(f"No JSON object found in LLM response: {raw!r}")


def _build_prompt(
    review_text: str,
    game_context: Optional[Dict[str, Any]] = None,
    reviewer_playtime: float = 0,
    reviewer_voted_up: bool = True,
    review_language: Optional[str] = None,
) -> str:
    truncated = _sanitize_review_text(review_text or "")

    # Build game context strings
    if game_context:
        game_name = game_context.get("name", "Unknown")
        game_type = game_context.get("type", "game")
        genres = game_context.get("genres", [])
        categories = game_context.get("categories", [])
        description = game_context.get("short_description", "")[:200]  # Limit description length

        game_genres = ", ".join(genres) if genres else "Unknown"
        game_categories = ", ".join(categories[:5]) if categories else "Unknown"  # Limit to 5
        game_description = description if description else "Not available"
    else:
        game_name = "Unknown"
        game_type = "game"
        game_genres = "Unknown"
        game_categories = "Unknown"
        game_description = "Not available"

    # Format playtime
    playtime_hours = round(reviewer_playtime / 60, 1) if reviewer_playtime else 0
    recommendation = "Positive" if reviewer_voted_up else "Negative"

    return _PROMPT_TEMPLATE.substitute(
        review_text=truncated,
        game_name=game_name,
        game_type=game_type,
        game_genres=game_genres,
        game_categories=game_categories,
        game_description=game_description,
        review_language=review_language or "english",
        reviewer_playtime=playtime_hours,
        reviewer_recommendation=recommendation,
    )





def _strip_schema_enums(schema: dict) -> dict:
    """Deep-copy a JSON schema and remove all 'enum' keys from string items.

    Gemini's constrained decoding can reject schemas with large enums
    (e.g. 60-value enum repeated across batch properties exceeds state limits).
    """
    import copy

    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "string" and "enum" in node:
            del node["enum"]
        for v in node.values():
            if isinstance(v, dict):
                _walk(v)
            elif isinstance(v, list):
                for item in v:
                    _walk(item)

    result = copy.deepcopy(schema)
    _walk(result)
    return result


def _parse_aspects(value: Any, allowed_subcategories: list[str]) -> list[dict[str, Any]]:
    """Normalize aspect sentiment without allowing untrusted taxonomy keys through."""
    if not isinstance(value, list):
        return []
    allowed = set(allowed_subcategories)
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        aspect = _normalize_subcategory_value(item.get("aspect") or item.get("subcategory"))
        if aspect not in allowed:
            continue
        try:
            sentiment = int(item.get("sentiment"))
        except (TypeError, ValueError):
            continue
        if sentiment < -2 or sentiment > 2:
            continue
        evidence_span = str(item.get("evidence_span") or "").strip()
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        key = (aspect, sentiment, evidence_span)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "aspect": aspect,
            "subtopic": str(item.get("subtopic") or "").strip(),
            "sentiment": sentiment,
            "evidence_span": evidence_span[:160],
            "confidence": round(confidence, 6),
        })
    return result[:12]


def _model_id(provider: str, model: str) -> str:
    return f"{provider}:{model}"


@dataclass
class LLMResponse:
    """Response from an LLM call, potentially with tool calls."""

    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    model: str = ""


async def call_llm_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> LLMResponse:
    """Call an LLM with function calling enabled, routing through providers.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.
        tools: List of tool definitions.
        model: Optional model override.
        timeout: Optional timeout in seconds.

    Returns:
        LLMResponse with either content or tool_calls populated.
    """
    _maybe_load_dotenv()

    try:
        from .providers import get_provider
        provider = get_provider()
        result = await provider.generate_with_tools(messages, tools)
        return LLMResponse(
            content=result.get("content"),
            tool_calls=result.get("tool_calls", []),
            model=result.get("model", provider.model_id()),
        )
    except RuntimeError as e:
        raise LLMError(str(e), LLMErrorType.UNKNOWN, retryable=False) from e


def _run_llm(
    prompt: str,
    response_schema: Optional[type] = None,
    max_tokens: Optional[int] = None,
) -> tuple[str, str]:
    """Route through the active provider for general LLM calls."""
    from .providers import get_provider
    provider = get_provider()
    json_schema = None
    if response_schema is not None:
        json_schema = response_schema.model_json_schema()
    try:
        content = provider.generate(prompt, response_schema=json_schema, max_tokens=max_tokens)
    except TypeError as exc:
        if "max_tokens" not in str(exc):
            raise
        content = provider.generate(prompt, response_schema=json_schema)
    return content, provider.model_id()


def run_chat_completion(
    prompt: str,
) -> tuple[str, str]:
    """Run a chat completion with a pre-built prompt and return (content, model_id)."""
    return _run_llm(prompt)


# Language name mapping for translation prompts
LANGUAGE_NAMES = {
    "en": "English",
    "it": "Italian",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "pl": "Polish",
    "tr": "Turkish",
    "nl": "Dutch",
    "sv": "Swedish",
    "no": "Norwegian",
    "da": "Danish",
    "fi": "Finnish",
    "cs": "Czech",
    "hu": "Hungarian",
    "ro": "Romanian",
    "uk": "Ukrainian",
    "th": "Thai",
    "vi": "Vietnamese",
    "ar": "Arabic",
    "id": "Indonesian",
    "el": "Greek",
}


def translate_text(text: str, target_language: str) -> tuple[str, str]:
    """Translate text to the target language using the active LLM provider.

    Args:
        text: The text to translate
        target_language: Target language code (e.g., 'en', 'it', 'fr', 'de')

    Returns:
        Tuple of (translated_text, model_id)
    """
    if not text or not text.strip():
        from .providers import get_provider
        provider = get_provider()
        return text, provider.model_id()

    target_name = LANGUAGE_NAMES.get(target_language, target_language)

    prompt = f"""Translate the following text to {target_name}.
Only output the translated text, nothing else. Preserve the original formatting and tone.
If the text is already in {target_name}, return it unchanged.

Text to translate:
{text}"""

    translated, model_used = _run_llm(prompt)
    return translated.strip(), model_used


def _parse_payload(raw: str) -> Dict[str, Any]:
    if not raw:
        raise ValueError("Empty response from LLM")

    payload = _load_json_mapping(raw)
    return _parse_payload_mapping(payload)


def _parse_payload_mapping(payload: Mapping[str, Any]) -> Dict[str, Any]:
    # Multi-label subcategories (canonical format "main/sub").
    # `subcategories[0]` is treated as the primary label; main/sub are derived from it.
    candidate_subcategories = _parse_subcategory_list(payload.get("subcategories"))
    if not candidate_subcategories:
        main_value = payload.get("main_category") or payload.get("main")
        sub_value = payload.get("subcategory") or payload.get("sub")
        normalized_primary = _normalize_subcategory_value({"main_category": main_value, "subcategory": sub_value})
        if normalized_primary:
            candidate_subcategories = [normalized_primary]
    if not candidate_subcategories:
        raise ValueError("No valid subcategories found in LLM response.")
    if len(candidate_subcategories) > 6:
        candidate_subcategories = candidate_subcategories[:6]

    issue_subcategories = _parse_subcategory_list(payload.get("issue_subcategories"))
    request_subcategories = _parse_subcategory_list(payload.get("request_subcategories"))

    primary_key = candidate_subcategories[0]
    main_category, subcategory = primary_key.split("/", 1)

    def _ordered_unique(items: Sequence[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    subcategories = candidate_subcategories
    issue_subcategories = [entry for entry in _ordered_unique(issue_subcategories) if entry in subcategories][:6]
    request_subcategories = [entry for entry in _ordered_unique(request_subcategories) if entry in subcategories][:6]
    evidence = _parse_evidence(payload.get("evidence"), subcategories)
    aspects = _parse_aspects(payload.get("aspects"), subcategories)

    return {
        "main_category": main_category,
        "subcategory": subcategory,
        "subcategories": subcategories,
        "issue_subcategories": issue_subcategories,
        "request_subcategories": request_subcategories,
        "evidence": evidence,
        "aspects": aspects,
    }


def normalize_taxonomy_payload(payload: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a stored label payload to the currently supported taxonomy.

    This is used to keep older cached labels compatible when subcategory keys are renamed
    (e.g., v1 -> v1.1) without forcing a full re-labeling run.
    """
    if not isinstance(payload, Mapping):
        return _DEFAULT_LABEL.copy()

    proxy: Dict[str, Any] = {
        "subcategories": payload.get("subcategories"),
        "issue_subcategories": payload.get("issue_subcategories"),
        "request_subcategories": payload.get("request_subcategories"),
        "evidence": payload.get("evidence"),
        "aspects": payload.get("aspects"),
        # Optional fallback fields (some payloads may contain these).
        "main_category": payload.get("main_category") or payload.get("main"),
        "subcategory": payload.get("subcategory") or payload.get("sub"),
    }

    try:
        normalized = _parse_payload_mapping(proxy)
    except Exception:
        fallback = _DEFAULT_LABEL.copy()
        fallback["evidence"] = _parse_evidence(payload.get("evidence"), fallback["subcategories"])
        fallback["aspects"] = _parse_aspects(payload.get("aspects"), fallback["subcategories"])
        return fallback

    for extra_key in ("_label_source", "_label_model"):
        if extra_key in payload:
            normalized[extra_key] = payload.get(extra_key)

    return normalized


def _classifier_prompt_variant() -> str:
    value = os.getenv("SENTINEXT_CLASSIFIER_PROMPT_VARIANT", "legacy").strip().lower()
    return value if value in {"legacy", "v3", "v3_1"} else "legacy"


def _active_classifier_prompt_version() -> str:
    variant = _classifier_prompt_variant()
    if variant == "v3_1":
        return PROMPT_VERSION_V3_1
    return PROMPT_VERSION_V3 if variant == "v3" else PROMPT_VERSION


def active_classifier_prompt_version() -> str:
    """Return the prompt version used by the current classifier batch run."""
    return _active_classifier_prompt_version()


def _build_batch_prompt_legacy(
    items: Sequence[Mapping[str, Any]],
    *,
    game_context: Optional[Dict[str, Any]] = None,
) -> str:
    # Build game context strings (same shape as `_build_prompt`, but once per batch).
    if game_context:
        game_name = game_context.get("name", "Unknown")
        game_type = game_context.get("type", "game")
        genres = game_context.get("genres", [])
        categories = game_context.get("categories", [])
        description = game_context.get("short_description", "")[:200]

        game_genres = ", ".join(genres) if genres else "Unknown"
        game_categories = ", ".join(categories[:5]) if categories else "Unknown"
        game_description = description if description else "Not available"
    else:
        game_name = "Unknown"
        game_type = "game"
        game_genres = "Unknown"
        game_categories = "Unknown"
        game_description = "Not available"

    blocks: list[str] = []
    for item in items:
        review_id = str(item.get("review_id") or "")
        review_text = str(item.get("review_text") or "")
        review_language = str(item.get("review_language") or "english")
        reviewer_playtime = float(item.get("reviewer_playtime") or 0)
        reviewer_voted_up = bool(item.get("reviewer_voted_up", True))
        truncated = _sanitize_review_text(review_text or "")
        playtime_hours = round(reviewer_playtime / 60, 1) if reviewer_playtime else 0
        recommendation = "Positive" if reviewer_voted_up else "Negative"
        blocks.append(
            dedent(
                f"""[review_id={review_id}]
                Language: {review_language}
                Playtime_hours: {playtime_hours}
                Recommendation: {recommendation}
                <<<BEGIN REVIEW>>>
                {truncated}
                <<<END REVIEW>>>"""
            ).strip()
        )

    return _BATCH_PROMPT_TEMPLATE_LEGACY.substitute(
        game_name=game_name,
        game_type=game_type,
        game_genres=game_genres,
        game_categories=game_categories,
        game_description=game_description,
        reviews_text="\n\n".join(blocks),
    )


def _build_batch_prompt_v3(
    items: Sequence[Mapping[str, Any]],
) -> str:
    blocks: list[str] = []
    for item in items:
        review_id = str(item.get("review_id") or "")
        truncated = _sanitize_review_text(str(item.get("review_text") or ""))
        blocks.append(
            dedent(
                f"""[review_id={review_id}]
                <<<BEGIN REVIEW>>>
                {truncated}
                <<<END REVIEW>>>"""
            ).strip()
        )
    return _BATCH_PROMPT_TEMPLATE_V3.substitute(reviews_text="\n\n".join(blocks))


def _build_batch_prompt_v3_1(items: Sequence[Mapping[str, Any]]) -> str:
    blocks: list[str] = []
    for item in items:
        review_id = str(item.get("review_id") or "")
        truncated = _sanitize_review_text(str(item.get("review_text") or ""))
        blocks.append(
            dedent(
                f"""[review_id={review_id}]
                <<<BEGIN REVIEW>>>
                {truncated}
                <<<END REVIEW>>>"""
            ).strip()
        )
    return _BATCH_PROMPT_TEMPLATE_V3_1.substitute(reviews_text="\n\n".join(blocks))


def _build_batch_prompt(
    items: Sequence[Mapping[str, Any]],
    *,
    game_context: Optional[Dict[str, Any]] = None,
) -> str:
    if _classifier_prompt_variant() == "v3_1":
        return _build_batch_prompt_v3_1(items)
    if _classifier_prompt_variant() == "v3":
        return _build_batch_prompt_v3(items)
    return _build_batch_prompt_legacy(items, game_context=game_context)


def classification_identity(
    review: Mapping[str, Any],
    game_context: Optional[Dict[str, Any]],
    *,
    provider: Optional[str],
    model_id: Optional[str],
    prompt_version: Optional[str] = None,
    taxonomy_version: str = TAXONOMY_VERSION,
    mode: str = "batch",
    processed_text: Optional[str] = None,
    preprocessor_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the complete semantic identity of one classifier input."""
    prompt_version = prompt_version or _active_classifier_prompt_version()
    raw_text = str(review.get("review") or review.get("review_text") or "").strip()
    # The identity must hash exactly the text that the classifier builder will
    # send, including dangerous-string replacement and the 3000-char cap.
    processed_text = _sanitize_review_text(
        raw_text if processed_text is None else str(processed_text)
    )
    context = game_context or {}
    prompt_variant = "v3" if prompt_version == PROMPT_VERSION_V3 else "legacy"
    semantic_input = {
        "schema_version": CLASSIFICATION_SCHEMA_VERSION,
        "mode": mode,
        "review_text": processed_text,
        "preprocessor_version": preprocessor_version,
        "prompt_variant": prompt_variant,
    }
    if prompt_variant == "legacy":
        semantic_input.update({
            "review_language": str(review.get("language") or review.get("review_language") or "english"),
            "playtime_hours": round(float(review.get("author", {}).get("playtime_forever", 0) if isinstance(review.get("author"), Mapping) else review.get("reviewer_playtime", 0) or 0) / 60, 1),
            "reviewer_recommendation": bool(review.get("voted_up", review.get("reviewer_voted_up", True))),
            "game_context": {
                "name": context.get("name", "Unknown"),
                "type": context.get("type", "game"),
                "genres": list(context.get("genres") or []),
                "categories": list((context.get("categories") or [])[:5]),
                "short_description": str(context.get("short_description") or "")[:200],
            },
        })
    canonical = json.dumps(semantic_input, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "review_hash": hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        "classification_input_hash": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "taxonomy_version": taxonomy_version,
        "prompt_version": prompt_version,
        "provider": provider,
        "model_id": model_id,
        "was_truncated": processed_text != raw_text,
        "original_char_count": len(raw_text),
        "processed_char_count": len(processed_text),
    }


def label_cache_eligible(label: Mapping[str, Any], current_identity: Mapping[str, Any]) -> bool:
    """Centralized rule for reusing a persisted label."""
    return bool(
        label.get("label_origin") == "llm"
        and label.get("validated") is True
        and label.get("review_hash") == current_identity.get("review_hash")
        and label.get("classification_input_hash") == current_identity.get("classification_input_hash")
        and label.get("taxonomy_version") == current_identity.get("taxonomy_version")
        and label.get("prompt_version") == current_identity.get("prompt_version")
        and label.get("provider") == current_identity.get("provider")
        and label.get("model_id") == current_identity.get("model_id")
    )


def label_cache_identity(
    review_text: str,
    taxonomy_version: str,
    prompt_version: str,
    model_id: str,
    *,
    provider: Optional[str] = None,
    classification_input_hash: Optional[str] = None,
) -> str:
    """Stable public digest for callers that need to inspect cache identity."""
    identity = {
        "review_hash": hashlib.sha256(str(review_text).encode("utf-8")).hexdigest(),
        "taxonomy_version": taxonomy_version,
        "prompt_version": prompt_version,
        "provider": provider,
        "model_id": model_id,
        "classification_input_hash": classification_input_hash,
    }
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _active_model_id() -> str:
    """Return model_id string for the currently active provider, or '' if none."""
    from .providers.config import get_active_provider
    name, model = get_active_provider()
    return _model_id(name, model) if name and model else ""


def classify_reviews_batch(
    items: Sequence[Mapping[str, Any]],
    *,
    game_context: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Dict[str, Any]], str]:
    if not items:
        return {}, _active_model_id()

    expected_ids = [str(item.get("review_id") or "") for item in items]
    if any(not rid for rid in expected_ids):
        raise ValueError("Missing review_id in batch input.")

    logger.info(f"Classifying batch of {len(items)} reviews with LLM")
    prompt = _build_batch_prompt(items, game_context=game_context)
    raw, model_used = _run_llm(prompt, max_tokens=estimate_batch_output_tokens(len(items)))
    logger.info(f"LLM batch classification complete: {len(items)} reviews processed")
    payload = _load_json_mapping(raw)

    results: Dict[str, Dict[str, Any]] = {}
    failed_ids = []
    for review_id in expected_ids:
        entry = payload.get(review_id)
        if not isinstance(entry, dict):
            logger.warning(f"Missing/invalid payload for review_id={review_id}, using default label")
            missing_payload = _DEFAULT_LABEL.copy()
            missing_payload["_batch_missing"] = True
            results[review_id] = missing_payload
            failed_ids.append(review_id)
            continue
        try:
            results[review_id] = _parse_payload_mapping(entry)
        except ValueError as e:
            logger.warning(f"Failed to parse payload for review_id={review_id}: {e}, using default label")
            results[review_id] = _DEFAULT_LABEL.copy()
            results[review_id]["_batch_invalid"] = True
            failed_ids.append(review_id)

    # Preserve unexpected provider keys for the dynamic validator to observe.
    # They are never consumed by the persistence loop.
    for returned_id, returned_value in payload.items():
        if str(returned_id) not in expected_ids:
            results[str(returned_id)] = returned_value

    if failed_ids:
        logger.warning(f"Batch had {len(failed_ids)} parsing failures out of {len(expected_ids)} reviews")

    return results, model_used


def classify_reviews(items: Sequence[Mapping[str, Any]], *, game_context: Optional[Dict[str, Any]] = None) -> tuple[Dict[str, Dict[str, Any]], str]:
    """Classify reviews in a batch with fallback to single-review processing on failure."""
    if not items:
        return {}, _active_model_id()

    try:
        return classify_reviews_batch(items, game_context=game_context)
    except Exception as batch_error:
        # Batch failed completely - retry each review individually
        if len(items) == 1:
            # Already single review, use default label
            review_id = str(items[0].get("review_id") or "unknown")
            logger.error(f"Single review classification failed for {review_id}: {batch_error}")
            return {review_id: _DEFAULT_LABEL.copy()}, _active_model_id()

        logger.warning(f"Batch of {len(items)} failed: {batch_error}. Retrying individually...")
        results: Dict[str, Dict[str, Any]] = {}
        model_used = _active_model_id()

        for item in items:
            review_id = str(item.get("review_id") or "unknown")
            try:
                single_result, model_used = classify_review_basic_single(item, game_context=game_context)
                results.update(single_result)
            except Exception as single_error:
                logger.warning(f"Individual review {review_id} failed: {single_error}, using default label")
                results[review_id] = _DEFAULT_LABEL.copy()

    return results, model_used


def classify_review_basic_single(
    item: Dict[str, Any],
    *,
    game_context: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Run the lightweight first-pass classifier for one retry item."""
    review_id = str(item.get("review_id") or "")
    if not review_id:
        raise ValueError("Missing review_id in single retry input.")
    prompt = _build_batch_prompt([item], game_context=game_context)
    raw, model_used = _run_llm(prompt, max_tokens=512)
    payload = _load_json_mapping(raw)
    entry = payload.get(review_id)
    if not isinstance(entry, dict):
        raise ValueError(f"Basic classifier response missing review_id={review_id}")
    if entry.get("_batch_missing"):
        raise ValueError(f"Basic classifier returned missing review_id={review_id}")
    return _parse_payload_mapping(entry), model_used


def classify_review_single(
    item: Dict[str, Any],
    *,
    game_context: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str]:
    """Classify a single review using the active provider.

    Uses one structured-output call per review with the currently active provider.
    Falls back to _DEFAULT_LABEL if all attempts fail.
    """
    from .providers import get_provider

    provider = get_provider()
    review_text = (item.get("review_text") or "").strip()
    if not review_text:
        return _DEFAULT_LABEL.copy(), provider.model_id()

    prompt = _build_prompt(
        review_text,
        game_context,
        item.get("reviewer_playtime", 0),
        item.get("reviewer_voted_up", True),
        item.get("review_language"),
    )

    raw = provider.generate_with_pydantic(prompt, ReviewClassification)
    payload = _load_json_mapping(raw)
    validated = _parse_payload_mapping(payload)
    logger.debug("Provider %s succeeded for review %s", provider.name, item.get("review_id"))
    return validated, provider.model_id()


def classify_review(
    review_text: str,
    game_context: Optional[Dict[str, Any]] = None,
    reviewer_playtime: float = 0,
    reviewer_voted_up: bool = True,
    review_language: Optional[str] = None,
) -> Tuple[Dict[str, Any], str]:
    """Legacy single-review classification. Delegates to classify_review_single."""
    item = {
        "review_text": review_text,
        "reviewer_playtime": reviewer_playtime,
        "reviewer_voted_up": reviewer_voted_up,
        "review_language": review_language,
    }
    return classify_review_single(item, game_context=game_context)


def ensure_review_labels(
    app_id: int,
    reviews: Sequence[Mapping[str, Any]],
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    game_context: Optional[Dict[str, Any]] = None,
    cache_enabled: bool = True,
) -> Dict[str, Dict[str, Any]]:
    from .providers.config import get_active_provider

    if not reviews:
        if progress_callback is not None:
            progress_callback(0, 0)
        return {}

    existing = storage.load_review_labels(app_id) if cache_enabled else {}
    preprocess_mode = review_preprocessor.get_mode()
    preprocess_run = review_preprocessor.preprocess_reviews_for_classification(
        app_id, reviews, mode=preprocess_mode,
    ) if preprocess_mode != "off" else None
    active_name, active_model = get_active_provider()
    active_prompt_version = _active_classifier_prompt_version()
    current_model_id = _model_id(active_name, active_model) if active_name and active_model else None
    results: Dict[str, Dict[str, Any]] = {}
    total_reviews = len(reviews)
    processed_count = 0
    failed_count = 0
    cached_reuse_count = 0

    pending_reviews: list[Dict[str, Any]] = []

    if progress_callback is not None:
        progress_callback(0, total_reviews)

    for review in reviews:
        review_id_value = review.get("recommendationid") or review.get("review_id")
        if review_id_value is None:
            processed_count += 1
            if progress_callback is not None:
                progress_callback(processed_count, total_reviews)
            continue
        review_id = str(review_id_value)
        prep_result = preprocess_run.results.get(review_id) if preprocess_run is not None else None
        review_text = (review.get("review") or "").strip()
        identity = classification_identity(
            review, game_context, provider=active_name, model_id=current_model_id,
            prompt_version=active_prompt_version,
            processed_text=(prep_result.processed_text if preprocess_mode == "active" and prep_result else None),
            preprocessor_version=(review_preprocessor.PREPROCESSOR_VERSION if preprocess_mode == "active" else None),
        )
        review_hash = identity["review_hash"]

        cached = existing.get(review_id)
        needs_refresh = force_refresh or cached is None or not label_cache_eligible(cached or {}, identity)

        if not review_text:
            if cached is not None and not needs_refresh:
                payload = cached["payload"]
            else:
                payload = _DEFAULT_LABEL.copy()
                payload["_label_source"] = "empty_review"
                payload["_label_model"] = "empty_review"
                if cache_enabled:
                    storage.upsert_review_label(
                        app_id,
                        review_id,
                        review_hash,
                        payload,
                        "empty_review",
                        active_prompt_version,
                        label_origin="rule_fallback", validated=False,
                        taxonomy_version=TAXONOMY_VERSION, provider=None, model_id=None,
                        classification_input_hash=identity["classification_input_hash"],
                        was_truncated=identity["was_truncated"],
                        original_char_count=identity["original_char_count"],
                        processed_char_count=identity["processed_char_count"],
                        generated_at=datetime.now(timezone.utc),
                    )
            results[review_id] = {**payload, "_resolution_source": "generated"}
            processed_count += 1
            if progress_callback is not None:
                progress_callback(processed_count, total_reviews)
            continue

        # Only empty and high-confidence pure-nonlexical reviews may bypass
        # classification. Short lexical text remains an LLM candidate.
        if preprocess_mode == "active" and prep_result is not None and prep_result.skip_llm:
            if cached is not None and not needs_refresh:
                payload = normalize_taxonomy_payload(cached.get("payload") or {})
            else:
                payload = _DEFAULT_LABEL.copy()
                payload["_label_source"] = "nonlexical_skip"
                payload["_label_model"] = "nonlexical_skip"
                if cache_enabled:
                    storage.upsert_review_label(
                        app_id, review_id, identity["review_hash"], payload,
                        "nonlexical_skip", active_prompt_version,
                        label_origin="rule_fallback", validated=False,
                        taxonomy_version=TAXONOMY_VERSION, provider=None, model_id=None,
                        classification_input_hash=identity["classification_input_hash"],
                        was_truncated=identity["was_truncated"],
                        original_char_count=identity["original_char_count"],
                        processed_char_count=identity["processed_char_count"],
                        generated_at=datetime.now(timezone.utc),
                    )
            results[review_id] = {**payload, "_resolution_source": "generated"}
            processed_count += 1
            if progress_callback is not None:
                progress_callback(processed_count, total_reviews)
            continue

        if not needs_refresh:
            cached_payload = cached.get("payload") or {}
            payload = normalize_taxonomy_payload(cached_payload)
            payload = {**payload, "_resolution_source": "cache_hit"}
            results[review_id] = payload
            cached_reuse_count += 1
            processed_count += 1
            if progress_callback is not None:
                progress_callback(processed_count, total_reviews)
            continue

        # Extract reviewer context from review
        reviewer_playtime = review.get("author", {}).get("playtime_forever", 0)
        reviewer_voted_up = review.get("voted_up", True)
        review_language = review.get("language", "english")

        pending_reviews.append(
            {
                "review_id": review_id,
                "review_text": (prep_result.processed_text if preprocess_mode == "active" and prep_result else review_text),
                "original_review_text": review_text,
                "review_hash": review_hash,
                "classification_input_hash": identity["classification_input_hash"],
                "was_truncated": identity["was_truncated"],
                "original_char_count": identity["original_char_count"],
                "processed_char_count": identity["processed_char_count"],
                "reviewer_playtime": reviewer_playtime,
                "reviewer_voted_up": reviewer_voted_up,
                "review_language": review_language,
                "votes_up": int(review.get("votes_up") or 0),
                "timestamp_created": int(review.get("timestamp_created") or 0),
            }
        )

    # Active duplicate reuse is scoped to this classification call and this
    # app. Cached historical labels are intentionally not consulted here.
    duplicate_members_by_rep: dict[str, list[Dict[str, Any]]] = {}
    if preprocess_mode == "active" and preprocess_run is not None and preprocess_run.metrics.get("exact_duplicate_groups"):
        pending_by_id = {str(item["review_id"]): item for item in pending_reviews}
        grouped: dict[tuple[int, str], list[Dict[str, Any]]] = {}
        for item in pending_reviews:
            prep = preprocess_run.results.get(str(item["review_id"]))
            if prep is None or not prep.duplicate_group_key:
                grouped[(app_id, str(item["review_id"]))] = [item]
            else:
                grouped.setdefault(prep.duplicate_group_key, []).append(item)
        representative_pending: list[Dict[str, Any]] = []
        for members in grouped.values():
            representative = members[0]
            duplicate_members_by_rep[str(representative["review_id"])] = members
            representative_pending.append(representative)
        pending_reviews = representative_pending
    else:
        duplicate_members_by_rep = {str(item["review_id"]): [item] for item in pending_reviews}

    if preprocess_run is not None:
        preprocess_run.metrics["actual_llm_reviews_submitted"] = len(pending_reviews)
        preprocess_run.metrics["actual_duplicate_inputs_saved"] = (
            sum(max(0, len(members) - 1) for members in duplicate_members_by_rep.values())
            if preprocess_mode == "active" else 0
        )
        preprocess_run.metrics["actual_nonlexical_skips"] = sum(
            1 for result in preprocess_run.results.values() if result.skip_llm
        ) if preprocess_mode == "active" else 0
        logger.info("Review preprocessing mode=%s metrics=%s", preprocess_mode, preprocess_run.metrics)

    provider_label = active_name or "unknown"
    logger.info(f"{len(pending_reviews)} reviews to classify via {provider_label} provider")

    # Process reviews in parallel batches. A failed batch falls back to single
    # review calls so one malformed response does not discard the whole batch.
    if pending_reviews:
        if active_name == "ollama":
            # Keep Ollama strictly sequential to avoid local model overload/timeouts.
            max_workers = 1
        else:
            from .providers.config import get_max_workers
            max_workers = get_max_workers()
        configured_batch_size = max(1, int(os.getenv("SENTINEXT_LLM_BATCH_SIZE", "100")))
        batch_size = 1 if active_name == "ollama" else min(configured_batch_size, 200)

        # Keep normal batches large, but reduce the size when review text is
        # long. This protects the model context window and makes malformed JSON
        # responses cheaper to retry.
        LONG_REVIEW_CHARS = 1200
        VERY_LONG_REVIEW_CHARS = 8000
        MAX_BATCH_CHARS = 32000
        review_batches: list[list[Dict[str, Any]]] = []
        planned_by_ids: dict[tuple[str, ...], batch_planner.PlannedBatch] = {}
        current_batch: list[Dict[str, Any]] = []
        current_chars = 0

        def _flush_batch() -> None:
            nonlocal current_batch, current_chars
            if current_batch:
                review_batches.append(current_batch)
            current_batch = []
            current_chars = 0

        dynamic_enabled = os.getenv("SENTINEXT_DYNAMIC_BATCH_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        if dynamic_enabled:
            config = batch_planner.BatchPlannerConfig.from_env()
            plans = batch_planner.DynamicBatchPlanner(config).plan(pending_reviews)
            review_batches = [list(plan.items) for plan in plans]
            planned_by_ids = {plan.review_ids: plan for plan in plans}
            logger.info("Dynamic batch planner metrics=%s", batch_planner.DynamicBatchPlanner(config).metrics(plans))
        else:
            for item in pending_reviews:
                text_length = len(str(item.get("review_text") or ""))
                if active_name != "ollama" and text_length >= VERY_LONG_REVIEW_CHARS:
                    _flush_batch()
                    review_batches.append([item])
                    continue

                target_size = 50 if text_length >= LONG_REVIEW_CHARS else batch_size
                if current_batch and (
                    len(current_batch) >= target_size
                    or current_chars + text_length > MAX_BATCH_CHARS
                ):
                    _flush_batch()
                current_batch.append(item)
                current_chars += text_length
            _flush_batch()
        logger.info(
            "Processing %s reviews in %s dynamic batches (base_batch_size=%s, max_workers=%s, provider=%s)",
            len(pending_reviews),
            len(review_batches),
            batch_size,
            max_workers,
            provider_label,
        )

        # If a provider goes unstable, we degrade to fallback labels
        # so the analysis can still complete and be persisted.
        CONSECUTIVE_FAIL_LIMIT = 5
        consecutive_failures = 0
        last_failure_error: Optional[str] = None
        fallback_model_id = _model_id(active_name or "unknown", active_model or "unknown")

        # Bulk write buffer
        BULK_WRITE_SIZE = 20
        label_write_buffer: list[dict] = []

        def _flush_label_buffer(buf: list[dict]) -> None:
            if buf and cache_enabled:
                storage.bulk_upsert_review_labels(list(buf))
                buf.clear()

        def _record_success(item: Dict[str, Any], payload: Dict[str, Any], model_used: str) -> None:
            nonlocal processed_count, consecutive_failures
            members = duplicate_members_by_rep.get(str(item["review_id"]), [item])
            for member in members:
                review_id = str(member["review_id"])
                member_payload = {**payload, "_label_source": "llm", "_label_model": model_used}
                label_write_buffer.append({
                    "app_id": app_id,
                    "review_id": review_id,
                    "review_hash": member["review_hash"],
                    "classification_input_hash": member["classification_input_hash"],
                    "was_truncated": member["was_truncated"],
                    "original_char_count": member["original_char_count"],
                    "processed_char_count": member["processed_char_count"],
                    "payload": member_payload,
                    "model": model_used,
                    "prompt_version": active_prompt_version,
                    "label_origin": "llm",
                    "validated": True,
                    "taxonomy_version": TAXONOMY_VERSION,
                    "provider": str(model_used).split(":", 1)[0] if ":" in str(model_used) else active_name,
                    "model_id": model_used,
                    "generated_at": datetime.now(timezone.utc),
                })
                results[review_id] = {**member_payload, "_resolution_source": "generated"}
            processed_count += len(members)
            consecutive_failures = 0

            if len(label_write_buffer) >= BULK_WRITE_SIZE:
                _flush_label_buffer(label_write_buffer)

            if progress_callback is not None:
                progress_callback(processed_count, total_reviews)

        def _record_failure(
            item: Dict[str, Any],
            error_message: str,
            *,
            increment_consecutive: bool = True,
        ) -> None:
            nonlocal failed_count, processed_count, consecutive_failures, last_failure_error

            logger.error("Review %s classification failed: %s", item.get("review_id"), error_message)
            members = duplicate_members_by_rep.get(str(item["review_id"]), [item])
            failed_count += len(members)
            processed_count += len(members)
            if increment_consecutive:
                consecutive_failures += 1
                last_failure_error = error_message

            fallback_payload = _DEFAULT_LABEL.copy()
            fallback_payload["_label_source"] = "llm_fallback"
            fallback_payload["_label_model"] = fallback_model_id
            for member in members:
                review_id = str(member["review_id"])
                label_write_buffer.append({
                    "app_id": app_id,
                    "review_id": review_id,
                    "review_hash": member["review_hash"],
                    "classification_input_hash": member["classification_input_hash"],
                    "was_truncated": member["was_truncated"],
                    "original_char_count": member["original_char_count"],
                    "processed_char_count": member["processed_char_count"],
                    "payload": {**fallback_payload},
                    "model": fallback_model_id,
                    "prompt_version": active_prompt_version,
                    "label_origin": "rule_fallback",
                    "validated": False,
                    "taxonomy_version": TAXONOMY_VERSION,
                    "provider": None,
                    "model_id": None,
                    "generated_at": datetime.now(timezone.utc),
                })
                results[review_id] = {**fallback_payload, "_resolution_source": "generated"}

            if len(label_write_buffer) >= BULK_WRITE_SIZE:
                _flush_label_buffer(label_write_buffer)

            if progress_callback is not None:
                try:
                    progress_callback(processed_count, total_reviews)
                except InterruptedError:
                    raise
                except Exception:
                    pass

        def _process_batch(batch: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], str, List[Dict[str, Any]], float]:
            started = time.perf_counter()
            payloads, model_used = classify_reviews_batch(batch, game_context=game_context)
            return payloads, model_used, batch, (time.perf_counter() - started) * 1000

        retry_config = batch_planner.BatchPlannerConfig.from_env()

        def _validate_dynamic_payloads(expected_items, payloads):
            """Normalize the batch adapter's markers into validator input."""
            expected_ids = [str(item["review_id"]) for item in expected_items]
            raw_results = {}
            for returned_id, payload in payloads.items():
                if isinstance(payload, dict) and payload.get("_batch_missing"):
                    continue
                raw_results[str(returned_id)] = None if (
                    isinstance(payload, dict) and payload.get("_batch_invalid")
                ) else payload
            return batch_planner.validate_batch_results(
                expected_ids,
                raw_results,
                parse_result=_parse_payload_mapping,
            )

        def _recover_dynamic_batch(batch: list[Dict[str, Any]], *, attempt: int, split_depth: int) -> None:
            """Retry only failed IDs; split only an unrecoverable response."""
            if not batch:
                return
            plan = batch_planner.DynamicBatchPlanner(retry_config).plan(
                batch, batch_id_prefix="retry", attempt_number=attempt,
                is_retry=True, split_depth=split_depth,
            )
            for retry_plan in plan:
                retry_items = list(retry_plan.items)
                started = time.perf_counter()
                try:
                    retry_payloads, retry_model = classify_reviews_batch(retry_items, game_context=game_context)
                except ProviderFailure as provider_error:
                    error_type = batch_planner.classify_provider_error(provider_error)
                    logger.info("Batch telemetry=%s", batch_planner.batch_telemetry(
                        retry_plan, error_type=error_type, latency_ms=(time.perf_counter() - started) * 1000,
                    ))
                    if error_type == "OUTPUT_TRUNCATED" and attempt < retry_config.max_retry_attempts and len(retry_items) > retry_config.min_split_size:
                        midpoint = len(retry_items) // 2
                        _recover_dynamic_batch(retry_items[:midpoint], attempt=attempt + 1, split_depth=split_depth + 1)
                        _recover_dynamic_batch(retry_items[midpoint:], attempt=attempt + 1, split_depth=split_depth + 1)
                    elif getattr(provider_error, "retryable", False) and attempt < retry_config.max_retry_attempts:
                        # Transport/rate-limit failures should retry the same
                        # batch; splitting is reserved for malformed output.
                        _recover_dynamic_batch(retry_items, attempt=attempt + 1, split_depth=split_depth)
                    elif attempt < retry_config.max_retry_attempts and error_type in {"RATE_LIMIT", "PROVIDER_SERVER_ERROR", "TIMEOUT", "NETWORK_ERROR"}:
                        _recover_dynamic_batch(retry_items, attempt=attempt + 1, split_depth=split_depth)
                    else:
                        for retry_item in retry_items:
                            _record_failure(retry_item, str(provider_error), increment_consecutive=False)
                except Exception as structural_error:
                    logger.info("Batch telemetry=%s", batch_planner.batch_telemetry(
                        retry_plan, error_type="WHOLE_RESPONSE_PARSE_ERROR",
                        latency_ms=(time.perf_counter() - started) * 1000,
                    ))
                    if attempt < retry_config.max_retry_attempts and len(retry_items) > retry_config.min_split_size:
                        midpoint = len(retry_items) // 2
                        _recover_dynamic_batch(retry_items[:midpoint], attempt=attempt + 1, split_depth=split_depth + 1)
                        _recover_dynamic_batch(retry_items[midpoint:], attempt=attempt + 1, split_depth=split_depth + 1)
                    else:
                        for retry_item in retry_items:
                            _record_failure(retry_item, str(structural_error), increment_consecutive=False)
                else:
                    validation = _validate_dynamic_payloads(retry_items, retry_payloads)
                    valid_items = [item for item in retry_items if str(item["review_id"]) in validation.valid_results]
                    invalid_items = [item for item in retry_items if str(item["review_id"]) in validation.retry_ids]
                    for valid_item in valid_items:
                        _record_success(valid_item, validation.valid_results[str(valid_item["review_id"])], retry_model)
                    if validation.unexpected_ids or validation.duplicate_return_ids:
                        logger.warning(
                            "Dynamic batch validation anomaly batch_id=%s unexpected=%s duplicate=%s",
                            retry_plan.batch_id, validation.unexpected_ids, validation.duplicate_return_ids,
                        )
                    logger.info("Batch telemetry=%s", batch_planner.batch_telemetry(
                        retry_plan, valid_count=len(validation.valid_results),
                        invalid_count=len(validation.invalid_ids), missing_count=len(validation.missing_ids),
                        success=not validation.retry_ids, latency_ms=(time.perf_counter() - started) * 1000,
                    ))
                    if invalid_items:
                        if attempt < retry_config.max_retry_attempts:
                            _recover_dynamic_batch(invalid_items, attempt=attempt + 1, split_depth=split_depth)
                        else:
                            for invalid_item in invalid_items:
                                _record_failure(invalid_item, "Maximum batch retry attempts reached.", increment_consecutive=False)

        # Global timeout: 3 minutes per review (generous, accounts for retries + rate limits).
        # Prevents the entire background task from hanging forever if a worker thread is stuck.
        global_timeout = max(600, len(review_batches) * 180)  # At least 10 min
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            future_to_batch = {}
            for batch in review_batches:
                ctx = contextvars.copy_context()
                future = executor.submit(ctx.run, _process_batch, batch)
                future_to_batch[future] = batch

            try:
                for future in as_completed(list(future_to_batch), timeout=global_timeout):
                    batch = future_to_batch.pop(future, None)
                    if batch is None:
                        continue

                    try:
                        payloads, model_used, _, latency_ms = future.result(timeout=120)
                        if dynamic_enabled:
                            validation = _validate_dynamic_payloads(batch, payloads)
                            valid_items = [
                                (item, validation.valid_results[str(item["review_id"])])
                                for item in batch if str(item["review_id"]) in validation.valid_results
                            ]
                            retry_items = [item for item in batch if str(item["review_id"]) in validation.retry_ids]
                            for item, payload in valid_items:
                                _record_success(item, payload, model_used)
                            plan = planned_by_ids.get(tuple(str(item["review_id"]) for item in batch))
                            if plan is not None:
                                if validation.unexpected_ids or validation.duplicate_return_ids:
                                    logger.warning(
                                        "Dynamic batch validation anomaly batch_id=%s unexpected=%s duplicate=%s",
                                        plan.batch_id, validation.unexpected_ids, validation.duplicate_return_ids,
                                    )
                                logger.info("Batch telemetry=%s", batch_planner.batch_telemetry(
                                    plan, valid_count=len(validation.valid_results),
                                    invalid_count=len(validation.invalid_ids), missing_count=len(validation.missing_ids),
                                    success=not validation.retry_ids, latency_ms=latency_ms,
                                ))
                            if retry_items:
                                if retry_config.max_retry_attempts >= 1:
                                    _recover_dynamic_batch(retry_items, attempt=1, split_depth=0)
                                else:
                                    for retry_item in retry_items:
                                        _record_failure(retry_item, "Maximum batch retry attempts reached.", increment_consecutive=False)
                        else:
                            for item in batch:
                                review_id = str(item["review_id"])
                                payload = payloads.get(review_id)
                                if not isinstance(payload, dict) or payload.get("_batch_missing"):
                                    _recover_dynamic_batch([item], attempt=1, split_depth=0)
                                else:
                                    _record_success(item, payload, model_used)

                    except InterruptedError:
                        raise
                    except Exception as exc:
                        if dynamic_enabled:
                            if isinstance(exc, ProviderFailure):
                                error_type = batch_planner.classify_provider_error(exc)
                                logger.info("Batch telemetry=%s", batch_planner.batch_telemetry(
                                    planned_by_ids.get(tuple(str(item["review_id"]) for item in batch))
                                    or batch_planner.DynamicBatchPlanner(retry_config).plan(batch)[0],
                                    error_type=error_type,
                                ))
                                if error_type == "OUTPUT_TRUNCATED" and retry_config.max_retry_attempts >= 1 and len(batch) > retry_config.min_split_size:
                                    midpoint = len(batch) // 2
                                    _recover_dynamic_batch(batch[:midpoint], attempt=1, split_depth=1)
                                    _recover_dynamic_batch(batch[midpoint:], attempt=1, split_depth=1)
                                elif getattr(exc, "retryable", False) and retry_config.max_retry_attempts >= 1:
                                    _recover_dynamic_batch(batch, attempt=1, split_depth=0)
                                else:
                                    for failed_item in batch:
                                        _record_failure(failed_item, str(exc), increment_consecutive=False)
                            else:
                                if retry_config.max_retry_attempts >= 1:
                                    _recover_dynamic_batch(batch, attempt=1, split_depth=0)
                                else:
                                    for failed_item in batch:
                                        _record_failure(failed_item, str(exc), increment_consecutive=False)
                            continue
                        # Structural batch failures are recovered by the same
                        # bounded binary-split tree used by the dynamic path.
                        # Never fan one failed batch into N single requests.
                        logger.warning("Batch of %s reviews failed; recovering by bounded split: %s", len(batch), exc)
                        _recover_dynamic_batch(batch, attempt=1, split_depth=0)

                        if consecutive_failures >= CONSECUTIVE_FAIL_LIMIT:
                            logger.warning(
                                "Provider %s hit %s consecutive failures. "
                                "Using fallback labels for remaining %s reviews. Last error: %s",
                                provider_label,
                                CONSECUTIVE_FAIL_LIMIT,
                                len(future_to_batch),
                                last_failure_error,
                            )

                            for pending_future, pending_batch in list(future_to_batch.items()):
                                future_to_batch.pop(pending_future, None)

                                if pending_future.done():
                                    try:
                                        payloads, model_used, _, _ = pending_future.result(timeout=0)
                                        for pending_item in pending_batch:
                                            payload = payloads.get(str(pending_item["review_id"]))
                                            if not isinstance(payload, dict):
                                                raise ValueError("Batch response missing review")
                                            _record_success(pending_item, payload, model_used)
                                    except InterruptedError:
                                        raise
                                    except Exception as pending_exc:
                                        for pending_item in pending_batch:
                                            _record_failure(pending_item, str(pending_exc), increment_consecutive=False)
                                else:
                                    pending_future.cancel()
                                    for pending_item in pending_batch:
                                        _record_failure(pending_item, "Skipped after provider degradation fallback.", increment_consecutive=False)
                            break
            except TimeoutError:
                hung_count = len(future_to_batch)
                logger.error(
                    "Classification timed out after %ss with %s reviews still pending. "
                    "Applying fallback labels to pending reviews.",
                    global_timeout,
                    hung_count,
                )
                for pending_future, pending_batch in list(future_to_batch.items()):
                    future_to_batch.pop(pending_future, None)
                    pending_future.cancel()
                    for pending_item in pending_batch:
                        _record_failure(pending_item, f"Classification timed out after {global_timeout}s", increment_consecutive=False)
        finally:
            # Don't wait for hung threads — cancel queued futures and move on
            executor.shutdown(wait=False, cancel_futures=True)
            # Flush remaining labels (inside finally so we don't lose cached work)
            _flush_label_buffer(label_write_buffer)

        # Second pass: enrich only representative/high-risk reviews with
        # aspect sentiment and verbatim evidence. The first pass remains
        # lightweight for every review.
        enrich_limit = max(0, int(os.getenv("SENTINEXT_ASPECT_ENRICH_LIMIT", "0")))
        if enrich_limit and results:
            category_counts: Counter[str] = Counter()
            for payload in results.values():
                category_counts.update(payload.get("issue_subcategories") or [])
                category_counts.update(payload.get("request_subcategories") or [])
            priority_categories = {key for key, _ in category_counts.most_common(10)}
            severe_terms = (
                "crash", "崩溃", "cannot launch", "can't launch", "won't start", "无法启动",
                "lost save", "save corrupted", "存档", "progress lost", "data loss", "支付", "account banned",
            )
            candidates: list[Dict[str, Any]] = []
            for item in pending_reviews:
                rid = str(item["review_id"])
                payload = results.get(rid) or {}
                labels = set(payload.get("subcategories") or [])
                text = str(item.get("review_text") or "").lower()
                score = (
                    (1000 if labels & priority_categories else 0)
                    + (800 if any(term in text for term in severe_terms) else 0)
                    + min(int(item.get("votes_up") or 0), 500)
                    + min(len(text) // 100, 50)
                )
                candidates.append({"score": score, "item": item})
            candidates.sort(key=lambda entry: entry["score"], reverse=True)
            selected = [entry["item"] for entry in candidates[:enrich_limit]]
            logger.info("Second-pass aspect enrichment selected %s/%s reviews", len(selected), len(pending_reviews))
            for item in selected:
                rid = str(item["review_id"])
                try:
                    enriched, model_used = classify_review_single(item, game_context=game_context)
                    enriched["_label_source"] = "llm_enriched"
                    enriched["_label_model"] = model_used
                    enrichment_provider = str(model_used).split(":", 1)[0] if ":" in str(model_used) else active_name
                    for member in duplicate_members_by_rep.get(rid, [item]):
                        member_id = str(member["review_id"])
                        member_identity = classification_identity(
                            member, game_context, provider=enrichment_provider, model_id=model_used,
                            prompt_version=f"{active_prompt_version}:enriched", mode="single_enrichment",
                            processed_text=(member.get("review_text") if preprocess_mode == "active" else None),
                            preprocessor_version=(review_preprocessor.PREPROCESSOR_VERSION if preprocess_mode == "active" else None),
                        )
                        results[member_id] = {**enriched, "_resolution_source": "generated"}
                        storage.upsert_review_label(
                            app_id,
                            member_id,
                            str(member["review_hash"]),
                            enriched,
                            model_used,
                            f"{active_prompt_version}:enriched",
                            label_origin="llm", validated=True,
                            taxonomy_version=TAXONOMY_VERSION,
                            provider=enrichment_provider, model_id=model_used,
                            classification_input_hash=member_identity["classification_input_hash"],
                            was_truncated=member_identity["was_truncated"],
                            original_char_count=member_identity["original_char_count"],
                            processed_char_count=member_identity["processed_char_count"],
                            generated_at=datetime.now(timezone.utc),
                        )
                except Exception as exc:
                    logger.warning("Aspect enrichment failed for review %s: %s", rid, exc)

    if progress_callback is not None and processed_count < total_reviews:
        progress_callback(total_reviews, total_reviews)

    return results


def estimate_review_labeling(
    app_id: int,
    reviews: Sequence[Mapping[str, Any]],
    *,
    force_refresh: bool = False,
    cache_enabled: bool = True,
) -> Dict[str, Any]:
    """Estimate how many reviews will require LLM calls vs cache/rules.

    This mirrors the cache/refresh logic from `ensure_review_labels` but never calls an LLM.
    """
    from .providers.config import get_active_provider
    active_name, active_model = get_active_provider()
    active_prompt_version = _active_classifier_prompt_version()

    if not reviews:
        return {
            "total_reviews": 0,
            "cached_reviews": 0,
            "needs_refresh_reviews": 0,
            "empty_reviews": 0,
            "short_reviews": 0,
            "short_text_reviews": 0,
            "llm_reviews": 0,
            "reasons": {},
            "prompt_version": active_prompt_version,
            "model_id": "",
            "labeling_strategy": active_name or "unknown",
        }

    existing = storage.load_review_labels(app_id) if cache_enabled else {}
    current_model_id = _model_id(active_name, active_model) if active_name and active_model else None

    counts = {
        "total_reviews": len(reviews),
        "cached_reviews": 0,
        "needs_refresh_reviews": 0,
        "empty_reviews": 0,
        "short_reviews": 0,
        "short_text_reviews": 0,
        "llm_reviews": 0,
    }
    reasons: Dict[str, int] = {}

    for review in reviews:
        review_id_value = review.get("recommendationid") or review.get("review_id")
        if review_id_value is None:
            reasons["missing_review_id"] = reasons.get("missing_review_id", 0) + 1
            continue

        review_id = str(review_id_value)
        review_text = (review.get("review") or "").strip()
        identity = classification_identity(
            review, None, provider=active_name, model_id=current_model_id,
            prompt_version=active_prompt_version,
        )

        cached = existing.get(review_id)
        needs_refresh = force_refresh or cached is None or not label_cache_eligible(cached or {}, identity)
        if cached is None:
            reasons["missing_label"] = reasons.get("missing_label", 0) + 1
        elif not label_cache_eligible(cached, identity):
            reasons["identity_mismatch"] = reasons.get("identity_mismatch", 0) + 1

        if not needs_refresh:
            counts["cached_reviews"] += 1
            continue

        counts["needs_refresh_reviews"] += 1

        if not review_text:
            counts["empty_reviews"] += 1
            continue

        if len(review_text) <= 30:
            counts["short_reviews"] += 1
            counts["short_text_reviews"] += 1

        counts["llm_reviews"] += 1

    return {
        **counts,
        "reasons": reasons,
        "prompt_version": active_prompt_version,
        "model_id": _model_id(active_name, active_model) if active_name and active_model else "",
        "labeling_strategy": active_name or "unknown",
    }


def apply_review_labels(df: pd.DataFrame, labels: Mapping[str, Mapping[str, Any]]) -> pd.DataFrame:
    if df is None:
        return df

    df_labeled = df.copy()
    if df_labeled.empty:
        df_labeled["llm_main_category"] = pd.Series(dtype="object")
        df_labeled["llm_subcategory"] = pd.Series(dtype="object")
        df_labeled["llm_subcategories"] = pd.Series(dtype="object")
        df_labeled["llm_issue_subcategories"] = pd.Series(dtype="object")
        df_labeled["llm_request_subcategories"] = pd.Series(dtype="object")
        df_labeled["llm_subcategory_evidence"] = pd.Series(dtype="object")
        df_labeled["llm_has_issue"] = pd.Series(dtype="bool")
        df_labeled["llm_has_request"] = pd.Series(dtype="bool")
        df_labeled["llm_label_origin"] = pd.Series(dtype="object")
        df_labeled["llm_validated"] = pd.Series(dtype="bool")
        df_labeled["llm_has_aspects"] = pd.Series(dtype="bool")
        return df_labeled

    key_series = df_labeled["review_id"].astype(str)

    def _get_value(review_id: str, key: str, default: Any) -> Any:
        entry = labels.get(review_id)
        if not entry:
            return default
        # Unwrap nested storage format from load_review_labels():
        # {"model": ..., "payload": {actual label data}}
        payload = entry
        if "model" in entry and isinstance(entry.get("payload"), dict):
            payload = entry["payload"]
        value = payload.get(key, default)
        if key in ("subcategories", "issue_subcategories", "request_subcategories"):
            if isinstance(value, list):
                return list(value)
            return default
        if key == "evidence":
            return value if isinstance(value, dict) else default
        return default if value is None else value

    def _get_entry(review_id: str) -> Mapping[str, Any]:
        entry = labels.get(review_id)
        return entry if isinstance(entry, Mapping) else {}

    df_labeled["llm_main_category"] = key_series.map(lambda rid: _get_value(rid, "main_category", "other"))
    df_labeled["llm_subcategory"] = key_series.map(lambda rid: _get_value(rid, "subcategory", "general"))
    df_labeled["llm_subcategories"] = key_series.map(lambda rid: _get_value(rid, "subcategories", []))
    df_labeled["llm_issue_subcategories"] = key_series.map(lambda rid: _get_value(rid, "issue_subcategories", []))
    df_labeled["llm_request_subcategories"] = key_series.map(lambda rid: _get_value(rid, "request_subcategories", []))
    df_labeled["llm_subcategory_evidence"] = key_series.map(lambda rid: _get_value(rid, "evidence", {}))
    df_labeled["llm_has_issue"] = df_labeled["llm_issue_subcategories"].apply(
        lambda value: isinstance(value, list) and len(value) > 0
    )
    df_labeled["llm_has_request"] = df_labeled["llm_request_subcategories"].apply(
        lambda value: isinstance(value, list) and len(value) > 0
    )
    df_labeled["llm_label_origin"] = key_series.map(
        lambda rid: _get_entry(rid).get("label_origin")
    )
    df_labeled["llm_validated"] = key_series.map(
        lambda rid: _get_entry(rid).get("validated") is True
    )
    df_labeled["llm_has_aspects"] = key_series.map(
        lambda rid: bool((_get_value(rid, "aspects", []) or []))
    )

    return df_labeled


_SUMMARIZE_ISSUES_PROMPT = Template(
    dedent(
        """You are analyzing Steam game reviews to identify and categorize TOP ISSUES reported by players.

        GAME CONTEXT:
        Name: $game_name
        Type: $game_type
        Genres: $game_genres
        Description: $game_description

        SUMMARY SCOPE / FILTERS:
        $summary_context

        ISSUE CATEGORY: $subcategory
        TOTAL REVIEWS WITH THIS ISSUE: $review_count

        OUTPUT JSON SCHEMA (use these exact keys; no extras):
        {
          "summary": "<2-3 sentence overview of the core issue and its impact on players>",
          "pros": [],
          "cons": ["<specific issue #1>", "<specific issue #2>", "..."]
        }

        RULES FOR ISSUE ANALYSIS:
        - summary: Describe the PROBLEM clearly - what's broken, what's frustrating players, how widespread it is
        - pros: ALWAYS empty list for issues (we're focusing on problems, not positives)
        - cons: List 3-7 SPECIFIC, ACTIONABLE issues as a prioritized list:
          * Start each with a clear problem statement (e.g., "Game crashes on startup", "Matchmaking takes 10+ minutes")
          * Include frequency/severity if mentioned ("affects 30% of players", "game-breaking", "minor annoyance")
          * Be concrete and developer-actionable, not vague
          * Order by severity/frequency (most critical first)
        - Extract direct player quotes where impactful
        - Focus on technical specifics: error messages, reproduction steps, affected hardware/platforms
        - Distinguish between bug reports vs. design complaints
        - Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".

        REVIEWS (players reporting this issue):
        <<<BEGIN REVIEWS>>>
        $reviews_text
        <<<END REVIEWS>>>
        """
    )
)

_SUMMARIZE_REQUESTS_PROMPT = Template(
    dedent(
        """You are analyzing Steam game reviews to identify and prioritize TOP FEATURE REQUESTS from players.

        GAME CONTEXT:
        Name: $game_name
        Type: $game_type
        Genres: $game_genres
        Description: $game_description

        SUMMARY SCOPE / FILTERS:
        $summary_context

        REQUEST CATEGORY: $subcategory
        TOTAL REVIEWS REQUESTING THIS: $review_count

        OUTPUT JSON SCHEMA (use these exact keys; no extras):
        {
          "summary": "<2-3 sentence overview of what players want and why it matters>",
          "pros": ["<request #1>", "<request #2>", "..."],
          "cons": []
        }

        RULES FOR FEATURE REQUEST ANALYSIS:
        - summary: Describe WHAT players want, WHY they want it, and the expected benefit/impact
        - pros: List 3-7 SPECIFIC, ACTIONABLE feature requests as a prioritized list:
          * Start each with a clear request (e.g., "Add FOV slider", "Implement cross-platform play")
          * Include player motivation/use case (e.g., "for motion sickness", "to play with console friends")
          * Mention demand level if clear ("highly requested", "mentioned by veterans", "quality of life improvement")
          * Order by demand/impact (most requested/impactful first)
        - cons: ALWAYS empty list for requests (we're focusing on wants, not problems)
        - Be specific about the requested feature - HOW players want it implemented when mentioned
        - Distinguish between "nice to have" vs. "deal-breaker" requests
        - Note any common alternatives or workarounds players suggest
        - Group similar requests (e.g., multiple UI customization requests)
        - Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".

        REVIEWS (players requesting this feature):
        <<<BEGIN REVIEWS>>>
        $reviews_text
        <<<END REVIEWS>>>
        """
    )
)

_SUMMARIZE_PROMPT_TEMPLATE = Template(
    dedent(
        """You are analyzing Steam game reviews for a specific subcategory. Generate a concise, actionable summary.

        GAME CONTEXT:
        Name: $game_name
        Type: $game_type
        Genres: $game_genres
        Description: $game_description

        SUMMARY SCOPE / FILTERS:
        $summary_context

        SUBCATEGORY: $subcategory
        TOTAL REVIEWS IN CATEGORY: $review_count

        OUTPUT JSON SCHEMA (use these exact keys; no extras):
        {
          "summary": "<2-4 sentence overview of what players are saying about this aspect>",
          "pros": ["<positive point 1>", "<positive point 2>", "..."],
          "cons": ["<negative point 1>", "<negative point 2>", "..."]
        }

        RULES:
        - summary: A concise 2-4 sentence overview capturing recommendation (thumbs up/down) and key points
        - pros: 2-5 specific positive aspects mentioned by players (empty list if none)
        - cons: 2-5 specific issues or complaints mentioned by players (empty list if none)
        - Be specific and actionable, not generic
        - Use player language where appropriate
        - Focus on patterns across multiple reviews, not single opinions
        - Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
        - JSON MUST be valid: double quotes only, no trailing commas

        REVIEWS (sample from this subcategory):
        <<<BEGIN REVIEWS>>>
        $reviews_text
        <<<END REVIEWS>>>
        """
    )
)

_SUMMARIZE_WIDGET_GENERIC_PROMPT = Template(
    dedent(
        """You are analyzing a set of Steam game reviews shown in a dashboard widget. These reviews are a SAMPLE from the UI (not necessarily the full dataset).

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

WIDGET:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Issue-tagged reviews: $issue_rate
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence overview grounded in the provided reviews>",
  "key_points": ["<key point 1>", "<key point 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Use only the provided context + reviews. If something is unknown, say it's unknown.
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- key_points: 3-6 concise bullets, grounded in repeated patterns across reviews.
- actions: EXACTLY 3 prioritized, developer-actionable actions (start each with a verb).
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_SUMMARIZE_WIDGET_TREND_WEEK_PROMPT = Template(
    dedent(
        """You are analyzing Steam reviews for one game during a specific week. These reviews are a SAMPLE shown in the dashboard widget.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

WEEK:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Issue-tagged reviews: $issue_rate
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence weekly recap grounded in the provided reviews>",
  "key_points": ["<key point 1>", "<key point 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Treat this as a weekly snapshot: focus on what was top-of-mind for players that week.
- Highlight any recurring breakages/regressions and the most demanded fixes.
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- key_points: 3-6 bullets; include at least 1 player-facing positive if present.
- actions: EXACTLY 3 prioritized actions (start each with a verb). If evidence is insufficient, propose safe next steps (instrument, reproduce, clarify).
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_SUMMARIZE_WIDGET_SEGMENT_PROMPT = Template(
    dedent(
        """You are analyzing Steam reviews for one game written by a specific player segment (e.g., veterans, Steam Deck players, key users, a specific language).
These reviews are a SAMPLE shown in the dashboard widget.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

SEGMENT:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Issue-tagged reviews: $issue_rate
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence summary of what this segment cares about>",
  "key_points": ["<key point 1>", "<key point 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Explain what this segment disproportionately notices (pain points, expectations, requests).
- If baseline metrics are provided in widget_context, call out meaningful differences (avoid made-up numbers).
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- key_points: 3-6 bullets, grounded in review evidence.
- actions: EXACTLY 3 prioritized actions (start each with a verb).
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_SUMMARIZE_WIDGET_LANGUAGE_PROMPT = Template(
    dedent(
        """You are analyzing Steam reviews for one game written in a specific language (regional segment). These reviews are a SAMPLE shown in the dashboard widget.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

LANGUAGE SEGMENT:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Issue-tagged reviews: $issue_rate
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES:
$top_issues

TOP TAGGED REQUESTS:
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence summary of what this language segment is saying>",
  "key_points": ["<key point 1>", "<key point 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Pay attention to localization/regional issues: translation quality, UI strings, cultural references, region-specific pricing, servers, input layouts, legality/compliance, etc (only if present in reviews).
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- key_points: 3-6 bullets grounded in evidence; avoid generalizations about a region.
- actions: EXACTLY 3 prioritized actions (start each with a verb).
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_SUMMARIZE_WIDGET_RECENT_REVIEWS_PROMPT = Template(
    dedent(
        """You are analyzing the MOST RECENT Steam reviews for one game. These reviews represent the latest feedback window and should be treated as a "what's happening now" snapshot.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

RECENT WINDOW:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Issue-tagged reviews: $issue_rate
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence recap of the most recent player feedback>",
  "key_points": ["<key point 1>", "<key point 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Focus on NEW/EMERGING themes, regressions, and "top-of-mind" issues/requests in this recent window.
- If baseline metrics are provided in widget_context, call out meaningful differences (do not invent numbers).
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- key_points: 3-6 bullets grounded in repeated patterns across reviews.
- actions: EXACTLY 3 prioritized, developer-actionable actions (start each with a verb).
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_HEALTH_OVERVIEW_PROMPT = Template(
    dedent(
        """\
You are generating a HEALTH OVERVIEW CARD for a Steam game dashboard. This is a persistent summary that gives developers an at-a-glance view of their game's current reception.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

REVIEW WINDOW:
$widget_label

OUTPUT LANGUAGE:
$output_language

BASELINE (previous analysis snapshot to compare against):
$baseline_context

SUBSET METRICS (computed from provided reviews):
- Reviews: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Issue-tagged reviews: $issue_rate
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence executive recap of overall game health>",
  "key_points": ["<key observation 1>", "<key observation 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"],
  "health_score": <integer 1-10>,
  "sentiment_trend": "<improving|stable|declining>",
  "top_strengths": ["<strength 1>", "<strength 2>", "<strength 3>"]
}

RULES:
- Write all human-readable fields (summary, key_points, actions, and top_strengths) in the requested output language. Use Simplified Chinese for zh, English for en, and Japanese for ja. Keep sentiment_trend as the required English enum value.
- health_score: 1-10 integer. Consider recommendation rate, issue severity, and overall tone. 8-10 = healthy, 5-7 = mixed, 1-4 = concerning.
- sentiment_trend: "improving" if current metrics are better than the baseline snapshot, "declining" if worse, "stable" if similar or no baseline available. Only compare when a dated baseline is provided.
- top_strengths: Exactly 3 things players praise most (gameplay, visuals, value, etc.). Grounded in review evidence.
- key_points: 3-6 bullets covering the most important observations (issues, patterns, notable feedback).
- actions: EXACTLY 3 prioritized, developer-actionable recommendations (start each with a verb).
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_SUMMARIZE_WIDGET_TOP_ISSUES_PROMPT = Template(
    dedent(
        """\
You are analyzing the TOP REPORTED ISSUES across all categories for a Steam game.
These are the most frequently mentioned problems, aggregated across multiple review subcategories.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

TOP ISSUES OVERVIEW:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews with issues: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Issue-tagged reviews: $issue_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence executive overview of the most critical player issues>",
  "key_points": ["<key issue pattern 1>", "<key issue pattern 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Focus on cross-cutting PATTERNS: what are the biggest pain points across categories?
- Prioritize by severity and frequency — most impactful issues first.
- Distinguish between bugs (fixable) and design complaints (debatable).
- key_points: 3-6 bullets summarizing the main issue themes, grounded in review evidence.
- actions: EXACTLY 3 prioritized, developer-actionable fixes (start each with a verb).
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_SUMMARIZE_WIDGET_TOP_REQUESTS_PROMPT = Template(
    dedent(
        """\
You are analyzing the TOP FEATURE REQUESTS across all categories for a Steam game.
These are the most frequently requested improvements, aggregated across multiple review subcategories.

GAME CONTEXT:
Name: $game_name
Type: $game_type
Genres: $game_genres
Description: $game_description

TOP REQUESTS OVERVIEW:
$widget_label

WIDGET CONTEXT (structured):
$widget_context

SUBSET METRICS (computed from provided reviews):
- Reviews with requests: $review_count
- Recommendation rate (thumbs up): $recommendation_rate
- Avg helpful votes: $avg_helpful
- Languages (top): $language_mix
- Request-tagged reviews: $request_rate

TOP TAGGED ISSUES (count of reviews mentioning the issue):
$top_issues

TOP TAGGED REQUESTS (count of reviews mentioning the request):
$top_requests

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-4 sentence overview of what players want most and why it matters>",
  "key_points": ["<top request theme 1>", "<top request theme 2>", "..."],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Focus on cross-cutting DEMAND patterns: what do players want most across all categories?
- Prioritize by demand level and potential impact on player satisfaction.
- Distinguish between "nice to have" quality-of-life changes and "deal-breaker" missing features.
- key_points: 3-6 bullets summarizing the main request themes, grounded in review evidence.
- actions: EXACTLY 3 prioritized, developer-actionable improvements (start each with a verb).
- Avoid the word "sentiment". Use "recommendation rate" or "thumbs up/down".
- JSON MUST be valid: double quotes only, no trailing commas.

REVIEWS:
<<<BEGIN REVIEWS>>>
$reviews_text
<<<END REVIEWS>>>
"""
    )
)

_REPORT_SUMMARY_PROMPT = Template(
    dedent(
        """You are a product insights analyst. Summarize the monthly Steam review data into a concise executive brief.

GAME: $game_name
PERIOD: $period

CORE METRICS:
- Total reviews: $total_reviews
- Recommendation rate: $recommendation_rate
$comparison_text

TOP ISSUES:
$top_issues

TOP REQUESTS:
$top_requests

OUTPUT LANGUAGE:
$output_language

OUTPUT JSON SCHEMA (use these exact keys; no extras):
{
  "summary": "<2-3 sentence executive summary of the month>",
  "key_points": ["<key insight 1>", "<key insight 2>", "<key insight 3>"],
  "actions": ["<action 1>", "<action 2>", "<action 3>"]
}

RULES:
- Write summary, key_points, and actions in the requested output language: Simplified Chinese for zh, English for en, Japanese for ja.
- summary: Short overview (2-3 sentences) covering recommendation rate, main issue, and main request.
- key_points: 3 bullet-style insights from the data (what's working, what's broken, what players want).
- actions: 3 specific, developer-actionable recommendations ordered by priority.
- If month-over-month comparison provided, mention significant changes (>5% delta).
- Use only data provided; do not invent facts.
- Never use the word "sentiment". Say "recommendation rate" or "thumbs up/down".
- JSON MUST be valid: double quotes only, no trailing commas.
"""
    )
)


def summarize_monthly_report(
    *,
    game_name: str,
    period: str,
    insights: Mapping[str, Any],
    output_language: str = "zh",
) -> Dict[str, Any]:
    """Generate a concise executive summary for a monthly report.

    Returns dict with 'summary', 'key_points', and 'actions' keys.
    """
    if not insights:
        return {
            "summary": "Not enough data to summarize this period.",
            "key_points": [],
            "actions": [],
        }

    def _format_label(value: Any) -> str:
        text = str(value or "").replace("_", " ").replace("/", " / ").strip()
        return text.title() if text else "Unknown"

    def _format_issue_list(items: Any, limit: int = 3) -> str:
        if not isinstance(items, list) or not items:
            return "No clear issues identified."
        lines = []
        for item in items[:limit]:
            name = _format_label(item.get("subcategory"))
            count = int(item.get("count") or 0)
            rec_rate = item.get("recommendation_rate")
            rec_text = f"{rec_rate:.1%} rec" if isinstance(rec_rate, (int, float)) else "rec n/a"
            snippet = ""
            snippets = item.get("snippets") or []
            if isinstance(snippets, list) and snippets:
                snippet_text = str(snippets[0]).replace("\n", " ").strip()
                if snippet_text:
                    snippet = f" Example: \"{snippet_text[:120]}\""
            lines.append(f"- {name}: {count} mentions ({rec_text}).{snippet}")
        return "\n".join(lines)

    total_reviews = int(insights.get("total_reviews") or 0)
    recommendation_rate = float(insights.get("recommendation_rate") or 0.0)

    # Build comparison text if previous month data available
    comparison_text = ""
    previous = insights.get("previous")
    deltas = insights.get("deltas")
    if previous and deltas:
        prev_period = previous.get("period", "previous month")
        prev_reviews = previous.get("total_reviews", 0)
        delta_reviews = deltas.get("reviews", 0)
        delta_rec = deltas.get("recommendation_rate", 0.0)

        comparison_lines = [f"\nCOMPARISON WITH {prev_period.upper()}:"]
        review_change = "+" if delta_reviews >= 0 else ""
        comparison_lines.append(f"- Review volume: {review_change}{delta_reviews:,} ({prev_reviews:,} → {total_reviews:,})")
        rec_change = "+" if delta_rec >= 0 else ""
        comparison_lines.append(f"- Recommendation rate: {rec_change}{delta_rec:.1%} ({previous.get('recommendation_rate', 0):.1%} → {recommendation_rate:.1%})")
        comparison_text = "\n".join(comparison_lines)

    prompt = _REPORT_SUMMARY_PROMPT.substitute(
        game_name=game_name or "Unknown",
        period=period or "Unknown",
        total_reviews=f"{total_reviews:,}",
        recommendation_rate=f"{recommendation_rate:.1%}",
        comparison_text=comparison_text,
        top_issues=_format_issue_list(insights.get("top_issues")),
        top_requests=_format_issue_list(insights.get("top_requests")),
        output_language={"zh": "Simplified Chinese", "ja": "Japanese", "en": "English"}.get((output_language or "zh").lower(), "Simplified Chinese"),
    )

    try:
        raw, _model_used = _run_llm(prompt, response_schema=ReportSummary)
        parsed = ReportSummary.model_validate_json(raw)
        summary = parsed.summary.strip() or "Unable to generate summary."
        key_points = [s.strip() for s in parsed.key_points if s][:3]
        actions = [s.strip() for s in parsed.actions if s][:3]

        return {
            "summary": summary,
            "key_points": key_points,
            "actions": actions,
        }
    except Exception as exc:
        logger.error("Failed to generate monthly report summary: %s", exc)
        return {
            "summary": "Unable to generate summary.",
            "key_points": [],
            "actions": [],
        }


def summarize_subcategory_reviews(
    reviews: Sequence[Mapping[str, Any]],
    subcategory: str,
    game_context: Optional[Dict[str, Any]] = None,
    summary_type: str = "general",
    summary_context: Optional[str] = None,
    output_language: str = "zh",
) -> Dict[str, Any]:
    """Generate a summary with pros/cons for reviews in a subcategory.

    Args:
        reviews: List of review dicts with 'review' text field
        subcategory: The subcategory being summarized (e.g., "technical/performance")
        game_context: Optional game details (name, genres, etc.)
        summary_type: Type of summary - "issue", "request", or "general"

    Returns:
        Dict with 'summary', 'pros', 'cons' keys
    """
    output_language = (output_language or "zh").strip().lower()
    if output_language not in {"zh", "en", "ja"}:
        output_language = "zh"

    if not reviews:
        return {
            "summary": "该细分板块暂无可用评论。" if output_language == "zh" else "No reviews available for this subcategory.",
            "pros": [],
            "cons": [],
        }

    # Build game context strings
    if game_context:
        game_name = game_context.get("name", "Unknown")
        game_type = game_context.get("type", "game")
        genres = game_context.get("genres", [])
        description = game_context.get("short_description", "")[:200]

        game_genres = ", ".join(genres) if genres else "Unknown"
        game_description = description if description else "Not available"
    else:
        game_name = "Unknown"
        game_type = "game"
        game_genres = "Unknown"
        game_description = "Not available"

    def _clean_snippet(value: Any, max_len: int = 160) -> Optional[str]:
        text = str(value).replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return None
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def _extract_evidence_snippets(review: Mapping[str, Any], target_subcategory: str, max_snippets: int = 2) -> list[str]:
        evidence = review.get("llm_subcategory_evidence") or review.get("subcategory_evidence") or {}
        if not isinstance(evidence, dict):
            return []
        evidence_map = {
            str(key).lower(): value
            for key, value in evidence.items()
            if isinstance(key, str)
        }
        values = evidence_map.get(target_subcategory.lower())
        if values is None:
            return []
        if isinstance(values, list):
            raw_items = values
        else:
            raw_items = [values]
        snippets: list[str] = []
        for item in raw_items:
            cleaned = _clean_snippet(item)
            if cleaned and cleaned not in snippets:
                snippets.append(cleaned)
            if len(snippets) >= max_snippets:
                break
        return snippets

    # Hybrid: evidence snippets for coverage + a few full reviews for nuance
    max_reviews = min(50, len(reviews))
    sampled_reviews = reviews[:max_reviews]
    full_review_limit = min(10, max_reviews)

    evidence_blocks: list[str] = []
    full_review_blocks: list[str] = []

    for i, review in enumerate(sampled_reviews, 1):
        voted_up = review.get("voted_up", True)
        sentiment = "Positive" if voted_up else "Negative"

        snippets = _extract_evidence_snippets(review, subcategory, max_snippets=2)
        if snippets:
            evidence_blocks.append(f"[Review {i}] ({sentiment}) " + " | ".join(snippets))

        if i <= full_review_limit:
            text = (review.get("review") or "").strip()
            if text:
                if len(text) > 500:
                    text = text[:500] + "..."
                full_review_blocks.append(f"[Review {i}] ({sentiment})\n{text}")

    sections: list[str] = []
    if evidence_blocks:
        sections.append("EVIDENCE SNIPPETS (extracted highlights):\n" + "\n".join(evidence_blocks))
    if full_review_blocks:
        sections.append("FULL REVIEW EXAMPLES (top helpful):\n" + "\n\n".join(full_review_blocks))

    reviews_text = "\n\n".join(sections)
    if not reviews_text.strip():
        return {
            "summary": "该细分板块暂无可分析的评论文本。" if output_language == "zh" else "No review text available for this subcategory.",
            "pros": [],
            "cons": [],
        }

    # Select prompt template based on summary type
    if summary_type == "issue":
        prompt_template = _SUMMARIZE_ISSUES_PROMPT
    elif summary_type == "request":
        prompt_template = _SUMMARIZE_REQUESTS_PROMPT
    else:
        prompt_template = _SUMMARIZE_PROMPT_TEMPLATE

    prompt = prompt_template.substitute(
        game_name=game_name,
        game_type=game_type,
        game_genres=game_genres,
        game_description=game_description,
        summary_context=(summary_context or "None"),
        subcategory=subcategory,
        review_count=len(reviews),
        reviews_text=reviews_text,
    )
    prompt += (
        f"\n\nOUTPUT LANGUAGE CONTRACT: summary, pros, and cons MUST be written in "
        f"{_summary_language_name(output_language)}. Keep player quotes in their original language. "
        "Return only valid JSON and write all analytical prose in the requested language."
    )

    try:
        raw, _model_used = _run_llm(prompt, response_schema=SubcategorySummary)
        parsed = SubcategorySummary.model_validate_json(raw)
        values = [parsed.summary, *parsed.pros, *parsed.cons]
        if not _looks_like_requested_language(values, output_language):
            repair_prompt = prompt + (
                f"\n\nBOUNDED REPAIR: the previous answer did not follow "
                f"{_summary_language_name(output_language)}. Regenerate once. "
                "Do not translate or rewrite player quotes, but write every analytical field in the requested language."
            )
            repaired_raw, _model_used = _run_llm(repair_prompt, response_schema=SubcategorySummary)
            parsed = SubcategorySummary.model_validate_json(repaired_raw)

        if not _looks_like_requested_language([parsed.summary, *parsed.pros, *parsed.cons], output_language):
            raise ValueError("Provider did not honor the requested summary language.")

        summary = parsed.summary.strip() or ("暂时无法生成摘要。" if output_language == "zh" else "Unable to generate summary.")
        pros = [s.strip() for s in parsed.pros if s][:5]
        cons = [s.strip() for s in parsed.cons if s][:5]

        return {
            "summary": summary,
            "pros": pros,
            "cons": cons,
        }
    except Exception as exc:
        logger.error(f"Failed to summarize reviews: {exc}")
        return {
            "summary": "AI 摘要暂时生成失败，请检查系统设置中的 AI 服务配置后重试。" if output_language == "zh" else "Unable to generate summary.",
            "pros": [],
            "cons": [],
        }


def summarize_widget_reviews(
    reviews: Sequence[Mapping[str, Any]],
    widget_kind: str,
    widget_label: str,
    widget_context: Optional[Mapping[str, Any]] = None,
    game_context: Optional[Dict[str, Any]] = None,
    output_language: str = "zh",
) -> Dict[str, Any]:
    """Summarize review sets shown in different UI widgets (week/segment/etc.).

    Returns a structured summary suitable for displaying inside modal widgets.
    """
    if not reviews:
        return {
            "summary": "No reviews available for this widget.",
            "key_points": [],
            "actions": [],
            "output_language": output_language,
        }

    widget_context = widget_context or {}

    # Build game context strings
    if game_context:
        game_name = game_context.get("name", "Unknown")
        game_type = game_context.get("type", "game")
        genres = game_context.get("genres", [])
        description = game_context.get("short_description", "")[:200]

        game_genres = ", ".join(genres) if genres else "Unknown"
        game_description = description if description else "Not available"
    else:
        game_name = "Unknown"
        game_type = "game"
        game_genres = "Unknown"
        game_description = "Not available"

    def _to_int(value: Any) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                return int(float(value))
        except Exception:
            return 0
        return 0

    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "recommended", "thumbs_up", "up"}
        return False

    def _clean_snippet(value: Any, max_len: int = 160) -> Optional[str]:
        text = str(value).replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return None
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def _listify_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]

    def _extract_any_evidence_snippets(review: Mapping[str, Any], max_snippets: int = 2) -> list[str]:
        evidence = review.get("llm_subcategory_evidence") or review.get("subcategory_evidence") or {}
        if not isinstance(evidence, dict):
            return []

        # Prioritize issue/request subcategories when available, else fall back to evidence keys.
        candidate_keys: list[str] = []
        candidate_keys.extend(_listify_strings(review.get("llm_issue_subcategories")))
        candidate_keys.extend(_listify_strings(review.get("llm_request_subcategories")))
        if not candidate_keys:
            candidate_keys = [str(key) for key in evidence.keys() if isinstance(key, str)]

        snippets: list[str] = []
        for key in candidate_keys:
            raw_values = evidence.get(key)
            if raw_values is None:
                # evidence keys might have different casing
                for ev_key, ev_val in evidence.items():
                    if isinstance(ev_key, str) and ev_key.lower() == str(key).lower():
                        raw_values = ev_val
                        break
            if raw_values is None:
                continue
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            for item in values:
                cleaned = _clean_snippet(item)
                if cleaned and cleaned not in snippets:
                    snippets.append(cleaned)
                if len(snippets) >= max_snippets:
                    return snippets
        return snippets

    # Compute subset metrics
    review_count = len(reviews)
    voted_flags: list[bool] = [_to_bool(r.get("voted_up", False)) for r in reviews]
    rec_rate = (sum(1 for v in voted_flags if v) / review_count) if review_count else 0.0
    avg_helpful = sum(_to_int(r.get("votes_up")) for r in reviews) / review_count if review_count else 0.0

    # Issue/request rate + top tags
    issue_hits = 0
    request_hits = 0
    issue_counter: Counter[str] = Counter()
    request_counter: Counter[str] = Counter()
    for r in reviews:
        issues = _listify_strings(r.get("llm_issue_subcategories"))
        requests = _listify_strings(r.get("llm_request_subcategories"))
        if issues:
            issue_hits += 1
            issue_counter.update(issues)
        if requests:
            request_hits += 1
            request_counter.update(requests)

    issue_rate = issue_hits / review_count if review_count else 0.0
    request_rate = request_hits / review_count if review_count else 0.0

    def _format_top(counter: Counter[str], limit: int = 8) -> str:
        if not counter:
            return "- None"
        lines = []
        for key, count in counter.most_common(limit):
            lines.append(f"- {key}: {count}")
        return "\n".join(lines)

    # Language mix
    lang_counter: Counter[str] = Counter()
    for r in reviews:
        lang = r.get("language")
        if isinstance(lang, str) and lang.strip():
            lang_counter.update([lang.strip().lower()])
    if lang_counter:
        top_langs = [f"{lang} ({count})" for lang, count in lang_counter.most_common(3)]
        language_mix = ", ".join(top_langs)
    else:
        language_mix = "unknown"

    # Build review blocks (evidence snippets + a few full reviews)
    # Keep the prompt compact: prioritize helpful reviews for full examples.
    def _helpful_sort_key(r: Mapping[str, Any]) -> int:
        return _to_int(r.get("votes_up"))

    sorted_by_helpful = sorted(list(reviews), key=_helpful_sort_key, reverse=True)
    sampled_reviews = sorted_by_helpful[: min(50, len(sorted_by_helpful))]
    full_review_limit = min(8, len(sampled_reviews))

    evidence_blocks: list[str] = []
    full_review_blocks: list[str] = []

    for i, review in enumerate(sampled_reviews, 1):
        voted_up = _to_bool(review.get("voted_up", False))
        sentiment = "Recommended" if voted_up else "Not recommended"
        helpful = _to_int(review.get("votes_up"))
        lang = str(review.get("language") or "unknown")
        created = str(review.get("created_at") or "")

        snippets = _extract_any_evidence_snippets(review, max_snippets=2)
        if snippets:
            evidence_blocks.append(f"[Review {i}] ({sentiment}, {helpful} helpful, {lang}, {created}) " + " | ".join(snippets))
        else:
            fallback = _clean_snippet(review.get("review") or "", max_len=160)
            if fallback:
                evidence_blocks.append(f"[Review {i}] ({sentiment}, {helpful} helpful, {lang}, {created}) {fallback}")

        if i <= full_review_limit:
            text = (review.get("review") or "").strip()
            if text:
                if len(text) > 500:
                    text = text[:500] + "..."
                full_review_blocks.append(f"[Review {i}] ({sentiment}, {helpful} helpful, {lang}, {created})\n{text}")

    sections: list[str] = []
    if evidence_blocks:
        sections.append("EVIDENCE SNIPPETS (highlights):\n" + "\n".join(evidence_blocks[:24]))
    if full_review_blocks:
        sections.append("FULL REVIEW EXAMPLES (top helpful):\n" + "\n\n".join(full_review_blocks))

    reviews_text = "\n\n".join(sections)
    if not reviews_text.strip():
        return {
            "summary": "No review text available for this widget.",
            "key_points": [],
            "actions": [],
            "output_language": output_language,
        }

    # Compact context formatting (avoid dumping raw JSON).
    context_lines: list[str] = []
    for key in ("week_range", "segment_type", "segment_key", "segment_criteria", "filters", "query", "baseline", "top_subcategories"):
        value = widget_context.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            try:
                value_text = json.dumps(value, ensure_ascii=True)
            except Exception:
                value_text = str(value)
        else:
            value_text = str(value)
        if value_text.strip():
            context_lines.append(f"- {key}: {value_text.strip()}")
    widget_context_text = "\n".join(context_lines) if context_lines else "- None"

    # Pick a prompt based on widget kind and segment type.
    prompt_template = _SUMMARIZE_WIDGET_GENERIC_PROMPT
    if widget_kind == "recent_reviews":
        prompt_template = _SUMMARIZE_WIDGET_RECENT_REVIEWS_PROMPT
    elif widget_kind == "trend_week":
        prompt_template = _SUMMARIZE_WIDGET_TREND_WEEK_PROMPT
    elif widget_kind == "top_issues":
        prompt_template = _SUMMARIZE_WIDGET_TOP_ISSUES_PROMPT
    elif widget_kind == "top_requests":
        prompt_template = _SUMMARIZE_WIDGET_TOP_REQUESTS_PROMPT
    elif widget_kind == "segment":
        segment_type = str(widget_context.get("segment_type") or "").strip().lower()
        if segment_type == "language":
            prompt_template = _SUMMARIZE_WIDGET_LANGUAGE_PROMPT
        else:
            prompt_template = _SUMMARIZE_WIDGET_SEGMENT_PROMPT

    prompt = prompt_template.substitute(
        game_name=game_name,
        game_type=game_type,
        game_genres=game_genres,
        game_description=game_description,
        widget_label=widget_label,
        widget_context=widget_context_text,
        review_count=f"{review_count:,}",
        recommendation_rate=f"{rec_rate:.1%}",
        avg_helpful=f"{avg_helpful:.1f}",
        language_mix=language_mix,
        issue_rate=f"{issue_rate:.1%}",
        request_rate=f"{request_rate:.1%}",
        top_issues=_format_top(issue_counter),
        top_requests=_format_top(request_counter),
        reviews_text=reviews_text,
    )
    prompt += f"\n\nOUTPUT LANGUAGE CONTRACT: summary, key_points, and actions MUST be written in {_summary_language_name(output_language)}. Keep player quotes in their original language. Return output_language as '{output_language}'."

    try:
        raw, _model_used = _run_llm(prompt, response_schema=ReportSummary)
        parsed = ReportSummary.model_validate_json(raw)
        values = [parsed.summary, *parsed.key_points, *parsed.actions]
        if not _looks_like_requested_language(values, output_language):
            repair_prompt = prompt + f"\n\nBOUNDED REPAIR: the previous answer did not follow {_summary_language_name(output_language)}. Regenerate once, using only the requested language for analytical prose."
            repaired_raw, _model_used = _run_llm(repair_prompt, response_schema=ReportSummary)
            parsed = ReportSummary.model_validate_json(repaired_raw)
        summary = parsed.summary.strip() or "Unable to generate summary."
        key_points = [s.strip() for s in parsed.key_points if s][:6]
        actions = [s.strip() for s in parsed.actions if s][:3]

        return {
            "summary": summary,
            "key_points": key_points,
            "actions": actions,
            "output_language": output_language,
        }
    except Exception as exc:
        logger.error("Failed to summarize widget reviews: %s", exc)
        return {
            "summary": "Unable to generate summary.",
            "key_points": [],
            "actions": [],
            "output_language": output_language,
        }


def generate_health_overview(
    reviews: Sequence[Mapping[str, Any]],
    game_context: Optional[Dict[str, Any]] = None,
    baseline: Optional[Dict[str, Any]] = None,
    widget_context: Optional[Mapping[str, Any]] = None,
    output_language: str = "zh",
) -> Dict[str, Any]:
    """Generate a persistent health overview card for the dashboard.

    Reuses the same review preprocessing as summarize_widget_reviews() but
    produces an extended schema with health_score, sentiment_trend, and
    top_strengths in addition to the standard summary/key_points/actions.
    """
    if not reviews:
        return {
            "summary": "No reviews available to generate health overview.",
            "key_points": [],
            "actions": [],
            "health_score": 5,
            "sentiment_trend": "stable",
            "top_strengths": [],
        }

    widget_context = widget_context or {}

    # Build game context strings
    if game_context:
        game_name = game_context.get("name", "Unknown")
        game_type = game_context.get("type", "game")
        genres = game_context.get("genres", [])
        description = game_context.get("short_description", "")[:200]
        game_genres = ", ".join(genres) if genres else "Unknown"
        game_description = description if description else "Not available"
    else:
        game_name = "Unknown"
        game_type = "game"
        game_genres = "Unknown"
        game_description = "Not available"

    def _to_int(value: Any) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            if isinstance(value, str):
                return int(float(value))
        except Exception:
            return 0
        return 0

    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "recommended", "thumbs_up", "up"}
        return False

    def _clean_snippet(value: Any, max_len: int = 160) -> Optional[str]:
        text = str(value).replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return None
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def _listify_strings(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]

    # Compute subset metrics
    review_count = len(reviews)
    voted_flags: list[bool] = [_to_bool(r.get("voted_up", False)) for r in reviews]
    rec_rate = (sum(1 for v in voted_flags if v) / review_count) if review_count else 0.0
    avg_helpful = sum(_to_int(r.get("votes_up")) for r in reviews) / review_count if review_count else 0.0

    # Issue/request rate + top tags
    issue_hits = 0
    request_hits = 0
    issue_counter: Counter[str] = Counter()
    request_counter: Counter[str] = Counter()
    for r in reviews:
        issues = _listify_strings(r.get("llm_issue_subcategories"))
        requests = _listify_strings(r.get("llm_request_subcategories"))
        if issues:
            issue_hits += 1
            issue_counter.update(issues)
        if requests:
            request_hits += 1
            request_counter.update(requests)

    issue_rate = issue_hits / review_count if review_count else 0.0
    request_rate = request_hits / review_count if review_count else 0.0

    def _format_top(counter: Counter[str], limit: int = 8) -> str:
        if not counter:
            return "- None"
        lines = []
        for key, count in counter.most_common(limit):
            lines.append(f"- {key}: {count}")
        return "\n".join(lines)

    # Language mix
    lang_counter: Counter[str] = Counter()
    for r in reviews:
        lang = r.get("language")
        if isinstance(lang, str) and lang.strip():
            lang_counter.update([lang.strip().lower()])
    if lang_counter:
        top_langs = [f"{lang} ({count})" for lang, count in lang_counter.most_common(3)]
        language_mix = ", ".join(top_langs)
    else:
        language_mix = "unknown"

    # Build review blocks (same approach as summarize_widget_reviews)
    def _helpful_sort_key(r: Mapping[str, Any]) -> int:
        return _to_int(r.get("votes_up"))

    sorted_by_helpful = sorted(list(reviews), key=_helpful_sort_key, reverse=True)
    sampled_reviews = sorted_by_helpful[: min(50, len(sorted_by_helpful))]
    full_review_limit = min(8, len(sampled_reviews))

    evidence_blocks: list[str] = []
    full_review_blocks: list[str] = []

    for i, review in enumerate(sampled_reviews, 1):
        voted_up = _to_bool(review.get("voted_up", False))
        sentiment = "Recommended" if voted_up else "Not recommended"
        helpful = _to_int(review.get("votes_up"))
        lang = str(review.get("language") or "unknown")
        created = str(review.get("created_at") or "")

        # Evidence snippets
        evidence = review.get("llm_subcategory_evidence") or review.get("subcategory_evidence") or {}
        snippets: list[str] = []
        if isinstance(evidence, dict):
            for key in list(evidence.keys())[:3]:
                raw_values = evidence[key]
                values = raw_values if isinstance(raw_values, list) else [raw_values]
                for item in values:
                    cleaned = _clean_snippet(item)
                    if cleaned and cleaned not in snippets:
                        snippets.append(cleaned)
                    if len(snippets) >= 2:
                        break
                if len(snippets) >= 2:
                    break

        if snippets:
            evidence_blocks.append(f"[Review {i}] ({sentiment}, {helpful} helpful, {lang}, {created}) " + " | ".join(snippets))
        else:
            fallback = _clean_snippet(review.get("review") or "", max_len=160)
            if fallback:
                evidence_blocks.append(f"[Review {i}] ({sentiment}, {helpful} helpful, {lang}, {created}) {fallback}")

        if i <= full_review_limit:
            text = (review.get("review") or "").strip()
            if text:
                if len(text) > 500:
                    text = text[:500] + "..."
                full_review_blocks.append(f"[Review {i}] ({sentiment}, {helpful} helpful, {lang}, {created})\n{text}")

    sections: list[str] = []
    if evidence_blocks:
        sections.append("EVIDENCE SNIPPETS (highlights):\n" + "\n".join(evidence_blocks[:24]))
    if full_review_blocks:
        sections.append("FULL REVIEW EXAMPLES (top helpful):\n" + "\n\n".join(full_review_blocks))

    reviews_text = "\n\n".join(sections)
    if not reviews_text.strip():
        return {
            "summary": "No review text available.",
            "key_points": [],
            "actions": [],
            "health_score": 5,
            "sentiment_trend": "stable",
            "top_strengths": [],
        }

    # Format baseline context with explicit date
    if baseline:
        baseline_date = baseline.get("date") or "unknown date"
        baseline_lines = [f"Previous analysis from {baseline_date}:"]
        for key, value in baseline.items():
            if key != "date" and value is not None:
                baseline_lines.append(f"- {key}: {value}")
        baseline_context = "\n".join(baseline_lines)
    else:
        baseline_context = "No previous analysis available (first run). Set sentiment_trend to \"stable\"."

    prompt = _HEALTH_OVERVIEW_PROMPT.substitute(
        game_name=game_name,
        game_type=game_type,
        game_genres=game_genres,
        game_description=game_description,
        widget_label=f"All {review_count} analyzed reviews",
        output_language={"zh": "Simplified Chinese", "ja": "Japanese", "en": "English"}.get((output_language or "zh").lower(), "Simplified Chinese"),
        baseline_context=baseline_context,
        review_count=f"{review_count:,}",
        recommendation_rate=f"{rec_rate:.1%}",
        avg_helpful=f"{avg_helpful:.1f}",
        language_mix=language_mix,
        issue_rate=f"{issue_rate:.1%}",
        request_rate=f"{request_rate:.1%}",
        top_issues=_format_top(issue_counter),
        top_requests=_format_top(request_counter),
        reviews_text=reviews_text,
    )

    try:
        raw, _model_used = _run_llm(prompt, response_schema=HealthOverview)
        parsed = HealthOverview.model_validate_json(raw)

        # Clamp and validate
        health_score = max(1, min(10, parsed.health_score))
        sentiment_trend = parsed.sentiment_trend.strip().lower()
        if sentiment_trend not in ("improving", "stable", "declining"):
            sentiment_trend = "stable"

        return {
            "summary": parsed.summary.strip() or "Unable to generate summary.",
            "key_points": [s.strip() for s in parsed.key_points if s][:6],
            "actions": [s.strip() for s in parsed.actions if s][:3],
            "health_score": health_score,
            "sentiment_trend": sentiment_trend,
            "top_strengths": [s.strip() for s in parsed.top_strengths if s][:3],
        }
    except Exception as exc:
        logger.error("Failed to generate health overview: %s", exc)
        return {
            "summary": "Unable to generate health overview.",
            "key_points": [],
            "actions": [],
            "health_score": 5,
            "sentiment_trend": "stable",
            "top_strengths": [],
        }


def compare_games(
    games_data: List[Dict[str, Any]],
    comparison_type: str,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate AI-powered comparison summary for 2 games.

    Args:
        games_data: List of game dicts with:
            - app_id: int
            - name: str
            - reviews: List[dict] (filtered sample)
            - metrics: Dict (recommendation rates, counts)
        comparison_type: "overview" | "category" | "subcategory"
        category: Main category for category/subcategory comparisons
        subcategory: Specific subcategory for subcategory comparisons

    Returns:
        Dict with:
            - summary: str (2-3 sentence overview)
            - winners: Dict[str, List[int]] (app_ids that excel in different areas)
            - key_differences: List[str] (2-3 bullet points)
            - strengths_per_game: Dict[int, List[str]] (per app_id)
            - weaknesses_per_game: Dict[int, List[str]] (per app_id)
            - recommendations: Dict[int, str] (who each game is best for)
    """
    # Build prompt based on comparison type
    if comparison_type == "overview":
        prompt_template = """You are analyzing Steam game reviews to compare multiple games. Generate a clear, actionable comparison.

GAMES BEING COMPARED:
{game_summaries}

OUTPUT JSON SCHEMA:
{{
  "summary": "<2-4 sentence overview highlighting what makes each game unique>",
  "winners": {{
    "<aspect>": [<app_ids>],
    ...
  }},
  "key_differences": [
    "<specific comparison point with percentages>",
    ...
  ],
  "strengths_per_game": {{
    <app_id>: ["<strength 1>", "<strength 2>", ...],
    ...
  }},
  "weaknesses_per_game": {{
    <app_id>: ["<weakness 1>", "<weakness 2>", ...],
    ...
  }},
  "recommendations": {{
    <app_id>: "<who this game is best for>",
    ...
  }}
}}

RULES:
- Be specific with data (use percentages, review counts)
- Highlight competitive advantages (>10% difference is significant)
- Focus on actionable insights, not generic praise
- Winners can be multiple games (ties are OK)
- Each game should have 2-4 strengths and 1-3 weaknesses
- Recommendations should differentiate target audiences

REVIEW SAMPLES:
{review_samples}"""

    elif comparison_type == "category":
        prompt_template = """You are analyzing Steam game reviews to compare games in a specific category: {category}.

GAMES BEING COMPARED:
{game_summaries}

FOCUS CATEGORY: {category}

OUTPUT JSON SCHEMA:
{{
  "summary": "<2-3 sentence overview of differences in {category}>",
  "winners": {{
    "<subcategory_or_aspect>": [<app_ids>],
    ...
  }},
  "key_differences": [
    "<specific comparison point with percentages for {category}>",
    ...
  ],
  "strengths_per_game": {{
    <app_id>: ["<{category} strength 1>", "<{category} strength 2>"],
    ...
  }},
  "weaknesses_per_game": {{
    <app_id>: ["<{category} weakness 1>", ...],
    ...
  }},
  "recommendations": {{
    <app_id>: "<who this game is best for based on {category}>",
    ...
  }}
}}

RULES:
- Focus ONLY on {category} aspects
- Use specific metrics and percentages
- Identify which game excels in specific subcategories
- Be concise (2-3 strengths/weaknesses per game)

REVIEW SAMPLES (filtered for {category}):
{review_samples}"""

    else:  # subcategory
        prompt_template = """You are analyzing Steam game reviews to compare games on a specific subcategory: {subcategory}.

GAMES BEING COMPARED:
{game_summaries}

FOCUS SUBCATEGORY: {subcategory}

OUTPUT JSON SCHEMA:
{{
  "summary": "<1-2 sentence comparison of {subcategory} differences>",
  "winners": {{
    "{subcategory}": [<app_ids>]
  }},
  "key_differences": [
    "<specific {subcategory} comparison with data>",
    ...
  ],
  "strengths_per_game": {{
    <app_id>: ["<{subcategory} strength>", ...],
    ...
  }},
  "weaknesses_per_game": {{
    <app_id>: ["<{subcategory} weakness>", ...],
    ...
  }},
  "recommendations": {{
    <app_id>: "<who should choose this game for {subcategory}>",
    ...
  }}
}}

RULES:
- Focus ONLY on {subcategory}
- Extract specific player feedback about {subcategory}
- 1-2 strengths/weaknesses per game
- Very specific and actionable insights

REVIEW SAMPLES (filtered for {subcategory}):
{review_samples}"""

    # Build game summaries
    game_summaries = []
    for game in games_data:
        metrics = game.get("metrics", {})
        rec_rate_raw = metrics.get("recommendation_rate", 0)
        try:
            rec_rate = float(rec_rate_raw or 0.0)
        except Exception:
            rec_rate = 0.0
        # Support both 0-1 fractions and 0-100 percentages.
        rec_pct = rec_rate * 100.0 if rec_rate <= 1.0 else rec_rate
        total = metrics.get("total_reviews", len(game.get("reviews", [])))
        summary = f"Game: \"{game['name']}\" (App ID: {game['app_id']}, Recommendation: {rec_pct:.1f}%, Reviews: {total})"
        game_summaries.append(summary)

    def _clean_snippet(value: Any, max_len: int = 160) -> Optional[str]:
        text = str(value).replace("\n", " ").replace("\r", " ").strip()
        if not text:
            return None
        if len(text) > max_len:
            return text[:max_len] + "..."
        return text

    def _extract_evidence(review: Mapping[str, Any], *, target_subcategory: Optional[str], target_category: Optional[str]) -> list[str]:
        evidence = review.get("llm_subcategory_evidence") or review.get("subcategory_evidence") or {}
        if not isinstance(evidence, dict):
            return []
        evidence_map = {
            str(key).lower(): value
            for key, value in evidence.items()
            if isinstance(key, str)
        }

        items: list[Any] = []
        if target_subcategory:
            values = evidence_map.get(target_subcategory.lower())
            if values is not None:
                items = values if isinstance(values, list) else [values]
        elif target_category:
            prefix = f"{target_category.lower()}/"
            for key, value in evidence_map.items():
                if key.startswith(prefix):
                    if isinstance(value, list):
                        items.extend(value)
                    else:
                        items.append(value)
        else:
            for value in evidence_map.values():
                if isinstance(value, list):
                    items.extend(value)
                else:
                    items.append(value)
                if items:
                    break

        snippets: list[str] = []
        for item in items:
            cleaned = _clean_snippet(item)
            if cleaned and cleaned not in snippets:
                snippets.append(cleaned)
            if len(snippets) >= 2:
                break
        return snippets

    # Build review samples (hybrid: evidence snippets + a few full reviews)
    review_samples = []
    for game in games_data:
        reviews = game.get("reviews", [])[:50]  # Limit to 50 reviews per game
        if not reviews:
            continue

        review_samples.append(f"\n--- {game['name']} (App ID: {game['app_id']}) ---")
        evidence_lines: list[str] = []
        full_review_lines: list[str] = []
        full_review_limit = min(10, len(reviews))

        for i, review in enumerate(reviews, 1):
            voted_up = "Positive" if review.get("voted_up") else "Negative"
            subcats = review.get("llm_subcategories", [])
            snippets = _extract_evidence(
                review,
                target_subcategory=subcategory if comparison_type == "subcategory" else None,
                target_category=category if comparison_type == "category" else None,
            )
            if snippets:
                evidence_text = " | ".join(snippets)
            else:
                fallback = review.get("review", "")[:160]
                evidence_text = fallback + ("..." if len(fallback) == 160 else "")
            evidence_lines.append(f"{i}. [{voted_up}] {evidence_text} (Subcategories: {', '.join(subcats[:3])})")

            if i <= full_review_limit:
                review_text = review.get("review", "")[:300]  # Truncate long reviews
                full_review_lines.append(f"{i}. [{voted_up}] {review_text}... (Subcategories: {', '.join(subcats[:3])})")

        review_samples.append("EVIDENCE SNIPPETS:\n" + "\n".join(evidence_lines))
        review_samples.append("FULL REVIEW EXAMPLES:\n" + "\n".join(full_review_lines))

    # Format the prompt
    prompt = prompt_template.format(
        game_summaries="\n".join(game_summaries),
        review_samples="\n".join(review_samples),
        category=category or "",
        subcategory=subcategory or "",
    )

    # Call LLM via provider abstraction
    try:
        logger.info(f"Comparing {len(games_data)} games (type: {comparison_type})")

        content, model_id = _run_llm(prompt, response_schema=GameComparison)

        if not content or not content.strip():
            raise ValueError("Empty response from LLM")

        logger.debug(f"LLM response length: {len(content)}")

        try:
            result = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            logger.error(f"Response text: {content[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {str(e)}")

        # Convert string keys to int for per-game dicts
        if "strengths_per_game" in result:
            result["strengths_per_game"] = {
                int(k): v for k, v in result["strengths_per_game"].items()
            }
        if "weaknesses_per_game" in result:
            result["weaknesses_per_game"] = {
                int(k): v for k, v in result["weaknesses_per_game"].items()
            }
        if "recommendations" in result:
            result["recommendations"] = {
                int(k): v for k, v in result["recommendations"].items()
            }

        # Ensure all required fields exist
        result.setdefault("summary", "Comparison generated successfully")
        result.setdefault("winners", {})
        result.setdefault("key_differences", [])
        result.setdefault("strengths_per_game", {})
        result.setdefault("weaknesses_per_game", {})
        result.setdefault("recommendations", {})

        logger.info(f"Successfully compared {len(games_data)} games")
        return result

    except LLMError:
        raise
    except ImportError as exc:
        logger.error(f"Import error: {exc}")
        raise LLMError(
            "google-genai package not installed",
            error_type=LLMErrorType.BAD_REQUEST,
        ) from exc
    except json.JSONDecodeError as exc:
        logger.error(f"JSON parsing error: {exc}")
        raise LLMError(
            f"Invalid JSON response from AI: {str(exc)}",
            error_type=LLMErrorType.UNKNOWN,
        ) from exc
    except Exception as exc:
        logger.exception(f"Failed to compare games: {exc}")
        # Check if it's a ClientError from genai
        error_msg = str(exc)
        if "ClientError" in type(exc).__name__:
            error_msg = f"Gemini API error: {str(exc)}"
        raise LLMError(
            f"Failed to generate comparison: {error_msg}",
            error_type=LLMErrorType.UNKNOWN,
        ) from exc


def summarize_news_updates(
    news_items: Sequence[Mapping[str, Any]],
    game_name: Optional[str] = None,
    game_context: Optional[Dict[str, Any]] = None,
    recent_sentiment: Optional[Dict[str, Any]] = None,
    output_language: str = "zh",
) -> Dict[str, Any]:
    """Summarize recent game news/patches and correlate with sentiment if available.

    Args:
        news_items: List of news items with keys: title, contents, date, feed_label
        game_name: Name of the game
        game_context: Optional game context (genres, description)
        recent_sentiment: Optional recent sentiment data to correlate

    Returns:
        Dict with keys:
        - summary: Overall summary paragraph
        - key_updates: List of important updates
        - potential_impacts: List of potential player impact areas
        - correlation_insights: Optional insights correlating with sentiment
    """
    output_language = (output_language or "zh").strip().lower()
    if output_language not in {"zh", "en", "ja"}:
        output_language = "zh"

    if not news_items:
        return {
            "summary": "近期没有可用更新。" if output_language == "zh" else "No recent updates available.",
            "key_updates": [],
            "potential_impacts": [],
            "correlation_insights": None,
        }

    game_name = game_name or (game_context.get("name") if game_context else None) or "the game"

    # Build news context
    news_texts = []
    for item in news_items[:10]:  # Limit to recent 10 items
        title = item.get("title", "Untitled")
        contents = item.get("contents", "")[:500]  # Truncate long content
        feed_label = item.get("feed_label", "Update")
        date_ts = item.get("date", 0)
        date_str = time.strftime("%Y-%m-%d", time.localtime(date_ts)) if date_ts else "Unknown date"

        news_texts.append(f"[{date_str}] {feed_label}: {title}\n{contents}")

    news_block = "\n\n---\n\n".join(news_texts)

    # Build sentiment context if available
    sentiment_context = ""
    if recent_sentiment:
        rec_rate = recent_sentiment.get("recommendation_rate")
        trend = recent_sentiment.get("trend")  # e.g., "improving", "declining", "stable"
        top_issues = recent_sentiment.get("top_issues", [])[:3]
        top_requests = recent_sentiment.get("top_requests", [])[:3]

        if rec_rate is not None:
            sentiment_context += f"\nCurrent recommendation rate: {rec_rate:.1%}"
        if trend:
            sentiment_context += f"\nSentiment trend: {trend}"
        if top_issues:
            sentiment_context += f"\nTop complaints: {', '.join(top_issues)}"
        if top_requests:
            sentiment_context += f"\nTop requests: {', '.join(top_requests)}"

    prompt = dedent(f"""
        Analyze these recent news and updates for {game_name}.

        **Recent News/Patches:**
        {news_block}
        {f"**Recent Player Sentiment:**{sentiment_context}" if sentiment_context else ""}

        Provide a concise analysis in JSON format:
        {{
            "summary": "Brief 2-3 sentence overview of recent update activity",
            "key_updates": ["List of 3-5 most important updates/changes"],
            "potential_impacts": ["List of 2-4 areas that might affect player experience"],
            "correlation_insights": "If sentiment data provided, any correlation between updates and sentiment (or null if no sentiment data)"
        }}

        Focus on:
        - Major patches, bug fixes, content updates
        - Changes that could affect player satisfaction
        - Patterns in update frequency or focus areas
        - If sentiment data available: whether updates address player concerns

        OUTPUT LANGUAGE CONTRACT: summary, key_updates, potential_impacts, and correlation_insights MUST be written in { _summary_language_name(output_language) }. Keep proper nouns and source titles as needed, but write all analytical prose in the requested language.
        Return ONLY the JSON object.
    """).strip()

    prompt += f"\n\nReturn output_language as '{output_language}' when the field is present."

    try:
        raw, _model_used = _run_llm(prompt, response_schema=NewsUpdateSummary)
        result = NewsUpdateSummary.model_validate_json(raw)
        values = [result.summary, *result.key_updates, *result.potential_impacts]
        if result.correlation_insights:
            values.append(result.correlation_insights)
        if not _looks_like_requested_language(values, output_language):
            repair_prompt = prompt + (
                f"\n\nBOUNDED REPAIR: regenerate once using {_summary_language_name(output_language)} "
                "for every analytical field."
            )
            repaired_raw, _model_used = _run_llm(repair_prompt, response_schema=NewsUpdateSummary)
            result = NewsUpdateSummary.model_validate_json(repaired_raw)
            values = [result.summary, *result.key_updates, *result.potential_impacts]
            if result.correlation_insights:
                values.append(result.correlation_insights)
        if not _looks_like_requested_language(values, output_language):
            raise ValueError("Provider did not honor the requested summary language.")
        return {
            "summary": result.summary,
            "key_updates": result.key_updates,
            "potential_impacts": result.potential_impacts,
            "correlation_insights": result.correlation_insights,
        }
    except Exception as exc:
        logger.exception(f"Failed to summarize news: {exc}")
        return {
            "summary": (
                "AI 摘要暂时生成失败，请检查系统设置中的 AI 服务配置后重试。"
                if output_language == "zh"
                else "Failed to generate update summary."
            ),
            "key_updates": [],
            "potential_impacts": [],
            "correlation_insights": None,
        }


__all__ = [
    "apply_review_labels",
    "call_llm_with_tools",
    "classify_review",
    "classify_review_single",
    "compare_games",
    "ensure_review_labels",
    "LLMError",
    "LLMErrorType",
    "LLMResponse",
    "llm_usage_context",
    "run_chat_completion",
    "summarize_news_updates",
    "summarize_subcategory_reviews",
    "summarize_monthly_report",
]
