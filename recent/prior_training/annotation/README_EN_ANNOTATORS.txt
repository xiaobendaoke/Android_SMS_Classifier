英文四分类标注说明（UCI，已与中文主规格对齐）

打开文件：uci_pilot_500.csv
填写两列：
  - label：TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW
  - annotator：你的名字

════════════════════════════════════
一、四类定义（先看懂再标）
════════════════════════════════════
TRANSACTION 事务：用户预期要收到的业务结果
  （OTP/验证码、扣款到账、账单、物流取件、订单确认等）

AD 广告：正规商家/内容服务促销，目的是让你买/订购
  （铃声订阅、手机升级优惠、商店打折、退订类营销——不骗你转账）

HARASS 骚扰：不靠“骗转账”，但内容扰民
  （成人/约炮短信、灰色交友、催收、反复骚扰推销）

FRAUD 诈骗：靠欺骗造成损失
  （假中奖、假积分/账单要你回电领奖、钓鱼链接、冒充客服要码要钱）

不确定 → NEEDS_REVIEW（不要硬猜）
  ★ UCI 里大量 ham 是私人闲聊 → 一律 NEEDS_REVIEW，不要硬塞 TRANSACTION

════════════════════════════════════
二、强制判断顺序（必须按这个顺序问）
════════════════════════════════════
① 是不是在骗我？（假中奖/假奖励/要码要钱/钓鱼/假账单领奖）
     → 是：FRAUD
② 是不是账户/订单/认证/物流等“业务结果告知”？
     → 是：TRANSACTION
③ 是不是正规商家/内容服务在促销、拉订阅？
     → 是：AD
④ 是不是成人/交友灰产/催收/强行推销（但不是典型诈骗）？
     → 是：HARASS
⑤ 其他 → NEEDS_REVIEW

注意：不是「ham 就标事务」！也不是「有 link 就标诈骗」！
      不是「spam 就标诈骗」——很多 spam 是铃声/促销广告或成人骚扰。

════════════════════════════════════
三、UCI 英文易混例子（标错最多的）
════════════════════════════════════
WINNER!! £900 prize reward. To claim call 09...     → FRAUD
Private! Account Statement... Bonus Points. Claim → FRAUD
Your account refilled. Transaction ID KR...         → TRANSACTION
Delivery: your parcel is out for delivery           → TRANSACTION
Thanks for Ringtone UK subscription, £5/month       → AD
Update to latest colour mobiles Free! Call 0800...  → AD
Want 2 get laid tonight? Txt GRAVEL to 69888        → HARASS
FreeMsg... sexy female... 150p per msg              → HARASS
Hey, running late, see you at 4                     → NEEDS_REVIEW
Can you send me your account number? (朋友聊天)      → NEEDS_REVIEW

════════════════════════════════════
四、其他
════════════════════════════════════
- suggested_label 仅机器粗分，请按上面规则改 label
- uci_binary：ham/spam 是原二分类，不等于四类
- 全量建议粗分（机器，仅供参考）：
  TRANSACTION: 7
  AD: 241
  HARASS: 182
  FRAUD: 144
  NEEDS_REVIEW: 5000
- 完整说明：docs/labeling-guide.md（含英文补充）
- 待办清单：docs/en-annotation-todo.md


