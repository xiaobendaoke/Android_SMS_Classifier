# 验收标注下一步：中文缺口 / HARASS 待标 / 冻结双人任务

> 生成工具在 `training/scripts/`；**新** CSV 产物写回 `training/data/interim/annotation/`（当前为空占位）。  
> **历史标注包**已归档：`recent/prior_training/annotation/`（含旧 acceptance_packs）。  
> **这些包本身不能宣称中文 offline ≥98% PASS**——冻结金标要等双人标完并记 SHA。  
> **当前语种目标：仅中文（zh）**；英/印地/印尼不纳入本期验收。

## 1. 一键生成

```powershell
cd "C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
$env:PYTHONPATH = "training"

python training/scripts/report_label_gaps.py
python training/scripts/prepare_harass_id_relabel_packs.py
python training/scripts/prepare_freeze_dual_annotation_packs.py
```

或：`make prepare-acceptance-packs`

> 说明：脚本名里若仍含 `id`/`hi`，仅为历史工具残留；**验收只看中文格子**。

## 2. 产物位置

| 产物 | 路径 |
|------|------|
| 缺口表 JSON（新跑写入） | `training/reports/metrics/label_gap_report.json` |
| 历史缺口表（归档） | `recent/prior_training/training_reports/metrics/label_gap_report.json` |
| HARASS 待标（新跑） | `training/data/interim/annotation/acceptance_packs/...` |
| 历史 HARASS/冻结包 | `recent/prior_training/annotation/acceptance_packs/` |
| 冻结主池（新跑） | `.../acceptance_packs/freeze/freeze_pool.csv` |
| 标注人 A/B（新跑） | `.../freeze/freeze_annotator_A.csv` / `_B.csv` |
| 冻结缺口（新跑） | `.../freeze/freeze_shortfall.json` |

## 3. 你怎么标

1. **HARASS（中文）包**：只填 `label` + `annotator`；不确定就 `NEEDS_REVIEW`。  
2. **冻结包**：优先筛 `language=zh`；A、B 各拿一份，互不偷看，也不要看 `prior_label`。  
3. 两人标完后：相同标签可进候选金标；冲突交给第三人仲裁判定。  
4. 看 `freeze_shortfall.json`：只盯 **zh × 四类** 的 `shortfall>0`；en/hi/id 缺口本期可忽略。

## 4. 标完后怎么回流训练

把新 `label` 写回对应的 `*_all_suggested.csv`（或让助手做合并），然后：

```powershell
python training/scripts/convert_annotation_csv_to_jsonl.py
make prepare-annotation-bootstrap
```

冻结金标应单独存（不要混进 homework bootstrap），并在 `evaluate` 前记录 SHA。
