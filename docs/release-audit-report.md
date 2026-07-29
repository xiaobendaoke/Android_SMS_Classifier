# Release Audit Report

**Release:** 0.2.1-p0-fixes  
**Date:** 2026-07-16  
**Verdict:** `PASS_ENGINEERING` (synthetic closed-loop after P0 leakage fixes) — **NOT** full business acceptance PASS

## P0 checks

| Check | Result |
|-------|--------|
| No `INTERNET` permission | PASS |
| No cloud classification / runtime model download | PASS |
| No automatic permanent SMS deletion | PASS |
| Suspect/Review recoverable to inbox | PASS |
| Dataset train/val/test group leakage | PASS (`dataset_leakage.json`) |
| Lock-screen notification hides body/OTP | PASS (code path; device confirm pending) |

## Artifacts

| Artifact | Status |
|----------|--------|
| Debug APK | Built (`app-debug.apk`) |
| classifier-sdk AAR | Built (`classifier-sdk-release.aar`) |
| INT8 / hybrid TFLite | Present (~76 KB); may be hybrid — re-export after retrain |
| Rules JSON | Bundled (incl. HARASS) |
| SBOM | `reports/audit/dependency_sbom.json` |

## Metrics honesty

| Metric | Claim |
|--------|-------|
| Transaction recall ≥98% | **NOT claimed** — synthetic/small frozen set only |
| Memory ≤100 MB PSS | **Pending** 4GB/6GB device measurement |
| Latency ≤500 ms | Code budget enforced (timeout→REVIEW); device p50/p95 pending formal report |
| Language scope | **Chinese only** for current acceptance; en/hi/id deferred |
| Adversarial | Slices regenerated via `build_adversarial_slices.py`; formal scores pending |

## Residual risks

1. Teacher distillation skipped without local BERT cache.
2. Quantization may be hybrid INT8 (strict full-integer fallback).
3. Non-ASCII Windows path requires ASCII junction for reliable Gradle unit tests.
4. MMS handling remains placeholder.
5. Existing TFLite was trained before leakage fix — re-run distill→prune→quantize on current manifest.

## Sign-off

| 审核角色 | 审核内容 | 结论 | 姓名/编号 | 日期 |
|---|---|---|---|---|
| Android 工程审核 | 默认角色、收发、Provider、恢复 | PENDING |  |  |
| 模型审核 | 蒸馏、剪枝、量化、一致性 | PENDING |  |  |
| 数据审核 | 来源、许可、切分、标注 | PENDING（合成泄漏门禁 PASS） |  |  |
| 隐私安全审核 | 离线、权限、日志、存储 | PENDING |  |  |
| 性能审核 | 4GB/6GB 真机 | PENDING |  |  |
| 项目负责人 | 最终放行 | FAIL / 未放行 |  |  |
