#!/usr/bin/env python3
"""DEPRECATED: do not use for dataset builds.

This legacy generator assigned splits with i % 3 while keeping the same
template_group across variants, causing train/val/test leakage.

Use instead:
  python training/scripts/generate_synthetic_dataset.py
  python training/scripts/build_dataset.py
  python training/scripts/check_split_leakage.py
"""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description="DEPRECATED leaky synthetic generator — refuses to run."
    )


def main(argv=None) -> int:
    build_parser().parse_args(argv)
    print(
        "ERROR: _generate_synthetic_data.py is deprecated due to template_group "
        "cross-split leakage. Use generate_synthetic_dataset.py + build_dataset.py.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
