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

> Emulator numbers are engineering evidence only. The formal ≤100 MB PSS and ≤500 ms acceptance report requires 4GB/6GB real devices, default SMS role, and airplane mode.
