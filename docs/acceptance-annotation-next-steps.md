# 验收标注下一步：缺口表 / HARASS·印尼待标包 / 冻结双人任务

> 生成工具在 `training/scripts/`；CSV 产物在 `training/data/interim/annotation/acceptance_packs/`（gitignore）。  
> **这些包本身不能宣称四语 offline ≥98% PASS**——冻结金标要等双人标完并记 SHA。

## 1. 一键生成

```powershell
cd "C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier"
$env:PYTHONPATH = "training"

python training/scripts/report_label_gaps.py
python training/scripts/prepare_harass_id_relabel_packs.py
python training/scripts/prepare_freeze_dual_annotation_packs.py
```

或：`make prepare-acceptance-packs`

## 2. 产物位置

| 产物 | 路径 |
|------|------|
| 缺口表 JSON | `training/reports/metrics/label_gap_report.json` |
| HARASS 待标 | `.../acceptance_packs/harass_relabel_candidates.csv` |
| 印尼补洞待标 | `.../acceptance_packs/id_gap_fill_candidates.csv` |
| 冻结主池 | `.../acceptance_packs/freeze/freeze_pool.csv` |
| 标注人 A/B | `.../freeze/freeze_annotator_A.csv` / `_B.csv` |
| 冻结缺口 | `.../freeze/freeze_shortfall.json` |

## 3. 你怎么标

1. **HARASS / id 包**：只填 `label` + `annotator`；不确定就 `NEEDS_REVIEW`。  
2. **冻结包**：A、B 各拿一份，互不偷看，也不要看 `prior_label`。  
3. 两人标完后：相同标签可进候选金标；冲突交给第三人仲裁判定。  
4. 看 `freeze_shortfall.json`：`shortfall>0` 的格子还要**找新语料**（尤其 en TRANSACTION、hi FRAUD/TXN、天城文印地）。

## 4. 标完后怎么回流训练

把新 `label` 写回对应的 `*_all_suggested.csv`（或让助手做合并），然后：

```powershell
python training/scripts/convert_annotation_csv_to_jsonl.py
make prepare-annotation-bootstrap
```

冻结金标应单独存（不要混进 homework bootstrap），并在 `evaluate` 前记录 SHA。
