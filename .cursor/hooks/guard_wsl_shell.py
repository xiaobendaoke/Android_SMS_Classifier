#!/usr/bin/env python3
"""Deny unsafe WSL/PowerShell agent shell patterns before execution."""

from __future__ import annotations

import json
import re
import sys

WSL_RE = re.compile(r"(?i)(^|[;&|]\s*)wsl(\.exe)?\b")
BASH_LC_RE = re.compile(r"(?i)bash(\.exe)?\s+-l?c\b")
# Any non-ASCII in a wsl command line is a Chinese-path footgun on this machine.
NON_ASCII_RE = re.compile(r"[^\x00-\x7f]")
# PowerShell expands $var in double quotes and sometimes in unquoted tokens.
DOLLAR_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*|\$\{|\$\(")
SAFE_LAUNCHER_RE = re.compile(
    r"(?i)wsl_run\.ps1|tools\\wsl_run\.ps1|tools/wsl_run\.ps1"
)


def _deny(agent_message: str, user_message: str | None = None) -> dict:
    out = {
        "permission": "deny",
        "agent_message": agent_message,
    }
    if user_message:
        out["user_message"] = user_message
    return out


def evaluate(command: str) -> dict:
    cmd = command or ""
    if not WSL_RE.search(cmd):
        return {"permission": "allow"}

    if SAFE_LAUNCHER_RE.search(cmd):
        # Launcher itself may contain $ as PowerShell params; that is OK.
        return {"permission": "allow"}

    if NON_ASCII_RE.search(cmd):
        return _deny(
            "BLOCKED: wsl command contains non-ASCII (likely a Chinese Windows path). "
            "Use ASCII only via: "
            "powershell -NoProfile -File C:\\dev\\Android_SMS_Classifier\\tools\\wsl_run.ps1 "
            "-RelPath <relative\\script.sh>",
            "中文路径在 WSL 里解析失败，已拦截。请用 tools\\wsl_run.ps1 经 ASCII 路径启动。",
        )

    # Inline bash -c/-lc with $ is the classic PowerShell-eats-$ failure mode.
    if BASH_LC_RE.search(cmd) and DOLLAR_RE.search(cmd):
        return _deny(
            "BLOCKED: PowerShell will eat $ in this wsl/bash -lc one-liner. "
            "Write a .sh file and run: "
            "powershell -NoProfile -File C:\\dev\\Android_SMS_Classifier\\tools\\wsl_run.ps1 "
            "-RelPath <relative\\script.sh>",
            "PowerShell 会吃掉 $，已拦截内联 bash。请改用独立脚本 + wsl_run.ps1。",
        )

    # Long inline bash bodies are fragile even without $; nudge to launcher.
    if BASH_LC_RE.search(cmd) and len(cmd) > 280:
        return _deny(
            "BLOCKED: long inline wsl/bash -lc is fragile under PowerShell. "
            "Write a script and use tools\\wsl_run.ps1.",
            "过长的内联 wsl/bash 已拦截。请改用独立 bootstrap 脚本。",
        )

    return {"permission": "allow"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # Fail open if hook input is malformed.
        json.dump({"permission": "allow"}, sys.stdout)
        return 0

    command = ""
    if isinstance(payload, dict):
        command = str(payload.get("command") or "")

    json.dump(evaluate(command), sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
