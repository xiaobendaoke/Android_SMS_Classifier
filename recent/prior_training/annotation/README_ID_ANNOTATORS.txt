印尼语四分类标注说明（作业用）

请优先打开：id_yudiwbs_pilot_500.csv
补充可标：id_spamshield_pilot_500.csv（含较多机翻痕迹，建议次优先）

你只要填两列：
  1) label = TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW
  2) annotator = 你的名字

强制判断顺序（与中英文一致）：
  ① 是不是在骗我？ → FRAUD
  ② 是不是账户/订单/认证/物流业务结果？ → TRANSACTION
  ③ 是不是正规商家促销/订阅？ → AD
  ④ 是不是骚扰/灰产/催收？ → HARASS
  ⑤ 不确定 / 私人闲聊 → NEEDS_REVIEW

orig_label 含义：
  yudiwbs: 0=normal, 1=fraud/penipuan, 2=promo
  spamshield: ham/spam + category

注意：
  - suggested_label 只是机器建议，请人工写入 label
  - 不要把私人闲聊硬标成 TRANSACTION
  - SpamShield 印尼子集可能含 UCI 机翻句式，拿不准就 NEEDS_REVIEW

统计：{'yudiwbs_all': 1143, 'yudiwbs_suggested': {'AD': 300, 'FRAUD': 198, 'TRANSACTION': 5, 'NEEDS_REVIEW': 634, 'HARASS': 6}, 'spamshield_all': 1270, 'spamshield_suggested': {'NEEDS_REVIEW': 1002, 'FRAUD': 130, 'AD': 110, 'HARASS': 28}}

完整说明：docs/labeling-guide.md
