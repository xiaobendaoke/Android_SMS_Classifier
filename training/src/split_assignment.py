"""Immutable split assignment freeze helpers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from .schema import SmsRecord
from .split_groups import connected_group_ids

COMPONENT_ALGORITHM_VERSION = "connected_group_ids_v1"
ASSIGNMENT_VERSION = "1.0.0"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def sha256_ids(ids: Sequence[str]) -> str:
    return sha256_bytes("\n".join(ids).encode("utf-8"))


def compute_freeze_sha256(payload: Mapping[str, Any]) -> str:
    """Recompute freeze_sha256 from a canonical subset of assignment fields."""
    freeze_payload = {
        "component_algorithm_version": payload["component_algorithm_version"],
        "holdout_ids_sha256": payload["holdout_ids_sha256"],
        "seed": payload["seed"],
        "source_shas": payload["source_shas"],
        "splits": {
            name: {
                "count": payload["splits"][name]["count"],
                "ids_sha256": payload["splits"][name]["ids_sha256"],
                "sha256": payload["splits"][name]["sha256"],
            }
            for name in ("train", "validation", "test")
        },
        "version": payload["version"],
    }
    return sha256_bytes(
        json.dumps(freeze_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    )


def collect_ids_from_jsonl(path: Path) -> List[str]:
    """Collect IDs only; callers must not print SMS bodies."""
    ids: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        ids.append(str(payload.get("id", "")))
    return ids


def build_assignment_from_splits(
    split_paths: Mapping[str, Path],
    *,
    seed: int,
    source_shas: Sequence[Mapping[str, str]],
    holdout_ids_sha256: str,
    holdout_manifest_sha256: str,
    code_revision: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a frozen assignment manifest from already-written split JSONL files."""
    splits: Dict[str, Any] = {}
    for split_name in ("train", "validation", "test"):
        path = Path(split_paths[split_name])
        # Load full records only to derive component IDs; never emit bodies.
        from .schema import load_jsonl

        records = load_jsonl(path)
        ids = [record.id for record in records]
        component_map = connected_group_ids(records)
        component_ids = sorted({component_map[idx] for idx in range(len(records))})
        id_to_component = {
            records[idx].id: component_map[idx] for idx in range(len(records))
        }
        splits[split_name] = {
            "count": len(ids),
            "sha256": sha256_file(path),
            "ids_sha256": sha256_ids(ids),
            "ids": ids,
            "component_ids": component_ids,
            "id_to_component": id_to_component,
        }

    payload: Dict[str, Any] = {
        "version": ASSIGNMENT_VERSION,
        "seed": seed,
        "source_shas": list(source_shas),
        "holdout_ids_sha256": holdout_ids_sha256,
        "holdout_manifest_sha256": holdout_manifest_sha256,
        "component_algorithm_version": COMPONENT_ALGORITHM_VERSION,
        "splits": splits,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "code_revision": code_revision,
    }
    payload["freeze_sha256"] = compute_freeze_sha256(payload)
    return payload


def load_assignment(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = compute_freeze_sha256(payload)
    if payload.get("freeze_sha256") != expected:
        raise ValueError(
            f"split assignment freeze_sha256 mismatch: {path} "
            f"(stored={payload.get('freeze_sha256')}, recomputed={expected})"
        )
    return payload


def assignment_id_sets(payload: Mapping[str, Any]) -> Dict[str, Set[str]]:
    return {
        split_name: set(payload["splits"][split_name]["ids"])
        for split_name in ("train", "validation", "test")
    }


def apply_frozen_assignment(
    records: Sequence[SmsRecord],
    payload: Mapping[str, Any],
) -> Dict[str, List[SmsRecord]]:
    """Assign records into frozen splits. Fails on missing/extra/unknown IDs."""
    id_sets = assignment_id_sets(payload)
    all_assigned = set().union(*id_sets.values())
    by_id = {record.id: record for record in records}
    if len(by_id) != len(records):
        raise ValueError("duplicate record ids before applying frozen assignment")

    unknown = sorted(set(by_id) - all_assigned)
    missing = sorted(all_assigned - set(by_id))
    if unknown:
        raise ValueError(
            "records not present in frozen assignment: "
            + ", ".join(unknown[:20])
            + (f" (+{len(unknown) - 20} more)" if len(unknown) > 20 else "")
        )
    if missing:
        raise ValueError(
            "frozen assignment ids missing from records: "
            + ", ".join(missing[:20])
            + (f" (+{len(missing) - 20} more)" if len(missing) > 20 else "")
        )

    result: Dict[str, List[SmsRecord]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for split_name in ("train", "validation", "test"):
        for record_id in payload["splits"][split_name]["ids"]:
            record = by_id[record_id]
            clone = SmsRecord(**{**record.to_dict(), "split": split_name})
            result[split_name].append(clone)
    return result


def verify_split_file_against_assignment(
    path: Path,
    payload: Mapping[str, Any],
    split_name: str,
) -> List[str]:
    """Silent integrity check: IDs + file SHA only."""
    errors: List[str] = []
    expected = payload["splits"][split_name]
    actual_sha = sha256_file(path)
    if actual_sha != expected["sha256"]:
        errors.append(
            f"{split_name}: sha256 changed "
            f"(expected={expected['sha256']}, actual={actual_sha})"
        )
    actual_ids = collect_ids_from_jsonl(path)
    if actual_ids != expected["ids"]:
        errors.append(f"{split_name}: id membership/order differs from frozen assignment")
    if len(actual_ids) != expected["count"]:
        errors.append(
            f"{split_name}: count={len(actual_ids)} expected={expected['count']}"
        )
    return errors
