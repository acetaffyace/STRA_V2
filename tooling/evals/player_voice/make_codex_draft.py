"""Create a clearly non-gold, conservative first-pass review draft."""
from __future__ import annotations

import argparse
import json
import re

from .common import read_jsonl, write_jsonl


POS = r"\b(good|great|love|loving|fun|enjoy|enjoyed|recommend|excellent|best|happy|goated|brutal|yummy)\b|好玩|优秀|喜欢|爽|很好|推荐|牛逼|不错|素晴"
NEG = r"\b(worst|hate|painful|bad|boring|broken|bug|crash|lag|slow|awful|ass|meh|dumb|angry|hard|difficult)\b|垃圾|狗屎|恶心|难玩|太高|不好|延迟|外挂|封|问题|丑|差"
REQUEST = r"\b(please|wish|should|add|need|would love|hopefully|bring back|let me)\b|希望|请|应该|加强|改|补上|新增|能不能|求"


def _has(pattern: str, text: str) -> bool:
    return bool(re.search(pattern, text, flags=re.I))


def _label_topics(text: str) -> list[str]:
    labels: list[str] = []
    mappings = (
        (r"bug|glitch|故障|bug|打不开", "technical/bugs"),
        (r"crash|稳定|崩|闪退", "technical/stability_crashes"),
        (r"lag|delay|延迟|卡顿|性能|performance|performence", "technical/performance"),
        (r"server|服务器|network|网络", "technical/networking"),
        (r"difficulty|难度|难玩|boss|困难", "gameplay/difficulty"),
        (r"balance|平衡|数值|加强|削|削弱", "gameplay/balance"),
        (r"match|匹配|队友|rank|排位", "online_community/matchmaking"),
        (r"外挂|cheat|作弊", "online_community/cheating_anti_cheat"),
        (r"text|翻译|locali[sz]|中文|文本", "presentation/localization"),
        (r"graphic|graphics|画质|美术|visual|角色.*丑|丑", "presentation/visuals_art_style"),
        (r"music|audio|声音|音乐", "presentation/audio_music"),
        (r"story|narrative|剧情|角色.*塑造", "content_design/narrative_characters"),
        (r"level|stage|关|探索|quest|任务", "content_design/level_design"),
        (r"mechanic|gameplay|玩法|机制|战斗|combat", "gameplay/mechanics"),
        (r"control|controls|按键|操作", "gameplay/controls"),
        (r"card|抽|rng|概率|抽卡", "monetization_value/value_for_money"),
        (r"menu|ui|hud|菜单|界面", "ui_ux_accessibility/menus_hud"),
        (r"price|价格|原价|钱|packs", "monetization_value/pricing"),
    )
    for pattern, label in mappings:
        if _has(pattern, text):
            labels.append(label)
    return list(dict.fromkeys(labels))


def draft(record: dict) -> dict:
    text = str(record.get("source_review_text") or "")
    compact = re.sub(r"\s+", " ", text).strip()
    labels = _label_topics(compact)
    pos, neg = _has(POS, compact), _has(NEG, compact)
    if pos and neg:
        sentiment = "mixed"
    elif pos:
        sentiment = "positive"
    elif neg:
        sentiment = "negative"
    else:
        sentiment = "uncertain"
    issue = bool(labels) or neg and len(compact.split()) > 2
    request = _has(REQUEST, compact)
    reasons: list[str] = []
    if len(compact) <= 12:
        reasons.append("短文本，语义不足")
    if not compact or len(compact.split()) <= 2:
        reasons.append("内容过短或为空")
    if "�" in text or re.search(r"[\u2800-\u28ff]{3,}", text):
        reasons.append("可能乱码/符号文本")
    if re.search(r"[!?]{2,}|lol|yeah right|sure|讽刺", compact, flags=re.I):
        reasons.append("可能讽刺或反话")
    if len(compact) > 500:
        reasons.append("长评论，需人工确认多标签")
    if len(labels) > 1:
        reasons.append("多个主题，需确认 taxonomy 边界")
    if not labels and issue:
        reasons.append("问题存在但分类不明确")
    if record.get("language") not in ("english", "schinese", "tchinese"):
        reasons.append("非中英文，需确认语义")
    if not reasons and sentiment == "uncertain":
        reasons.append("缺少足够语义证据")
    evidence = []
    if compact and (issue or request) and len(compact) <= 240:
        evidence = [compact]
    return {
        "sample_id": record["sample_id"],
        "codex_draft": {
            "sentiment": sentiment,
            "issue_present": issue,
            "issue_labels": labels,
            "request_present": request,
            "request_labels": labels if request else [],
            "evidence_spans": evidence,
        },
        "uncertain": bool(reasons),
        "uncertain_reasons": reasons,
        "draft_note": "Codex first-pass draft only; never copy directly into gold without human verification.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="tooling/evals/drafts/P0_5B_annotation_batch.jsonl")
    parser.add_argument("--output", default="tooling/evals/drafts/P0_5B_codex_draft.jsonl")
    args = parser.parse_args()
    records = read_jsonl(args.input)
    write_jsonl(args.output, [draft(record) for record in records])
    print(json.dumps({"records": len(records), "uncertain": sum(draft(record)["uncertain"] for record in records)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
