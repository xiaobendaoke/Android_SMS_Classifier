# AGENTS.md — Android SMS Classifier

## Project overview

离线端侧四分类短信分类系统。四类: `TRANSACTION`, `AD`, `HARASS`, `FRAUD`（排除 `NEEDS_REVIEW`）。**当前目标语种：仅中文（zh）**；英/印地/印尼暂不作为验收目标。

## Repository structure

| Directory | Contents |
|-----------|----------|
| `android/` | Gradle 多模块: `:app`, `:classifier-sdk`, `:benchmark` |
| `training/` | Python 训练流水线 (`src/` 库, `scripts/` 入口, `configs/` 配置) |
| `tools/` | 发布审核、网络权限检查、SBOM 生成 |
| `docs/` | 架构、标注、隐私、测试、进度文档 |

## Key architecture facts

- **SDK inference pipeline** (classifier-sdk): normalize → rules → byte-encode → TFLite model → decision router
- **Student model**: Byte-level TextCNN (TensorFlow/Keras), INT8 quantized TFLite
- **Teacher model**: bert-base-multilingual-cased (PyTorch/transformers), used only for distillation
- **Android SDK loads TFLite Interpreter via reflection** — JVM unit tests compile without native TFLite libs
- **App manifest has NO `INTERNET` permission** — compliance requirement, enforced by `tools/check_no_network_permission.py`
- **Model output order** (fixed): TRANSACTION → AD → HARASS → FRAUD (`training/src/schema.py:LABEL_ORDER`)

## Environment & setup gotchas

- **Windows Chinese paths**: Gradle can fail with ClassNotFound. `android.overridePathCheck=true` is set in `gradle.properties`. If issues persist, create an ASCII junction: `mklink /J C:\dev\Android_SMS_Classifier "<repo_path>"`
- **gradle-wrapper.jar may be missing** — generate with `cd android && gradle wrapper --gradle-version 8.7` (see `android/README-GRADLE.md`)
- **JDK 17+**, Android SDK API 34, minSdk 26
- **Python heavy deps (PyTorch, TF) are separate**: `training/requirements-train.txt`, NOT `requirements.lock`
- **`requirements.lock`** is only light deps (numpy, PyYAML, pytest) — suitable for eval/audit only

## Commands

### Python
```bash
PYTHONPATH=training python3 -m pytest training/tests -q   # run all Python tests
PYTHONPATH=training python3 -m pytest training/tests/test_byte_encoder.py -q  # single test file
```

### Training pipeline (via Makefile)
```bash
make setup-python    # .venv + pip install -r requirements.lock
make prepare-data    # generate synthetic data → split → validate → check leakage
make train-teacher   # BERT teacher (needs requirements-train.txt deps)
make distill         # Byte TextCNN student (TF)
make prune           # structured channel pruning
make quantize        # INT8 PTQ/QAT → writes artifacts/student/sms_bytecnn_int8.tflite
make verify-model    # Keras vs TFLite consistency check (requires ≥99% agreement)
make evaluate        # frozen test set evaluation
make export-android-assets  # copy model+rules→SDK assets/
make audit-release   # compliance checks + SBOM
make pipeline        # full: prepare → distill → prune → quantize → verify → evaluate
```

### Android
```bash
cd android && ./gradlew test                           # SDK unit tests (no device)
cd android && ./gradlew :app:assembleDebug              # build Debug APK
cd android && ./gradlew :benchmark:connectedDebugAndroidTest  # instrumented benchmarks (device needed)
```

## Compliance constraints

1. **NO `INTERNET` permission** — never add it to any AndroidManifest.xml
2. **Raw SMS data never committed** — `training/data/raw/*`, `processed/*`, `interim/*` are gitignored
3. **Model artifacts never committed** — `.tflite`, `.keras`, `.h5`, `*.ckpt`, `artifacts/` are gitignored
4. **App cannot auto-delete SMS** — suspicious messages go to REVIEW, not permanent deletion

## Data format

JSONL with `SmsRecord` schema (`training/src/schema.py`): `id`, `text`, `label`, `language`, `source`, `source_license`, `sender_group`, `template_group`, `split`, `is_synthetic`, `is_adversarial`, `parent_id`, `annotator_ids`.

Datasets: `training/data/processed/{train,validation,test}.jsonl`

## Testing quirks

- Python tests import `from src.xxx` — requires `PYTHONPATH=training` or run from repo root
- `test_model_student.py` gracefully handles missing TensorFlow (skips with helpful error)
- Android SDK tests are JVM-only (no emulator needed): `classifier-sdk/src/test/`
- Benchmark tests require connected Android device: `benchmark/src/androidTest/`

## Key docs to reference

- 主规格: `Android终端侧离线短信分类识别系统-完整实施与最终审核方案.md`
- `docs/异机测试环境安装清单.md` — cross-machine environment setup
- `docs/colab-training-guide.md` — Colab training setup
- `docs/progress.md` — current status