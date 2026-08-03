#!/usr/bin/env python3
"""Call an xfyun OpenAI-compatible model without persisting credentials."""
from __future__ import annotations

import argparse
import ast
from pathlib import Path

from openai import OpenAI


BASE_URL = "https://maas-api.cn-huabei-1.xf-yun.com/v2"


def api_key_from_demo(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    constants: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = node.value.value
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "OpenAI":
            continue
        for keyword in node.keywords:
            if keyword.arg == "api_key" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                return keyword.value.value
            if keyword.arg == "api_key" and isinstance(keyword.value, ast.Name) and keyword.value.id in constants:
                return constants[keyword.value.id]
    raise ValueError("api_key not found in supplied xfyun demo")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo-config", required=True, type=Path)
    parser.add_argument("--model", required=True, choices=("xopglm52", "xopdeepseekv4flash"))
    parser.add_argument("--prompt", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    client = OpenAI(api_key=api_key_from_demo(args.demo_config), base_url=BASE_URL, timeout=args.timeout, max_retries=0)
    response = client.chat.completions.create(
        model=args.model,
        messages=[{"role": "user", "content": args.prompt.read_text(encoding="utf-8")}],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("xfyun response did not contain message content")
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
