"""Small local Chinese annotation UI for the P0.5b pending JSONL package."""
from __future__ import annotations

import argparse
import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .common import read_jsonl
from .taxonomy import taxonomy_manifest


HTML = Path(__file__).with_name("annotation_app.html")


class AnnotationState:
    def __init__(self, input_path: Path, output_path: Path, draft_path: Path | None = None):
        self.input_path = input_path
        self.output_path = output_path
        self.records = read_jsonl(input_path)
        self.by_id = {str(record["sample_id"]): record for record in self.records}
        self.drafts = {}
        if draft_path and draft_path.exists():
            self.drafts = {str(item["sample_id"]): item for item in read_jsonl(draft_path)}

    def public_records(self) -> list[dict]:
        # Deliberately expose no predictions, labels, confidence, or benchmark fields.
        return [{**{key: record.get(key) for key in (
            "sample_id", "app_id", "review_id", "source_review_text", "language",
            "sampling_stratum", "sampling_reason", "annotation_status", "gold",
        )}, "codex_draft": self.drafts.get(str(record["sample_id"]))} for record in self.records]

    def save(self, sample_id: str, payload: dict) -> dict:
        record = self.by_id[sample_id]
        gold = {
            "sentiment": payload.get("sentiment"),
            "subcategories": payload.get("subcategories", []),
            "issue_present": payload.get("issue_present"),
            "issue_labels": payload.get("issue_labels", []),
            "request_present": payload.get("request_present"),
            "request_labels": payload.get("request_labels", []),
            "evidence_spans": payload.get("evidence_spans", []),
        }
        record["gold"] = gold
        record["annotation_status"] = payload.get("annotation_status", "labeled")
        record["annotator_id"] = str(payload.get("annotator_id") or "").strip() or None
        record["annotation_notes"] = str(payload.get("annotation_notes") or "").strip()
        record["adjudication_status"] = payload.get("adjudication_status", "not_started")
        self._write()
        return {"sample_id": sample_id, "annotation_status": record["annotation_status"]}

    def _write(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="annotation-", suffix=".jsonl", dir=self.output_path.parent)
        try:
            with open(fd, "w", encoding="utf-8", newline="\n") as handle:
                for record in self.records:
                    handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
            Path(name).replace(self.output_path)
        finally:
            Path(name).unlink(missing_ok=True)


def make_handler(state: AnnotationState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def _json(self, value: object, status: int = 200) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                body = HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/options":
                self._json(taxonomy_manifest())
            elif path == "/api/records":
                self._json({"records": state.public_records(), "output": str(state.output_path)})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/save":
                self._json({"error": "not found"}, 404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                result = state.save(str(payload["sample_id"]), payload)
                self._json({"ok": True, **result})
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                self._json({"ok": False, "error": str(exc)}, 400)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="启动中文玩家评论人工标注平台")
    parser.add_argument("--input", default="tooling/evals/drafts/P0_5B_annotation_batch.jsonl")
    parser.add_argument("--output", default="tooling/evals/drafts/P0_5B_annotation_batch.annotated.jsonl")
    parser.add_argument("--draft", default="tooling/evals/drafts/P0_5B_codex_draft.jsonl")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    draft_path = Path(args.draft)
    state = AnnotationState(Path(args.input), Path(args.output), draft_path if draft_path.exists() else None)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(state))
    print(f"标注平台已启动: http://127.0.0.1:{args.port}/")
    print(f"输入: {state.input_path.resolve()}")
    print(f"保存: {state.output_path.resolve()}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n标注平台已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
