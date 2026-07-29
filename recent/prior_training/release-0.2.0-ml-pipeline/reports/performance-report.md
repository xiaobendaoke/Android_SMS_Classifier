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
