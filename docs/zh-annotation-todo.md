# 中文标注：你现在要做什么

详细分类标准已重写，请以这个为准：

- 完整版：`docs/labeling-guide.md`
- 短版：`training/data/interim/annotation/README_ZH_ANNOTATORS.txt`

## 核心变化（相对旧说明）

旧做法不对的地方：
- 看到“银行/验证码/套餐”就标事务
- 判断顺序把诈骗放太后

新标准（主规格）：
1. **先看是不是诈骗**（骗）
2. **再看是不是事务结果通知**（账户/订单/认证/物流）
3. **再看是不是正规广告**
4. **再看是不是骚扰**
5. 不确定 → `NEEDS_REVIEW`

## 你要做的

1. 重新看一遍 `README_ZH_ANNOTATORS.txt` / `docs/labeling-guide.md`
2. 打开 `zh_pilot_800.csv`
3. 只填 `label` + `annotator`
4. 已标过的请按新标准复查一遍

标完告诉我。
