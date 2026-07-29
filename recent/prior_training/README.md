# prior_training — 历史训练资料与结果归档

> 归档日期：2026-07-28  
> **性质**：中文-only 目标调整前的历史产物，**不作本期验收依据**。

本目录由仓库根路径迁入，活动流水线仍写回：

- `training/artifacts/`（空骨架，重训后写入）
- `training/reports/`（空骨架，重评后写入）
- `training/data/interim/annotation/`（空骨架，重标后写入）
- `training/data/processed/`（空骨架，重切分后写入）
- `reports/release/`（新发布包装填）

## 目录索引

| 子目录 | 原路径 | 内容 |
|--------|--------|------|
| `annotation/` | `training/data/interim/annotation/` | 历史标注 CSV、acceptance_packs、chunks、audit JSON、手标脚本 |
| `interim_misc/` | `training/data/interim/` 杂项 | 如 gitcode preview |
| `processed/` | `training/data/processed/` | 旧 train/val/test/representative/adversarial JSONL |
| `manifests/` | `training/data/manifests/` 历史摘要 | dataset/bootstrap/synthetic/web_candidate（`sources.json` 仍留在原路径） |
| `colab_export_light/` | `colab_export_light/` | Colab 导出：模型、metrics、manifests |
| `training_artifacts/` | `training/artifacts/` | baseline / student / homework_bootstrap（keras、tflite、manifest） |
| `training_reports/` | `training/reports/` | evaluate / distill / quantize / leakage 等 JSON |
| `release-0.2.0-ml-pipeline/` | `reports/release/release-0.2.0-ml-pipeline/` | 旧发布包（APK/AAR/模型） |
| `audit_out/` | `tools/_audit_out/` | 模拟器课题审核导出 |
| `docs/` | 部分 `docs/` | 如 homework-bootstrap 训练报告全文 |

重新训练/标注后请在原路径产出新文件；查阅旧结果请打开本归档。
