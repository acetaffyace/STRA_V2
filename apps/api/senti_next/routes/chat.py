"""Chat endpoints: /chat, /chat/simple, /chat/*."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from .. import storage, llm, chat as chat_module, chat_agent

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory chat status tracking for SSE
# ---------------------------------------------------------------------------

_chat_status_store: Dict[str, List[str]] = {}
_chat_status_lock = asyncio.Lock()


def _get_chat_status_store() -> Dict[str, List[str]]:
    return _chat_status_store


def _emit_chat_status(session_id: str, status: str) -> None:
    store = _get_chat_status_store()
    if session_id not in store:
        store[session_id] = []
    store[session_id].append(status)
    if len(store[session_id]) > 20:
        store[session_id] = store[session_id][-20:]
    if len(store) > 1000:
        oldest_keys = list(store.keys())[:len(store) - 1000]
        for key in oldest_keys:
            del store[key]


def _get_chat_status(session_id: str) -> List[str]:
    return _get_chat_status_store().get(session_id, [])


def _clear_chat_status(session_id: str) -> None:
    store = _get_chat_status_store()
    if session_id in store:
        del store[session_id]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    app_id: int = Field(..., gt=0)
    question: str = Field(..., min_length=3, max_length=5000)
    sentiment: str = Field("all")
    min_helpful: int = Field(0, ge=0)
    max_days: Optional[int] = Field(None, ge=1, le=365)
    playtime_bucket: str = Field("all")
    language: str = Field("all")
    max_reviews: int = Field(500, ge=1, le=5000)
    max_snippets: int = Field(8, ge=1, le=20)


class SimpleChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[str] = None
    app_ids: Optional[List[int]] = Field(None, max_length=2, description="App IDs for game context (max 2)")
    date_filter: str = Field("all", description="Date filter: 30d, 90d, 365d, or all")
    max_reviews_per_game: int = Field(50, ge=1, le=50, description="Max reviews per game")
    language: Optional[str] = Field(None, description="Preferred language for responses")


class ChatCitationItem(BaseModel):
    review_id: str
    app_id: int
    game_name: str
    snippet: str
    votes_up: int
    voted_up: Optional[bool] = None
    playtime_hours: float
    verification_status: str = "unverified"
    verification_method: Optional[str] = None
    source_review_hash: Optional[str] = None
    quote_start: Optional[int] = None
    quote_end: Optional[int] = None


class SimpleChatResponse(BaseModel):
    response: str
    session_id: str
    citations: List[ChatCitationItem] = Field(default_factory=list)
    games_used: List[Dict[str, Any]] = Field(default_factory=list)
    reviews_searched: int = 0
    has_game_context: bool = False
    suggested_questions: List[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_options: List[str] = Field(default_factory=list)
    tool_calls_made: int = 0
    suggest_search_game: bool = False
    search_game_name: str = ""
    source_reviews: List[ChatCitationItem] = Field(default_factory=list)
    mode: Optional[str] = None
    error_code: Optional[str] = None
    operational_warning: Optional[str] = None


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    session_id: Optional[str] = None


class ChatSession(BaseModel):
    session_id: str
    message_count: int
    started_at: Optional[str] = None
    last_message_at: Optional[str] = None
    first_user_message: Optional[str] = None


class ChatCitation(BaseModel):
    review_id: str
    subcategory: str
    snippet: str
    votes_up: Optional[int] = None
    created_at: Optional[str] = None
    voted_up: Optional[bool] = None
    review_text: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    citations: List[ChatCitation]
    used_subcategories: List[str]
    model: str
    review_count: int
    filtered_review_count: int


class CitationFeedbackRequest(BaseModel):
    review_id: str
    session_id: str
    helpful: bool


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def chat_insights(request: ChatRequest) -> ChatResponse:

    question = (request.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    sentiment = (request.sentiment or "all").strip().lower()
    if sentiment not in {"all", "positive", "negative"}:
        sentiment = "all"

    try:
        payload = chat_module.answer_chat(
            app_id=request.app_id,
            question=question,
            sentiment=sentiment,
            min_helpful=request.min_helpful,
            max_days=request.max_days,
            playtime_bucket=request.playtime_bucket,
            language=request.language,
            max_reviews=request.max_reviews,
            max_snippets=request.max_snippets,
        )
    except ValueError as exc:
        msg = str(exc)
        # LLM provider configuration errors → 503; everything else → 400
        if "provider" in msg.lower() and ("configured" in msg.lower() or "api key" in msg.lower()):
            raise HTTPException(status_code=503, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except Exception as exc:
        logger.exception("Chat failed: %s", exc)
        raise HTTPException(status_code=500, detail="Chat request failed.") from exc

    return ChatResponse(**payload)


@router.post("/chat/simple", response_model=SimpleChatResponse)
async def simple_chat(request: SimpleChatRequest) -> SimpleChatResponse:

    message = (request.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session_id: Optional[str] = None
    try:
        import uuid

        session_id = request.session_id
        if not session_id:
            session_id = str(uuid.uuid4())

        history = storage.load_chat_history(limit=20, session_id=session_id)

        app_ids = request.app_ids or []
        has_game_context = bool(app_ids)

        if has_game_context:
            logger.info(f"Chat with game context: app_ids={app_ids}, date_filter={request.date_filter}")

            # Offline fixture mode is a hard contract: it must never enter the
            # provider/tool-calling loop.  Resolve the immutable result first
            # and answer through deterministic evidence lookup.
            if len(app_ids) == 1:
                offline_result = storage.load_analysis_result(app_ids[0])
                offline_metadata = (offline_result or {}).get("metadata") or {}
                if offline_metadata.get("mode") == "codex_offline_fixture":
                    from ..offline_chat import answer_offline_question
                    offline_answer = answer_offline_question(offline_result, message)
                    game_metadata = storage.load_game_metadata_for_chat(app_ids)
                    game_names = {g["app_id"]: g["name"] for g in game_metadata}
                    citations = [
                        ChatCitationItem(
                            review_id=str(item.get("review_id") or ""),
                            app_id=app_ids[0],
                            game_name=game_names.get(app_ids[0], f"Game {app_ids[0]}"),
                            snippet=str(item.get("quote") or ""),
                            votes_up=0,
                            playtime_hours=0,
                            verification_status=str(item.get("verification_status") or "verified"),
                            verification_method=item.get("verification_method"),
                            source_review_hash=item.get("source_review_hash"),
                        )
                        for item in offline_answer.get("citations", [])
                        if item.get("review_id")
                    ]
                    response_text = json.dumps(offline_answer.get("answer"), ensure_ascii=False, indent=2)
                    storage.save_chat_message("user", message, session_id=session_id)
                    storage.save_chat_message("assistant", response_text, session_id=session_id, evidence=offline_answer.get("citations", []))
                    return SimpleChatResponse(
                        response=response_text,
                        session_id=session_id,
                        citations=citations,
                        source_reviews=citations,
                        games_used=game_metadata,
                        reviews_searched=int((offline_result.get("metadata") or {}).get("retrieved") or 0),
                        has_game_context=True,
                        suggested_questions=[],
                        tool_calls_made=0,
                        mode="codex_offline_fixture",
                    )

            def status_callback(status: str) -> None:
                _emit_chat_status(session_id, status)

            game_metadata = storage.load_game_metadata_for_chat(app_ids)
            game_names = {g["app_id"]: g["name"] for g in game_metadata}

            agent_context = chat_agent.AgentContext(
                session_id=session_id,
                app_ids=app_ids,
                date_filter=request.date_filter,
                max_reviews_per_game=request.max_reviews_per_game,
                language=(request.language or "zh").strip().lower(),
                conversation_history=[
                    {"role": msg["role"], "content": msg["content"]}
                    for msg in history
                ],
                game_names=game_names,
            )

            with llm.llm_usage_context(
                session_id=session_id,
                app_id=app_ids[0] if len(app_ids) == 1 else None,
                operation="chat_agent",
            ):
                agent_result = await chat_agent.run_agent(
                    message=message,
                    context=agent_context,
                    status_callback=status_callback,
                )

            _clear_chat_status(session_id)

            if agent_result.needs_clarification:
                clarification_text = chat_agent.build_clarification_response(
                    agent_result.clarification_options,
                    agent_result.clarification_context,
                )
                return SimpleChatResponse(
                    response=clarification_text,
                    session_id=session_id,
                    citations=[],
                    source_reviews=[],
                    games_used=game_metadata,
                    reviews_searched=0,
                    has_game_context=True,
                    suggested_questions=[],
                    needs_clarification=True,
                    clarification_options=agent_result.clarification_options,
                    tool_calls_made=len(agent_result.tool_calls_made),
                )

            if agent_result.suggest_search_game:
                return SimpleChatResponse(
                    response=agent_result.response,
                    session_id=session_id,
                    citations=[],
                    source_reviews=[],
                    games_used=game_metadata,
                    reviews_searched=0,
                    has_game_context=True,
                    suggested_questions=[],
                    needs_clarification=False,
                    clarification_options=[],
                    tool_calls_made=len(agent_result.tool_calls_made),
                    suggest_search_game=True,
                    search_game_name=agent_result.search_game_name,
                )

            response_text = agent_result.response
            if not response_text or not response_text.strip():
                response_text = "暂时没有生成完整回答，请换一种方式描述你的问题后重试。"
            from ..evidence import gate_response_quotes
            agent_sources = []
            for tool_call in agent_result.tool_calls_made:
                if tool_call.get("tool") != "search_reviews":
                    continue
                for review in (tool_call.get("result") or {}).get("reviews", []):
                    agent_sources.append({
                        "text": review.get("text", ""),
                        "review_id": review.get("review_id"),
                        "app_id": (tool_call.get("params") or {}).get("app_id"),
                    })
            gated_response = gate_response_quotes(response_text, agent_sources)
            response_text = gated_response["response"]
            persisted_evidence = [*agent_result.evidence, *gated_response["evidence"]]
            suggested_questions = agent_result.suggested_questions
            tool_calls_made = len(agent_result.tool_calls_made)
            verified_by_id = {
                str(item.get("review_id")): item
                for item in persisted_evidence
                if item.get("verification_status") == "verified" and item.get("review_id")
            }

            citations = []
            for tc in agent_result.tool_calls_made:
                if tc.get("tool") == "search_reviews":
                    result_data = tc.get("result", {})
                    for review in result_data.get("reviews", []):
                        if review.get("review_id"):
                            citation_app_id = int(tc.get("params", {}).get("app_id") or (app_ids[0] if app_ids else 0))
                            citation = ChatCitationItem(
                                review_id=str(review.get("review_id", "")),
                                app_id=citation_app_id,
                                game_name=game_names.get(citation_app_id, f"Game {citation_app_id}"),
                                snippet=review.get("text", "")[:200],
                                votes_up=review.get("votes_up", 0),
                                voted_up=review.get("sentiment") == "positive",
                                playtime_hours=review.get("playtime_hours", 0),
                                verification_status=(verified_by_id.get(str(review.get("review_id"))) or {}).get("verification_status", "unverified"),
                                verification_method=(verified_by_id.get(str(review.get("review_id"))) or {}).get("verification_method"),
                                source_review_hash=(verified_by_id.get(str(review.get("review_id"))) or {}).get("source_review_hash"),
                                quote_start=(verified_by_id.get(str(review.get("review_id"))) or {}).get("quote_start"),
                                quote_end=(verified_by_id.get(str(review.get("review_id"))) or {}).get("quote_end"),
                            )
                            citations.append(citation)
                            if len(citations) >= 5:
                                break
                if len(citations) >= 5:
                    break

            # Citation cards are direct-evidence surfaces. Only evidence that
            # passed the shared source verifier may be serialized as a quote.
            citations = [item for item in citations if item.verification_status == "verified"]

            source_reviews = []
            for tc in agent_result.tool_calls_made:
                if tc.get("tool") == "search_reviews":
                    result_data = tc.get("result", {})
                    for review in result_data.get("reviews", []):
                        if review.get("review_id"):
                            citation_app_id = int(tc.get("params", {}).get("app_id") or (app_ids[0] if app_ids else 0))
                            source_review = ChatCitationItem(
                                review_id=str(review.get("review_id", "")),
                                app_id=citation_app_id,
                                game_name=game_names.get(citation_app_id, f"Game {citation_app_id}"),
                                snippet=review.get("text", ""),
                                votes_up=review.get("votes_up", 0),
                                voted_up=review.get("sentiment") == "positive",
                                playtime_hours=review.get("playtime_hours", 0),
                                verification_status="verified",
                                verification_method="current_source_review",
                            )
                            source_reviews.append(source_review)

            games_used = game_metadata
            reviews_searched = sum(
                tc.get("result", {}).get("total_found", 0)
                for tc in agent_result.tool_calls_made
                if tc.get("tool") == "search_reviews"
            )
        else:
            conversation_text = ""
            for msg in history:
                role_label = "User" if msg["role"] == "user" else "Assistant"
                conversation_text += f"{role_label}: {msg['content']}\n\n"

            conversation_text += f"User: {message}\n\nAssistant:"

            prompt = f"""You are a helpful, friendly AI assistant. You are having a conversation with a user.
Previous conversation:
{conversation_text if history else 'This is the start of the conversation.'}

Please respond naturally to the user's latest message, considering the conversation history.
Respond in Simplified Chinese for all analytical prose and interface-facing text. Keep only proper nouns or direct quotes in their original language when needed.
If the user asks for a chart/plot/graph, include a fenced code block with language 'chart' containing JSON for Chart.js.
Example:
```chart
{{"type":"bar","title":"Example","data":{{"labels":["A","B"],"datasets":[{{"label":"Value","data":[1,2]}}]}}}}
```
"""

            with llm.llm_usage_context(
                session_id=session_id,
                operation="chat_simple",
            ):
                response_text, model_id = llm.run_chat_completion(prompt)
            citations = []
            source_reviews = []
            games_used = []
            reviews_searched = 0
            suggested_questions = []
            tool_calls_made = 0

        storage.save_chat_message("user", message, session_id=session_id)
        storage.save_chat_message(
            "assistant", response_text, session_id=session_id,
            evidence=(persisted_evidence if has_game_context and 'persisted_evidence' in locals() else []),
        )

        return SimpleChatResponse(
            response=response_text,
            session_id=session_id,
            citations=citations,
            source_reviews=source_reviews,
            games_used=games_used,
            reviews_searched=reviews_searched,
            has_game_context=has_game_context,
            suggested_questions=suggested_questions,
            needs_clarification=False,
            clarification_options=[],
            tool_calls_made=tool_calls_made,
            suggest_search_game=False,
            search_game_name="",
            mode="live_provider" if has_game_context else "live_provider",
            operational_warning=("部分工具或 Provider 结果不可用，以上回答仅包含已验证的观察。" if has_game_context and getattr(locals().get("agent_result"), "error", None) else None),
        )
    except Exception as exc:
        logger.exception("Simple chat failed: %s", exc)
        message_text = str(exc).lower()
        if "bind parameter" in message_text or "sqlalchemy" in message_text:
            code = "DATA_QUERY_FAILED"
        elif "provider" in message_text or "tool_call" in message_text:
            code = "PROVIDER_FAILED"
        else:
            code = "INTERNAL_ERROR"
        raise HTTPException(status_code=500, detail={"code": code, "message": "Chat 暂时无法完成，请查看已返回的证据或稍后重试。"}) from exc


@router.get("/chat/sessions", response_model=List[ChatSession])
def get_chat_sessions() -> List[ChatSession]:

    try:
        sessions = storage.get_chat_sessions()
        return [ChatSession(**session) for session in sessions]
    except Exception as exc:
        logger.exception("Failed to load chat sessions: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load chat sessions.") from exc


@router.get("/chat/history", response_model=List[ChatMessage])
def get_chat_history(session_id: Optional[str] = None) -> List[ChatMessage]:

    try:
        history = storage.load_chat_history(limit=100, session_id=session_id)
        return [ChatMessage(**msg) for msg in history]
    except Exception as exc:
        logger.exception("Failed to load chat history: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load chat history.") from exc


@router.delete("/chat/history")
def clear_chat_history_endpoint(session_id: Optional[str] = None) -> Dict[str, Any]:

    try:
        count = storage.clear_chat_history(session_id=session_id)
        return {"deleted": count}
    except Exception as exc:
        logger.exception("Failed to clear chat history: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to clear chat history.") from exc


@router.post("/chat/citation-feedback")
def submit_citation_feedback(request: CitationFeedbackRequest) -> Dict[str, str]:

    try:
        storage.save_citation_feedback(
            session_id=request.session_id,
            review_id=request.review_id,
            helpful=request.helpful,
        )
        return {"status": "ok"}
    except Exception as exc:
        logger.exception("Failed to save citation feedback: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save feedback.") from exc


@router.get("/chat/export/{session_id}")
def export_chat_session(session_id: str, format: str = "markdown"):

    messages = storage.load_chat_history(limit=500, session_id=session_id)

    if not messages:
        raise HTTPException(status_code=404, detail="No messages found for this session.")

    if format == "json":
        return JSONResponse(
            content={"session_id": session_id, "messages": messages},
            headers={"Content-Disposition": f"attachment; filename=chat-{session_id}.json"},
        )

    md_lines = [f"# Chat Session {session_id}\n"]
    for msg in messages:
        role_label = "**User**" if msg["role"] == "user" else "**Assistant**"
        timestamp = msg.get("timestamp", "")
        if timestamp:
            md_lines.append(f"{role_label} ({timestamp}):\n")
        else:
            md_lines.append(f"{role_label}:\n")
        md_lines.append(f"{msg['content']}\n\n---\n")

    md_content = "\n".join(md_lines)
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=chat-{session_id}.md"},
    )


@router.get("/chat/stream/{session_id}")
async def chat_stream(session_id: str):
    async def event_generator():
        last_index = 0
        idle_count = 0
        max_idle = 60

        while True:
            try:
                statuses = _get_chat_status(session_id)

                if len(statuses) > last_index:
                    for status in statuses[last_index:]:
                        yield f"event: status\ndata: {json.dumps({'message': status, 'timestamp': datetime.now(timezone.utc).isoformat() + 'Z'})}\n\n"
                        idle_count = 0
                    last_index = len(statuses)

                if statuses and any("generating" in s.lower() for s in statuses[-3:]):
                    await asyncio.sleep(0.5)
                    if not _get_chat_status(session_id):
                        yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"
                        return

                idle_count += 1
                if idle_count >= max_idle:
                    yield f"event: timeout\ndata: {json.dumps({'status': 'timeout'})}\n\n"
                    return

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning("Chat SSE stream error: %s", exc)
                yield f"event: error\ndata: {json.dumps({'status': 'error', 'error': str(exc)})}\n\n"
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


