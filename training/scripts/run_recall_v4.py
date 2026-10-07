#!/usr/bin/env python3
"""Run the dual-head, transaction-protected Recall v4 pipeline."""
from __future__ import annotations

try:
    from scripts.run_recall_v3 import main
except ImportError:  # Direct execution from training/scripts.
    from run_recall_v3 import main


if __name__ == "__main__":
    raise SystemExit(main())
