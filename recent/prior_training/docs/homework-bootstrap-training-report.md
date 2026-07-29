# 作业级标注 Bootstrap 训练报告

> **性质**：engineering / homework bootstrap  
> **不是**冻结验收金标，**不得**据此宣称中文 offline ≥98% 验收通过。  
> **语种目标**：当前仅中文；英/印地/印尼不纳入本期验收。

生成日期：2026-07-22

---

## 1. 做了什么

1. 将五份已复审标注 CSV（排除 `NEEDS_REVIEW`）转为 `SmsRecord` JSONL  
2. 与合成 `synthetic_v2.jsonl` 混合后跑 group 切分 + 泄漏门禁  
3. Hard-label 训练 Byte TextCNN（无 teacher logits；3 epoch）

---

## 2. 关键路径

| 产物 | 路径 |
|------|------|
| 转换脚本 | `training/scripts/convert_annotation_csv_to_jsonl.py` |
| 标注 raw | `training/data/raw/annotated_homework_bootstrap.jsonl`（gitignore） |
| 转换摘要 | `training/data/manifests/annotated_bootstrap_summary.json` |
| 切分清单 | `training/data/manifests/dataset_manifest.json` |
| 泄漏审计 | `training/reports/metrics/dataset_leakage.json` |
| 学生配置 | `training/configs/student_homework_bootstrap.yaml` |
| Keras 模型 | `training/artifacts/student_homework_bootstrap/sms_bytecnn_fp32.keras` |
| 蒸馏清单 | `training/artifacts/student_homework_bootstrap/distill_manifest.json` |
| Val 指标 | `training/reports/metrics/student_distill.json` |

Make 入口：

```bash
make prepare-annotation-bootstrap
# 然后（需 .venv + TensorFlow）：
PYTHONPATH=training .venv/Scripts/python training/scripts/distill_student.py \
  --config training/configs/student_homework_bootstrap.yaml --hard-only
```

---

## 3. 数据规模（本轮）

| 阶段 | 数量 |
|------|------|
| 标注可训四类（转 JSONL 前） | 10658 |
| 精确/归一去重去掉 | 3135 + 8 |
| train / val / test（含 train 增强） | 10305 / 811 / 819 |
| 泄漏审计 | **PASS** |

语种注意：`iiitd` 记为 `hi`，正文为 Hinglish/en-IN，**无天城文**。

---

## 4. 验证集指标（homework，非冻结测）

来自 mixed processed validation（811 条），hard-only 3 epoch：

| 指标 | 值 |
|------|-----|
| accuracy | 0.887 |
| macro_f1 | 0.837 |
| TRANSACTION f1 | 0.908 |
| AD f1 | 0.914 |
| HARASS f1 | 0.754 |
| FRAUD f1 | 0.770 |

`distill_manifest.status = OK`（未单类坍塌）。

---

## 5. 明确未完成 / 禁止宣称

- 无双人一致性金标；无中文每类 ≥500 冻结测试集  
- 未跑 teacher 软标签蒸馏、剪枝、量化、设备 PSS  
- 本报告 **不能** 替代主规格正式验收报告  

后续（本批不做）：中文冻结双人验收集；英/印地/印尼暂缓。
