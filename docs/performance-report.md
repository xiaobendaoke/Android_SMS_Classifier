# Performance Report (engineering)

**Status:** Partial — local code budget + on-device UI microbench available; formal 4GB/6GB PSS not yet recorded.

## Code path

- Receiver classification timeout: **500 ms** → `action=REVIEW`, message already in system SMS Provider.
- SDK `ClassificationResult.elapsedMs` recorded per classify call.
- App Performance tab: local multi-sample latency p50/p95/p99 + throughput.

## Model

- Asset: `sms_bytecnn_int8.tflite` (~76 KB)
- Keras/TFLite agreement (validation synthetic): **1.0** (`reports/metrics` / training reports)

## Device acceptance (pending)

| Device | RAM | PSS delta | p50 | p95 | Notes |
|--------|-----|-----------|-----|-----|-------|
| TBD | 4GB | | | | Install default SMS role, airplane mode |
| TBD | 6GB | | | | Same script |

Do not mark memory/latency hard metrics PASS until the table above is filled from real devices.

## Emulator measurement (engineering, not formal)

Source: `reports/benchmarks/emulator_pss_latency.json` (instrumented `:benchmark` test on Pixel_9a AVD, API 36, x86_64, 500 synthetic samples).

| Metric | Value |
|--------|-------|
| p50 | 2.4 ms |
| p95 | 2.8 ms |
| p99 | 3.2 ms |
| Throughput | 401.5 msg/s |
| PSS after warm-up | 37,864 KB |
| PSS after run | 59,448 KB |
| Model loaded | yes (`model_available=true`) |

### 4GB / 6GB emulator rerun (2026-08-08)

The same instrumented test was rerun on two AVDs configured with `hw.ramSize=4096` (Pixel_9a) and `hw.ramSize=6144` (Pixel_9a_6G), API 36, x86_64, 500 synthetic samples each:

| Config | p50 | p95 | p99 | Throughput | PSS warm-up | PSS after run |
|---|---|---|---|---|---|---|
| 4GB | 2.4 ms | 3.1 ms | 3.6 ms | 395.7 msg/s | 37,911 KB | 59,504 KB |
| 6GB | 10.1 ms | 41.4 ms | 93.4 ms | 64.9 msg/s | 38,330 KB | 44,228 KB |

Sources: `reports/benchmarks/emulator_4gb_pss_latency.json` and `reports/benchmarks/emulator_6gb_pss_latency.json`. Both configurations stay below the ≤500 ms latency and ≤100 MB PSS engineering budgets, but these are still emulator-only measurements; the formal 4GB/6GB real-device report remains pending.

> Emulator numbers are engineering evidence only. The formal ≤100 MB PSS and ≤500 ms acceptance report requires 4GB/6GB real devices, default SMS role, and airplane mode.
