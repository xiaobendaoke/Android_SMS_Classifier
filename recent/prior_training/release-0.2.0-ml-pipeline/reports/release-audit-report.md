# Release Audit Report

**Release:** 0.2.0-ml-pipeline  
**Date:** 2026-07-16  
**Verdict:** `PASS_ENGINEERING` (synthetic closed-loop) — **NOT** full business acceptance PASS

## P0 checks

| Check | Result |
|-------|--------|
| No `INTERNET` permission | PASS |
| No cloud classification / runtime model download | PASS |
| No automatic permanent SMS deletion | PASS |
| Suspect/Review recoverable to inbox | PASS |

## Artifacts

| Artifact | Status |
|----------|--------|
| Debug APK | Built (`app-debug.apk`) |
| classifier-sdk AAR | Built (`classifier-sdk-release.aar`) |
| INT8 / hybrid TFLite | Present (~76 KB), exported to SDK assets |
| Rules JSON | Bundled |
| SBOM | `reports/audit/dependency_sbom.json` |

## Metrics honesty

| Metric | Claim |
|--------|-------|
| Transaction recall ≥98% | **NOT claimed** — synthetic/small frozen set only |
| Memory ≤100 MB PSS | **Pending** 4GB/6GB device measurement |
| Latency ≤500 ms | Code budget enforced (timeout→REVIEW); device p50/p95 pending formal report |
| Multilingual | Synthetic zh/en/hi/id pipeline exercised; formal report pending real labels |
| Adversarial | Synthetic clean/known/unseen JSONL generated; formal scores pending |

## Residual risks

1. Teacher distillation skipped without local BERT cache.
2. Quantization may be hybrid INT8 (strict full-integer fallback).
3. Non-ASCII Windows path requires ASCII junction for reliable Gradle unit tests.
4. MMS handling remains placeholder.

## Sign-off

Engineering closed-loop complete for demo/review.  
Business hard-metric PASS requires real labeled freeze + device evidence.
