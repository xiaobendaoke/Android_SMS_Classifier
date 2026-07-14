# 训练数据目录

原始短信数据**不得**提交到 Git 仓库。

## 目录说明

| 目录 | 内容 |
|------|------|
| `raw/` | 原始来源文件（本地 only） |
| `interim/` | 清洗中间产物 |
| `processed/` | train/val/test JSONL |
| `manifests/` | 带 SHA256 的数据与模型 manifest |

## JSONL 记录格式

见主规格第 9.1 节。每条样本包含 `id`、`text`、`label`、`language`、`source`、`template_group`、`split` 等字段。

## 获取数据

仅使用主规格第 9.2 节列出的已批准来源，并通过 `scripts/audit_sources.py` 记录许可证与哈希。
