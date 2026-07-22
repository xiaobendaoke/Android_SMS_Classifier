.PHONY: help setup-python audit-data prepare-data prepare-annotation-bootstrap \
	train-baseline train-teacher \
	distill prune quantize verify-model evaluate export-android-assets \
	android-test android-build benchmark audit-release package-release \
	check-leakage pipeline

ROOT := $(CURDIR)
PYTHON := PYTHONPATH=$(ROOT)/training python3
VENV := $(ROOT)/.venv
GRADLE := cd $(ROOT)/android && ./gradlew

help:
	@echo "Android 离线短信分类 — Make 目标"
	@echo ""
	@echo "  setup-python          创建 .venv 并安装 training/requirements.lock"
	@echo "  audit-data            数据来源与许可证审计 + 切分泄漏检查"
	@echo "  prepare-data          生成合成 raw + group 切分 + 泄漏门禁"
	@echo "  prepare-annotation-bootstrap  标注 CSV→JSONL + 与合成混合切分（作业级，非冻结）"
	@echo "  check-leakage         仅检查 train/val/test 泄漏"
	@echo "  train-baseline        训练 n-gram 基线"
	@echo "  train-teacher         微调 bert-base-multilingual-cased 教师"
	@echo "  distill               蒸馏 Byte TextCNN 学生"
	@echo "  distill-homework-bootstrap  作业级 hard-only 学生（标注+合成，非冻结）"
	@echo "  prune                 结构化通道剪枝"
	@echo "  quantize              INT8 PTQ/QAT 量化"
	@echo "  verify-model          Keras 与 TFLite 一致性验证"
	@echo "  evaluate              冻结测试集评测（默认 TFLite）"
	@echo "  export-android-assets 导出模型与规则到 classifier-sdk"
	@echo "  android-test          Gradle 单元测试"
	@echo "  android-build         构建 app Debug APK"
	@echo "  benchmark             仪器化性能基准"
	@echo "  audit-release         发布前合规审核"
	@echo "  package-release       打包发布产物"
	@echo "  pipeline              prepare → distill → prune → quantize → verify → evaluate"
	@echo ""
	@echo "主规格: Android终端侧离线短信分类识别系统-完整实施与最终审核方案.md"

setup-python:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r training/requirements.lock

audit-data:
	$(PYTHON) training/scripts/audit_sources.py
	$(PYTHON) training/scripts/check_split_leakage.py

prepare-data:
	$(PYTHON) training/scripts/generate_synthetic_dataset.py
	$(PYTHON) training/scripts/build_dataset.py --augment-train
	$(PYTHON) training/scripts/build_adversarial_slices.py
	$(PYTHON) training/scripts/validate_labels.py
	$(PYTHON) training/scripts/check_split_leakage.py

# Homework bootstrap: audited annotation CSVs + synthetic raw → processed splits.
# NOT frozen acceptance. Requires local interim CSVs under data/interim/annotation/.
prepare-annotation-bootstrap:
	$(PYTHON) training/scripts/convert_annotation_csv_to_jsonl.py
	$(PYTHON) training/scripts/generate_synthetic_dataset.py
	$(PYTHON) training/scripts/build_dataset.py --augment-train
	$(PYTHON) training/scripts/build_adversarial_slices.py
	$(PYTHON) training/scripts/validate_labels.py
	$(PYTHON) training/scripts/check_split_leakage.py

check-leakage:
	$(PYTHON) training/scripts/check_split_leakage.py

train-baseline:
	$(PYTHON) training/scripts/train_baseline.py

train-teacher:
	$(PYTHON) training/scripts/train_teacher.py

distill:
	$(PYTHON) training/scripts/distill_student.py

# Homework bootstrap hard-label student (annotation CSV + synthetic). NOT frozen acceptance.
distill-homework-bootstrap:
	$(PYTHON) training/scripts/distill_student.py \
		--config training/configs/student_homework_bootstrap.yaml --hard-only

prune:
	$(PYTHON) training/scripts/prune_channels.py

quantize:
	$(PYTHON) training/scripts/quantize_int8.py

verify-model:
	$(PYTHON) training/scripts/verify_tflite.py

evaluate:
	$(PYTHON) training/scripts/evaluate.py --mode auto

export-android-assets:
	$(PYTHON) training/scripts/export_android_assets.py

android-test:
	$(GRADLE) test

android-build:
	$(GRADLE) :app:assembleDebug

benchmark:
	$(GRADLE) :benchmark:connectedDebugAndroidTest

audit-release:
	python3 tools/audit_release.py
	python3 tools/check_no_network_permission.py
	python3 tools/check_no_sensitive_logs.py
	python3 tools/check_model_ops.py
	python3 tools/generate_sbom.py

package-release:
	python3 tools/audit_release.py --package
	python3 tools/generate_sbom.py

pipeline:
	$(MAKE) prepare-data
	$(MAKE) distill
	$(MAKE) prune
	$(MAKE) quantize
	$(MAKE) verify-model
	$(MAKE) evaluate
	$(MAKE) export-android-assets
	$(MAKE) audit-data
