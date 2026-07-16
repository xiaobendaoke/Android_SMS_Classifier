# Google Colab 训练与微调操作手册

> 适用版本：仓库 `0.2.1-p0-fixes` 及之后  
> 目标：在 Colab 上完成 **教师 BERT 微调 → 学生蒸馏 → 剪枝 → INT8 量化 → 验证**，再把产物拷回 Windows 本机导出 APK。  
> 主规格仍以根目录《完整实施与最终审核方案》为准。

---

## 0. 开始前必读（合规）

1. **禁止把真实用户短信、私有标注集、含手机号/OTP 的正文上传到 Colab / Drive / Hugging Face。**  
   Colab 属于公网第三方算力；当前仓库合成数据可以上云；真实业务数据只能在公司批准的内网训练机跑。
2. 教师模型 `bert-base-multilingual-cased` 来自 Hugging Face【第三方】。下载后记录许可证与文件哈希；优先公司内网镜像。
3. App / SDK 始终无 `INTERNET`。训练可以联网下载权重，**运行时分类绝不联网**。
4. 合成数据上的指标 **不能** 用来宣称事务召回 ≥98%。

如果你只有合成数据：可以完整走通工程。  
如果你有真实标注数据：请在内网训练，不要用公共 Colab。

---

## 1. 你需要做的事总览

| 步骤 | 在哪做 | 做什么 | 产出 |
|------|--------|--------|------|
| A | Windows 本机 | 生成无泄漏合成数据 / 准备脱敏训练集 | `training/data/processed/*.jsonl` + manifest |
| B | Google Colab | 装依赖、下载 BERT、微调教师、蒸馏剪枝量化 | `artifacts/`、`*.tflite`、metrics JSON |
| C | Windows 本机 | 拷回产物、导出 SDK assets、编译 APK | APK / AAR |
| D | 真机 | 默认短信角色、飞行模式、PSS/时延 | `docs/performance-report.md` |

推荐分工：**数据准备与 Android 在本机；重训练在 Colab。**

---

## 2. 本机先准备数据（Windows）

在仓库根目录打开 PowerShell：

```powershell
cd "C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"

# 可选：建虚拟环境
python -m venv .venv
.\.venv\Scripts\activate
pip install -U pip
pip install -r training\requirements.lock

$env:PYTHONPATH = "training"

# 1) 生成合成 raw（无真实短信）
python training\scripts\generate_synthetic_dataset.py --per-label-lang 40

# 2) group 切分 + 训练增强 + 泄漏门禁
python training\scripts\build_dataset.py --augment-train

# 3) 对抗评测切片
python training\scripts\build_adversarial_slices.py

# 4) 校验
python training\scripts\validate_labels.py
python training\scripts\check_split_leakage.py
```

成功标志：

- `training/reports/metrics/dataset_leakage.json` 里 `"status": "PASS"`
- `training/data/manifests/dataset_manifest.json` 的 count/sha256 与 `processed/*.jsonl` 一致

**打包上传到 Colab 的最小包（不要塞私有短信）：**

```
training/
  configs/
  scripts/
  src/
  tests/
  requirements.lock
  requirements-train.txt
  data/
    processed/          # train/validation/test/representative/adversarial
    manifests/
  rules/                # 如有
```

也可用整个 Git 仓库 zip，但务必确认没有 `training/data/raw` 里的私有文件。

---

## 3. 打开 Colab 并开启 GPU

1. 打开 [Google Colab](https://colab.research.google.com/)【第三方】
2. 菜单 **Runtime → Change runtime type → Hardware accelerator → GPU**（T4 即可）
3. 新建 Notebook，按下面单元格顺序执行

---

## 4. Colab Notebook 逐步执行

### 单元格 1：环境检查

```python
!nvidia-smi
import sys
print(sys.version)
```

建议 Python 3.10/3.11。若 Colab 默认版本过新导致 TF 装不上，可换旧 runtime 或按报错装对应 wheel。

### 单元格 2：上传仓库并解压

两种方式任选：

**方式 A：上传 zip**

```python
from google.colab import files
uploaded = files.upload()  # 选择 Android_SMS_Classifier.zip 或 training_pack.zip
!unzip -q Android_SMS_Classifier.zip -d /content/
# 按实际解压目录调整：
%cd /content/Android_SMS_Classifier
```

**方式 B：挂载 Google Drive**（同样禁止放私有短信）

```python
from google.colab import drive
drive.mount('/content/drive')
%cd /content/drive/MyDrive/Android_SMS_Classifier
```

### 单元格 3：安装训练依赖

```python
!pip install -U pip
!pip install -r training/requirements.lock
!pip install -r training/requirements-train.txt

# 可选：确认版本
import tensorflow as tf, transformers
print("TF", tf.__version__)
print("transformers", transformers.__version__)
print("GPU", tf.config.list_physical_devices("GPU"))
```

如果 `tensorflow` 安装很慢/失败：

```python
!pip install "tensorflow[and-cuda]>=2.16" transformers tensorflow-model-optimization scikit-learn PyYAML numpy
```

### 单元格 4：下载教师模型（BERT）

默认模型：

```text
google-bert/bert-base-multilingual-cased
【第三方】Hugging Face
许可证：Apache-2.0（以模型卡为准）
体积：约 700MB 量级
```

**推荐做法（先下载到本地目录，训练时用 `--model-path`，可复现）：**

```python
from transformers import AutoTokenizer, TFAutoModelForSequenceClassification
from pathlib import Path

MODEL_ID = "google-bert/bert-base-multilingual-cased"
CACHE = Path("/content/hf_cache/bert-base-multilingual-cased")
CACHE.mkdir(parents=True, exist_ok=True)

# 首次联网下载并落盘
tok = AutoTokenizer.from_pretrained(MODEL_ID)
# 先按 4 分类头下载骨架（微调脚本会再加载）
mdl = TFAutoModelForSequenceClassification.from_pretrained(MODEL_ID, num_labels=4)
tok.save_pretrained(CACHE)
mdl.save_pretrained(CACHE)
print("Saved to", CACHE)
```

若公司有内网镜像：把镜像目录上传到 Colab，跳过 Hugging Face 下载，直接：

```bash
--model-path /content/hf_cache/bert-base-multilingual-cased
```

记录哈希（验收用）：

```python
import hashlib
from pathlib import Path

def sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(path.rglob("*")):
        if f.is_file():
            h.update(f.relative_to(path).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()

print(sha256_dir(CACHE))
```

把打印出的哈希写进 `docs/model-card.md` 或 `training/data/manifests/sources.json` 备注。

### 单元格 5：确认数据无泄漏

```python
import os
os.environ["PYTHONPATH"] = "training"

!python training/scripts/check_split_leakage.py
!python training/scripts/validate_labels.py
```

必须看到 `Leakage audit PASS`。否则先修数据，不要训练。

### 单元格 6：微调教师（核心）

```python
!python training/scripts/train_teacher.py \
  --model-path /content/hf_cache/bert-base-multilingual-cased \
  --seed 42
```

说明：

- 配置文件：`training/configs/teacher.yaml`
- 默认 `epochs=3`，`batch_size=16`，`max_length=512`
- Colab T4 显存不够时，改 YAML 或临时：

```python
# 快速冒烟（可选）
!python training/scripts/train_teacher.py \
  --model-path /content/hf_cache/bert-base-multilingual-cased \
  --max-samples 200 \
  --seed 42
```

成功标志：

| 文件 | 含义 |
|------|------|
| `training/artifacts/teacher/` | 微调后的教师 checkpoint |
| `training/artifacts/teacher/teacher_logits_train.npz` | 训练集 soft labels |
| `training/data/manifests/teacher_logits_manifest.json` | 蒸馏入口清单 |
| `training/data/manifests/teacher_manifest.json` | 教师元数据 |
| `training/reports/metrics/teacher.json` | 验证指标 |

**没有 `teacher_logits_manifest.json`，后面蒸馏就不是真蒸馏。**

### 单元格 7：蒸馏学生 Byte TextCNN（不要加 `--hard-only`）

```python
!python training/scripts/distill_student.py --seed 42
```

成功标志：

- 日志出现 `Distillation: alpha=... teacher_logits=...`
- `training/artifacts/student/sms_bytecnn_fp32.keras`
- `training/reports/metrics/student_distill.json`
- `distill_manifest.json` 里 `"used_distillation": true`、`"status": "OK"`

如果退出码 3（塌缩成单类）：

1. 加大 `--per-label-lang` 重新准备数据  
2. 确认四类样本都有  
3. 不要继续 prune/quantize 坏模型

### 单元格 8：结构化剪枝

```python
!python training/scripts/prune_channels.py --seed 42
```

会按 `0.25 → 0.15 → 0.10` 尝试；超预算会 `FAIL_BUDGET` 并拒绝交付劣质剪枝模型。

产出：`training/artifacts/student/sms_bytecnn_pruned.keras`

### 单元格 9：INT8 量化

```python
!python training/scripts/quantize_int8.py --seed 42
```

看 `training/reports/metrics/quantize.json`：

- `"quantization": "full_integer_int8"` → 可写 metadata INT8  
- `"quantization": "hybrid_fallback"` → **不能**谎称全整型 INT8；可再试 QAT：

```python
!python training/scripts/quantize_int8.py --mode qat --seed 42
```

### 单元格 10：一致性验证 + TFLite 评测

```python
!python training/scripts/verify_tflite.py --seed 42
!python training/scripts/evaluate.py --mode tflite --seed 42
```

注意：

- `evaluate.py` 不要再默默用规则刷事务召回  
- 合成集上的 recall **不能**写进最终 PASS

### 单元格 11：打包下载回本机

```python
!mkdir -p /content/colab_export
!cp -r training/artifacts /content/colab_export/
!cp -r training/reports/metrics /content/colab_export/metrics
!cp -r training/data/manifests /content/colab_export/manifests
!cp training/artifacts/student/sms_bytecnn_int8.tflite /content/colab_export/ 2>/dev/null || true

%cd /content
!zip -r colab_export.zip colab_export
from google.colab import files
files.download("colab_export.zip")
```

---

## 5. 拷回 Windows 后怎么接 Android

假设你把 `colab_export.zip` 解压到仓库旁，然后：

```powershell
cd "C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"

# 覆盖训练产物（按你解压路径改）
Copy-Item -Recurse -Force ..\colab_export\artifacts\* training\artifacts\
Copy-Item -Recurse -Force ..\colab_export\metrics\* training\reports\metrics\
Copy-Item -Recurse -Force ..\colab_export\manifests\* training\data\manifests\

$env:PYTHONPATH = "training"
python training\scripts\export_android_assets.py
```

导出后检查：

- `android/classifier-sdk/src/main/assets/model/sms_bytecnn_int8.tflite`
- `android/classifier-sdk/src/main/assets/model/model_metadata.json`  
  （`quantization` 字段应与 `quantize.json` 一致；hybrid 时为 `HYBRID`）

编译 APK（路径含中文时建议 ASCII junction）：

```powershell
# 管理员 CMD 一次即可：
# mklink /J C:\dev\Android_SMS_Classifier "C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"

cd C:\dev\Android_SMS_Classifier\android
.\gradlew.bat :classifier-sdk:test :app:assembleDebug
```

---

## 6. 教师微调参数怎么改（可选）

编辑 `training/configs/teacher.yaml`：

```yaml
model:
  hub_id: google-bert/bert-base-multilingual-cased
  max_length: 128          # Colab 显存紧就改 128；正式可 256/512
training:
  batch_size: 8            # OOM 就降到 4/8
  learning_rate: 2.0e-5
  epochs: 3
```

经验：

| 现象 | 处理 |
|------|------|
| CUDA OOM | 降 `batch_size`、`max_length` |
| 教师 val 很差 | 先检查数据是否四类均衡、泄漏是否 PASS |
| 蒸馏仍塌缩 | 确认用了 logits；不要 `--hard-only`；加数据 |
| 量化变 hybrid | 试 QAT；或降低剪枝率后再 PTQ |

---

## 7. 你不需要在 Colab 做的事

- 不要在 Colab 编译 Android APK（太折腾，回 Windows）
- 不要上传系统短信库导出
- 不要把最终业务 PASS 建立在 Colab 合成指标上
- 不要为了刷召回把低置信样本改成 TRANSACTION

---

## 8. 验收 checklist（你自己勾）

- [ ] `dataset_leakage.json` = PASS  
- [ ] 教师用了本地 `--model-path`，并记录模型哈希  
- [ ] `teacher_logits_manifest.json` 存在  
- [ ] `distill_manifest.json` 中 `used_distillation=true`  
- [ ] `student_distill.json` 不是“全预测 TRANSACTION”  
- [ ] `quantize.json` 标明 full INT8 或 hybrid  
- [ ] `verify_tflite.py` PASS  
- [ ] `evaluate.py --mode tflite` 已跑，且文档未谎称 ≥98%  
- [ ] 本机 `export_android_assets.py` 成功  
- [ ] Debug APK 可装，飞行模式可分类  

---

## 9. 一键命令对照（Colab 里）

```bash
export PYTHONPATH=training

python training/scripts/check_split_leakage.py
python training/scripts/train_teacher.py --model-path /content/hf_cache/bert-base-multilingual-cased
python training/scripts/distill_student.py
python training/scripts/prune_channels.py
python training/scripts/quantize_int8.py
python training/scripts/verify_tflite.py
python training/scripts/evaluate.py --mode tflite
```

等价于本机 Makefile 的训练段，但教师必须先成功。

---

## 10. 出问题怎么问我

把下面几样贴回来即可（**不要贴短信正文**）：

1. Colab 报错最后 30 行  
2. `teacher_manifest.json` / `distill_manifest.json` / `quantize.json` 内容  
3. `dataset_leakage.json` 的 status  
4. GPU 型号与 `tf.__version__`
