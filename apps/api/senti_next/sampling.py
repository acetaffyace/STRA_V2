"""Research sampling contracts for Steam review populations.

The contract describes the population to acquire.  It deliberately does not
describe the later semantic/LLM sample, which is a separate concern.
"""
from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


CollectionOrder = Literal["recent", "updated", "helpful"]
ReviewType = Literal["all", "positive", "negative"]
PurchaseType = Literal["all", "steam", "non_steam_purchase"]


class SamplingContract(BaseModel):
    """Serializable definition of a Steam review research population.

    ``start_time`` and ``end_time`` are inclusive Unix timestamps applied to
    ``timestamp_created`` after acquisition. ``max_reviews=0`` is the sole
    unlimited convention.  A time window is intentionally restricted to the
    chronological Steam mode: Steam's helpfulness mode uses sliding windows
    and cannot establish complete historical coverage.
    """

    app_id: int = Field(..., gt=0)
    start_time: Optional[int] = Field(default=None, ge=0)
    end_time: Optional[int] = Field(default=None, ge=0)
    languages: List[str] = Field(default_factory=lambda: ["all"], min_length=1)
    review_type: ReviewType = "all"
    purchase_type: PurchaseType = "all"
    collection_order: CollectionOrder = "recent"
    include_offtopic_activity: bool = False
    max_reviews: int = Field(default=0, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _normalize_languages(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        normalized = dict(values)
        languages = normalized.get("languages")
        if languages is None:
            normalized["languages"] = ["all"]
        elif isinstance(languages, str):
            normalized["languages"] = [languages]
        else:
            normalized["languages"] = list(languages)
        return normalized

    @model_validator(mode="after")
    def _validate_scope(self) -> "SamplingContract":
        self.languages = [str(language).strip().lower() for language in self.languages if str(language).strip()]
        if not self.languages:
            raise ValueError("languages must contain at least one non-empty language")
        if "all" in self.languages and len(self.languages) > 1:
            raise ValueError("languages cannot combine 'all' with specific languages")
        if self.start_time is not None and self.end_time is not None and self.start_time > self.end_time:
            raise ValueError("start_time must not be after end_time")
        if (self.start_time is not None or self.end_time is not None) and self.collection_order != "recent":
            raise ValueError("arbitrary time windows require collection_order='recent'")
        return self

    @property
    def unlimited(self) -> bool:
        return self.max_reviews == 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible immutable configuration snapshot."""
        return self.model_dump(mode="json")


# Friendly alias for callers that prefer the query vocabulary.
ReviewQuery = SamplingContract


__all__ = [
    "CollectionOrder",
    "PurchaseType",
    "ReviewQuery",
    "ReviewType",
    "SamplingContract",
]
