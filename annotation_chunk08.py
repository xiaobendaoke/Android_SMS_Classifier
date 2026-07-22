import csv

INPUT = r"C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier\training\data\interim\annotation\chunks\chunk_08.csv"

rows = []
with open(INPUT, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    for row in reader:
        rows.append(row)

print(f"Loaded {len(rows)} rows")

FRAUD_IDS = {
    "uci_02427": "情人节特别活动声称赢得1000英镑并让发送GO到付费号码，典型假中奖诈骗",
    "uci_02438": "声称每周赢取250英镑现金并要求发PLAY到付费号码，假中奖吸费诈骗",
    "uci_02473": "声称最终机会领取150英镑折扣券并发送YES到付费号码，假奖励吸费诈骗",
    "uci_02496": "声称作为获奖网络客户获得900英镑奖励并要求拨打电话领取，典型中奖诈骗",
    "uci_02514": "声称赢得诺基亚6230和免费数码相机要求发送NOKIA到付费号码，假中奖吸费诈骗",
    "uci_02525": "声称免费进入250英镑周赛并发WIN到付费号码，假中奖诈骗",
    "uci_02556": "声称已获奖获得免费数码相机要求回复SNAP领取，假中奖吸费诈骗",
    "uci_02574": "声称获得3G视频手机要求拨打付费电话号码领取，假中奖吸费诈骗",
    "uci_02596": "阳光竞猜声称赢取索尼DVD播放器要求发答案到付费号码，假中奖吸费诈骗",
    "uci_02612": "敲门笑话群发参加250英镑礼品券周赛，典型中奖吸费诈骗",
    "uci_02632": "声称手机号码赢得2000英镑奖金并要求尽快拨打付费电话领取，典型大奖诈骗",
    "uci_02642": "声称保证获得诺基亚手机或iPod或500英镑并要求发送COLLECT到付费号码，假中奖诈骗",
    "uci_02686": "声称今日抽奖赢得800英镑保证奖要求拨打固定电话领取，典型中奖吸费诈骗",
    "uci_02693": "声称有800张免费欧洲机票赠送要求拨打电话领取，虚假中奖诈骗",
}

AD_IDS = {
    "uci_02402": "提供色情交友服务推广并要求付费订阅成人内容，属于成人广告类营销",
    "uci_02413": "发送CHAT到86688收费聊天交友平台推广，属于付费聊天服务广告",
    "uci_02420": "短信服务费积分推广包含退订说明和登录网址，属于付费订阅服务广告",
    "uci_02480": "万圣节主题诺基亚logo和免费铃声下载推广，属于付费内容订阅广告",
    "uci_02548": "推广下载铃声、标志和游戏的付费服务网站，属于内容服务广告",
    "uci_02575": "免费色情视频并要求回复关键词获取下一条，属于成人内容付费订阅广告",
    "uci_02581": "声称已订阅英国最佳移动内容服务并发送STOP退订，属于付费订阅服务广告",
    "uci_02583": "免费塔罗牌文本占卜服务推广需付费续订，属于付费内容服务广告",
    "uci_02590": "推广狗交服务并要求发送ENTRY订阅，属于成人付费交友广告",
    "uci_02620": "转发自21870000的40个匹配并要求拨打电话检索消息的收费交友服务推广",
    "uci_02622": "免费铃声订阅服务推广每周新铃声，属于付费内容订阅广告",
    "uci_02626": "免费铃声服务推广每1.50英镑每周，属于付费铃声订阅广告",
    "uci_02663": "聊天介绍外貌和性趣的推广短信，属于成人聊天服务广告",
    "uci_02664": "免费第一周诺基亚铃声订阅推广，属于付费铃声服务广告",
    "uci_02669": "狗交服务网络发送位置推广，属于成人付费交友广告",
    "uci_02670": "回复关于新诺基亚手机和摄像机优惠的尝试联系短信，属于手机促销广告",
    "uci_02680": "本周新铃声推广要求按下一条短信指示订购，属于付费铃声订阅广告",
    "uci_02691": "体育新闻免费加免费铃声推广，属于内容订阅服务广告",
    "uci_02699": "丢失12英镑帮助来自86688的付费服务短信，属于收费信息服务推广",
}

SPECIAL_NEEDS_REVIEW = {
    "uci_02408": "侦探推理谜题转发消息，属于娱乐类转发内容，不属前四类",
    "uci_02430": "邀请访问ASJESUS.COM网站并让回复意见的群发消息，非直接诈骗也不是促销广告，归为待审核",
    "uci_02434": "关于瑞士银行印度存款的政治宣传转发消息，非个人聊天但也非诈骗/广告/骚扰，归为待审核",
    "uci_02526": "宗教连锁短信要求发送给十个人获得奇迹，属于转发类消息，归为待审核",
    "uci_02545": "关于Shoranur火车事故的慈善连锁转发短信，属于转发类消息，归为待审核",
    "uci_02565": "脑筋急转弯/谜语转发消息，属于娱乐转发类内容，不属前四类",
    "uci_02644": "客服满意度调查短信，非推销非诈骗，属于服务反馈类通知",
    "uci_02681": "侦探推理谜题转发消息，属于娱乐类转发内容，不属前四类",
}

def annotate(rid, uci):
    if rid in FRAUD_IDS:
        return ("FRAUD", FRAUD_IDS[rid])
    if rid in AD_IDS:
        return ("AD", AD_IDS[rid])
    if rid in SPECIAL_NEEDS_REVIEW:
        return ("NEEDS_REVIEW", SPECIAL_NEEDS_REVIEW[rid])
    return ("NEEDS_REVIEW", "私人日常闲聊/生活对话/朋友间沟通，不属于事务/广告/诈骗/骚扰四类")


def main():
    counts = {}
    for row in rows:
        rid = row["id"]
        uci = row["uci_binary"]
        label, notes = annotate(rid, uci)
        row["label"] = label
        row["notes"] = notes
        row["annotator"] = ""
        counts[label] = counts.get(label, 0) + 1

    with open(INPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("Done. Counts:")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print(f"Total: {sum(counts.values())}")


if __name__ == "__main__":
    main()
