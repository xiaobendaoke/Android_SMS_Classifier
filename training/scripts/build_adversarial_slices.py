#!/usr/bin/env python3
"""Build clean / known / unseen adversarial eval slices from frozen test set."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

SEED = 42
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.schema import load_jsonl  # noqa: E402
from src.train_utils import set_seed  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate adversarial eval slices from test JSONL.")
    p.add_argument(
        "--test",
        type=Path,
        default=ROOT / "data" / "processed" / "test.jsonl",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "adversarial",
    )
    p.add_argument("--seed", type=int, default=SEED)
    return p


def write_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    set_seed(args.seed)
    if not args.test.exists():
        print(f"Test set missing: {args.test}", file=sys.stderr)
        return 1

    records = [r.to_dict() for r in load_jsonl(args.test)]
    clean = [dict(r, is_adversarial=False) for r in records]

    known = []
    for r in clean:
        clone = dict(r)
        clone["id"] = f"{r['id']}-zw"
        clone["text"] = str(r["text"]).replace(" ", "\u200b ")
        clone["is_adversarial"] = True
        clone["parent_id"] = r["id"]
        known.append(clone)

    unseen = []
    for r in clean:
        clone = dict(r)
        clone["id"] = f"{r['id']}-leet"
        text = str(r["text"])
        for a, b in (("a", "@"), ("e", "3"), ("o", "0"), ("微", "薇"), ("信", "伈")):
            text = text.replace(a, b)
        clone["text"] = text
        clone["is_adversarial"] = True
        clone["parent_id"] = r["id"]
        unseen.append(clone)

    write_jsonl(args.output_dir / "clean.jsonl", clean)
    write_jsonl(args.output_dir / "known_perturbation.jsonl", known)
    write_jsonl(args.output_dir / "unseen_perturbation.jsonl", unseen)
    print(
        json.dumps(
            {
                "clean": len(clean),
                "known": len(known),
                "unseen": len(unseen),
                "output_dir": str(args.output_dir),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
