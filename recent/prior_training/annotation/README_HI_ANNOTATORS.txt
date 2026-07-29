印地/印度短信四分类标注说明（作业用）

请打开：iiitd_pilot_500.csv

你只要填两列：
  1) label = TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW
  2) annotator = 你的名字

重要：
  - 本集 language 记为 hi，但正文多为拉丁文 Hinglish / 印度英语
  - 几乎没有天城文 Devanagari；不能当「纯印地文」验收金标
  - ham 里大量私人闲聊 → NEEDS_REVIEW
  - spam 里很多问答促销/quiz → 倾向 AD，不要一律 FRAUD

强制判断顺序：FRAUD → TRANSACTION → AD → HARASS → NEEDS_REVIEW

统计：{'iiitd_all': 2000, 'iiitd_suggested': {'NEEDS_REVIEW': 1698, 'TRANSACTION': 6, 'AD': 289, 'HARASS': 6, 'FRAUD': 1}}

完整说明：docs/labeling-guide.md
