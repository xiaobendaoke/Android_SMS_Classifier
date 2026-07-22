# 英文标注：你现在要做什么

详细分类标准已按主规格重写（与中文同一套），请以这个为准：

- 完整版：`docs/labeling-guide.md`（含「英文 UCI 补充」）
- 短版：`training/data/interim/annotation/README_EN_ANNOTATORS.txt`

## 核心变化（相对旧英文说明）

旧做法不对的地方：
- 判断顺序写成「先事务再诈骗」
- 看到 ham / verify / appointment 就倾向事务
- spam 容易一律当诈骗（其实很多是铃声广告或成人骚扰）

新标准（主规格，与中文一致）：
1. **先看是不是诈骗**（假中奖 / 假账单领奖 / 钓鱼 / 要码要钱）
2. **再看是不是事务结果通知**（OTP、到账、物流、订单确认）
3. **再看是不是正规广告**（铃声订阅、手机促销、退订类营销）
4. **再看是不是骚扰**（成人、交友灰产、催收）
5. 不确定 → `NEEDS_REVIEW`（**私人闲聊一律走这里**）

## 你要做的

1. 重新看一遍 `README_EN_ANNOTATORS.txt` / `docs/labeling-guide.md` §5
2. 重新生成表（若本地还是旧表）：

```powershell
python training\scripts\prepare_uci_annotation_pack.py
```

3. 打开 `uci_pilot_500.csv`
4. 只填 `label` + `annotator`
5. 已标过的请按新标准复查一遍

## 建议节奏

| 阶段 | 数量 | 目的 |
|------|------|------|
| 今晚 | 50 条 | 练手，对照易混表 |
| 本周 | 500 条（整张试点） | 英文试点完成 |
| 双人 | 再独立标一份 | 算一致性 |

标完告诉我。
