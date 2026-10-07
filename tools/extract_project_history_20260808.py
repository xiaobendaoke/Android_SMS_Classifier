#!/usr/bin/env python3
"""Extract a dated timeline summary from Codex and Cursor project history.

Inputs:
- C:\\Users\\woshinibaba\\.codex\\sessions\\2026\\08\\**\\*.jsonl
- C:\\Users\\woshinibaba\\.cursor\\projects\\c-Users-woshinibaba-Documents-oppo-Android-SMS-Classifier\\agent-transcripts\\**\\*.jsonl
- C:\\Users\\woshinibaba\\.cursor\\projects\\c-dev-Android-SMS-Classifier\\agent-transcripts\\**\\*.jsonl

Output (gitignored): training/data/interim/history/history_summary_20260808.json
Keeps only dates, roles, truncated user asks, assistant conclusions and tool
names. No raw SMS text is intentionally captured.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT = Path(__file__).resolve().parent.parent
PROJECT_CWD = "Android_SMS_Classifier"
CODEX_ROOT = Path.home() / ".codex/sessions/2026/08"
CURSOR_ROOTS = [
    Path.home() / ".cursor/projects/c-Users-woshinibaba-Documents-oppo-Android-SMS-Classifier/agent-transcripts",
    Path.home() / ".cursor/projects/c-dev-Android-SMS-Classifier/agent-transcripts",
]
OUT = ROOT / "training/data/interim/history/history_summary_20260808.json"


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
            elif item.get("type") == "input_text" and item.get("text"):
                parts.append(str(item["text"]))
            elif item.get("type") == "tool_use":
                name = item.get("name", "")
                try:
                    args = json.dumps(item.get("input", {}), ensure_ascii=False)
                except (TypeError, ValueError):
                    args = ""
                parts.append(f"[tool:{name}] {args[:300]}")
            elif item.get("type") == "tool_result":
                inner = item.get("content", "")
                parts.append(f"[tool_result] {text_of(inner)[:200]}")
        return "\n".join(part for part in parts if part)
    return ""


def first_timestamp(text: str) -> Optional[str]:
    match = re.search(r"<timestamp>([^<]+)</timestamp>", text)
    if match:
        return match.group(1).strip()
    return None


def truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value[:limit] + ("..." if len(value) > limit else "")


def parse_codex(path: Path) -> Optional[Dict[str, Any]]:
    cwd: Optional[str] = None
    originator = ""
    timestamps: List[str] = []
    user_msgs: List[str] = []
    assistant_msgs: List[str] = []
    tools: Counter = Counter()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = obj.get("payload") or {}
            if obj.get("type") == "session_meta":
                cwd = payload.get("cwd") or ""
                originator = str(payload.get("originator") or "")
            ts = str(obj.get("timestamp") or "")
            if ts:
                timestamps.append(ts)
            if obj.get("type") != "response_item":
                continue
            if payload.get("type") != "message":
                continue
            role = str(payload.get("role") or "")
            content = payload.get("content")
            text = text_of(content)
            if not text:
                continue
            if role == "user":
                user_msgs.append(truncate(text, 400))
            elif role == "assistant":
                assistant_msgs.append(truncate(text, 400))
            for tool_name in re.findall(r"\[tool:([A-Za-z0-9_]+)\]", text):
                tools[tool_name] += 1
    if not cwd or PROJECT_CWD not in cwd:
        return None
    return {
        "source": "codex",
        "file": str(path),
        "cwd": cwd,
        "originator": originator,
        "first_ts": timestamps[0] if timestamps else "",
        "last_ts": timestamps[-1] if timestamps else "",
        "user_asks": user_msgs[-4:],
        "assistant_final": assistant_msgs[-1:] or assistant_msgs[-2:],
        "tool_counts": dict(tools.most_common(12)),
    }


def parse_cursor(path: Path) -> Optional[Dict[str, Any]]:
    user_msgs: List[str] = []
    assistant_msgs: List[str] = []
    tools: Counter = Counter()
    first_date = ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            role = str(obj.get("role") or "")
            message = obj.get("message") or {}
            content = message.get("content")
            text = text_of(content)
            if not text:
                continue
            if role == "user":
                stamp = first_timestamp(text)
                if stamp and not first_date:
                    first_date = stamp
                user_msgs.append(truncate(re.sub(r"<timestamp>.*?</timestamp>", "", text), 400))
            elif role == "assistant":
                assistant_msgs.append(truncate(text, 400))
            for tool_name in re.findall(r"\[tool:([A-Za-z0-9_]+)\]", text):
                tools[tool_name] += 1
    return {
        "source": "cursor",
        "file": str(path),
        "date": first_date,
        "user_asks": user_msgs[-3:],
        "assistant_final": assistant_msgs[-1:] or assistant_msgs[-2:],
        "tool_counts": dict(tools.most_common(12)),
    }


def main() -> int:
    sessions: List[Dict[str, Any]] = []
    for path in sorted(CODEX_ROOT.rglob("*.jsonl")):
        parsed = parse_codex(path)
        if parsed:
            sessions.append(parsed)
    for root in CURSOR_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.jsonl")):
            parsed = parse_cursor(path)
            if parsed:
                sessions.append(parsed)
    sessions.sort(key=lambda item: (item.get("first_ts") or item.get("date") or "", item.get("file", "")))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "generated_at": datetime.now().astimezone().isoformat(),
                "session_count": len(sessions),
                "sessions": sessions,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    codex_count = sum(1 for item in sessions if item["source"] == "codex")
    cursor_count = sum(1 for item in sessions if item["source"] == "cursor")
    print(
        json.dumps(
            {
                "total": len(sessions),
                "codex": codex_count,
                "cursor": cursor_count,
                "output": str(OUT),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
