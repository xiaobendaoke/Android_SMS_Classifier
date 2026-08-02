#!/usr/bin/env python3
"""Final annotation script - handles all 600 records directly."""
import csv, sys
csv.field_size_limit(sys.maxsize)

ANNOTATOR = "HUMAN_A_001"
INPATH = "training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv"

# Use csv.DictReader with utf-8-sig to handle BOM
with open(INPATH, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    fieldnames = [fn.strip().strip('"').strip("'") for fn in reader.fieldnames]
    reader.fieldnames = fieldnames
    rows = []
    for row in reader:
        cleaned = {}
        for k, v in row.items():
            k_clean = k.strip().strip('"').strip("'")
            cleaned[k_clean] = v
        rows.append(cleaned)

print(f"Read {len(rows)} rows, fields: {fieldnames}")

# Define all annotations
ANNOTATIONS = {}

def set_label(rid, label, note=""):
    ANNOTATIONS[rid] = (label, note)

# === TRANSACTION: Bank/financial notifications ===
bank_tx = [
    "zh-n2w-00760", "zh-n2w-00926", "zh-n2w-01001", "zh-n2w-01047",
    "zh-n2w-01644", "zh-n2w-01647", "zh-n2w-01812", "zh-n2w-02079",
    "zh-n2w-02499", "zh-n2w-02907", "zh-n2w-03044", "zh-n2w-03172",
    "zh-n2w-03191", "zh-n2w-03657", "zh-n2w-03757", "zh-n2w-04186",
    "zh-n2w-04320", "zh-n2w-05006", "zh-n2w-05185", "zh-n2w-06440",
    "zh-n2w-06597", "zh-n2w-07663", "zh-n2w-07729", "zh-n2w-08011",
    "zh-n2w-09188", "zh-n2w-09405",
    "zh_00196", "zh_00201", "zh_00230", "zh_00253",
    "zh_00276", "zh_00372", "zh_00668", "zh_00972",
    "zh_01041", "zh_01043", "zh_01109", "zh_01575",
    "zh_01645", "zh_01978", "zh_02000", "zh_02026",
    "zh_02210", "zh_02342", "zh_02654", "zh_02891",
    "zh_02904", "zh_03052", "zh_03201", "zh_03741",
    "zh_03782", "zh_03847", "zh_03894", "zh_04202",
    "zh_04462", "zh_04627", "zh_05178", "zh_05233",
    "zh_05259", "zh_05425", "zh_05433", "zh_05477",
    "zh_05479", "zh_05544", "zh_05633", "zh_05790",
    "zh_06403", "zh_06433", "zh_06501", "zh_06954",
    "zh_06999", "zh_07041", "zh_07444", "zh_07823",
    "zh_08579", "zh_08894", "zh_09138", "zh_09972",
    "zh_10441",
    "zh_01157",   # 外币记账规则通知
    "zh_05356",   # 北京银行快捷支付开通
    "zh_05773",   # 政府一站通启动码
]
for rid in bank_tx:
    set_label(rid, "TRANSACTION")

# === TRANSACTION: Orders/Travel/Reservations ===
orders = [
    "zh_00077", "zh_00221", "zh_00349", "zh_00359",
    "zh_00578", "zh_00709", "zh_00720", "zh_00776",
    "zh_00808", "zh_00839", "zh_00885", "zh_00901",
    "zh_01553", "zh_01561", "zh_01940", "zh_01947",
    "zh_02685", "zh_02686", "zh_02773", "zh_03196",
    "zh_03556", "zh_03728", "zh_03916", "zh_03980",
    "zh_04385", "zh_04696", "zh_04832", "zh_04948",
    "zh_04959", "zh_04982", "zh_05023", "zh_05131",
    "zh_05181", "zh_05217", "zh_05349", "zh_05441",
    "zh_05975", "zh_06023", "zh_06350", "zh_06555",
    "zh_06671", "zh_06748", "zh_06802", "zh_06896",
    "zh_07006", "zh_07121", "zh_07335", "zh_07350",
    "zh_07474", "zh_07678", "zh_07871", "zh_08122",
    "zh_08317", "zh_08396", "zh_08525", "zh_08797",
    "zh_09144", "zh_09214", "zh_09404", "zh_09415",
    "zh_09912", "zh_10141", "zh_10305", "zh_10670",
    "zh_10737", "zh_10807",
]
for rid in orders:
    set_label(rid, "TRANSACTION")

# === TRANSACTION: OTP/Verification codes ===
otps = [
    "zh-n2w-00013", "zh-n2w-00470", "zh-n2w-02645",
    "zh-n2w-02829", "zh-n2w-05036", "zh-n2w-06698",
    "zh-n2w-07241", "zh-n2w-09364", "zh-n2w-04389",
    "zh_00025", "zh_00138", "zh_00146", "zh_00182",
    "zh_00213", "zh_00338", "zh_00493", "zh_00502",
    "zh_00648", "zh_00819", "zh_00987", "zh_01002",
    "zh_01110", "zh_01256", "zh_01413", "zh_01668",
    "zh_01725", "zh_01859", "zh_01933", "zh_01935",
    "zh_02074", "zh_02174", "zh_02274", "zh_02489",
    "zh_02493", "zh_02523", "zh_02628", "zh_02697",
    "zh_02708", "zh_02957", "zh_03018", "zh_03168",
    "zh_03354", "zh_03386", "zh_03685", "zh_03783",
    "zh_03961", "zh_03973", "zh_03974", "zh_04134",
    "zh_04169", "zh_04211", "zh_04265", "zh_04381",
    "zh_05010", "zh_05027", "zh_05077", "zh_05139",
    "zh_05280", "zh_05281", "zh_05298", "zh_05333",
    "zh_05334", "zh_05486", "zh_05564", "zh_05589",
    "zh_05602", "zh_05888", "zh_05937", "zh_06028",
    "zh_06092", "zh_06104", "zh_06207", "zh_06541",
    "zh_06773", "zh_07252", "zh_07348", "zh_07542",
    "zh_07634", "zh_08052", "zh_08128", "zh_08195",
    "zh_08292", "zh_08353", "zh_08535", "zh_08585",
    "zh_09418", "zh_09428", "zh_09528", "zh_09589",
    "zh_09624", "zh_09633", "zh_09759", "zh_09811",
    "zh_09843", "zh_10019", "zh_10256", "zh_10339",
    "zh_10361", "zh_10426",
]
for rid in otps:
    set_label(rid, "TRANSACTION")

# Override some OTPs with notes
set_label("zh-n2w-02645", "TRANSACTION", "网易验证码+安全提醒")
set_label("zh-n2w-09364", "TRANSACTION", "移动订购确认验证码")
set_label("zh-n2w-04389", "TRANSACTION", "聚水潭系统授权验证码")
set_label("zh_03354", "TRANSACTION", "支付宝校验码(乱码)")
set_label("zh_03961", "TRANSACTION", "支付宝提现验证码")
set_label("zh_03973", "TRANSACTION", "机场无线验证码")
set_label("zh_10339", "TRANSACTION", "支付宝校验码(乱码)")
set_label("zh_09418", "NEEDS_REVIEW", "短信截断内容不完整")
set_label("zh_06773", "NEEDS_REVIEW", "验证码格式异常")

# === TRANSACTION: Delivery/Logistics ===
deliveries = [
    "zh-n2w-00010", "zh-n2w-00038", "zh-n2w-00150", "zh-n2w-00181",
    "zh-n2w-00261", "zh-n2w-00262", "zh-n2w-00324", "zh-n2w-00359",
    "zh-n2w-00570", "zh-n2w-00611", "zh-n2w-00766", "zh-n2w-00911",
    "zh-n2w-01093", "zh-n2w-01277", "zh-n2w-01369", "zh-n2w-01472",
    "zh-n2w-01711", "zh-n2w-01792", "zh-n2w-01849", "zh-n2w-01977",
    "zh-n2w-02086", "zh-n2w-02204", "zh-n2w-02316", "zh-n2w-02427",
    "zh-n2w-02557", "zh-n2w-02620", "zh-n2w-02632", "zh-n2w-02860",
    "zh-n2w-02951", "zh-n2w-02980", "zh-n2w-03003", "zh-n2w-03009",
    "zh-n2w-03022", "zh-n2w-03121", "zh-n2w-03580", "zh-n2w-03591",
    "zh-n2w-03649", "zh-n2w-03664", "zh-n2w-03685", "zh-n2w-03743",
    "zh-n2w-03814", "zh-n2w-03888", "zh-n2w-03899", "zh-n2w-04041",
    "zh-n2w-04100", "zh-n2w-04174", "zh-n2w-04188", "zh-n2w-04222",
    "zh-n2w-04263", "zh-n2w-04325", "zh-n2w-04502", "zh-n2w-04553",
    "zh-n2w-04583", "zh-n2w-04752", "zh-n2w-05025", "zh-n2w-05435",
    "zh-n2w-05465", "zh-n2w-05593", "zh-n2w-05782", "zh-n2w-05906",
    "zh-n2w-05966", "zh-n2w-06299", "zh-n2w-06431", "zh-n2w-06588",
    "zh-n2w-06662", "zh-n2w-06723", "zh-n2w-06725", "zh-n2w-06901",
    "zh-n2w-07223", "zh-n2w-07232", "zh-n2w-07351", "zh-n2w-07387",
    "zh-n2w-07628", "zh-n2w-07632", "zh-n2w-07639", "zh-n2w-07856",
    "zh-n2w-07923", "zh-n2w-08266", "zh-n2w-08453", "zh-n2w-09043",
    "zh-n2w-09069", "zh-n2w-09070", "zh-n2w-09151", "zh-n2w-09158",
    "zh-n2w-09293", "zh-n2w-09329", "zh-n2w-09420", "zh-n2w-09453",
    "zh-n2w-09615", "zh-n2w-09646", "zh-n2w-09821", "zh-n2w-09894",
    "zh-n2w-09950",
    "zh_01796", "zh_02587", "zh_03147", "zh_04910",
    "zh_10201", "zh_10610",
]
for rid in deliveries:
    set_label(rid, "TRANSACTION")

# === TRANSACTION: China Unicom Assistant ===
cu = [
    "zh-n2w-00055", "zh-n2w-00072", "zh-n2w-00120", "zh-n2w-00204",
    "zh-n2w-00379", "zh-n2w-01054", "zh-n2w-01086", "zh-n2w-01092",
    "zh-n2w-01172", "zh-n2w-01195", "zh-n2w-01421", "zh-n2w-01725",
    "zh-n2w-01983", "zh-n2w-02133", "zh-n2w-02303", "zh-n2w-02900",
    "zh-n2w-03037", "zh-n2w-03180", "zh-n2w-03879", "zh-n2w-04135",
    "zh-n2w-04187", "zh-n2w-04772", "zh-n2w-05585", "zh-n2w-05809",
    "zh-n2w-06483", "zh-n2w-06600", "zh-n2w-07543", "zh-n2w-07983",
    "zh-n2w-08566",
]
for rid in cu:
    set_label(rid, "TRANSACTION")

# === TRANSACTION: Telecom usage ===
telco = [
    "zh-n2w-00882", "zh-n2w-01036", "zh-n2w-01236", "zh-n2w-01425",
    "zh-n2w-01463", "zh-n2w-01544", "zh-n2w-02172", "zh-n2w-02224",
    "zh-n2w-02325", "zh-n2w-02616", "zh-n2w-02908", "zh-n2w-03132",
    "zh-n2w-03244", "zh-n2w-03434", "zh-n2w-04734", "zh-n2w-05519",
    "zh-n2w-06224", "zh-n2w-06746", "zh-n2w-06779", "zh-n2w-06942",
    "zh-n2w-07083", "zh-n2w-08251", "zh-n2w-08270", "zh-n2w-08597",
    "zh-n2w-08962", "zh-n2w-09239", "zh-n2w-09644", "zh-n2w-09765",
    "zh-n2w-02364", "zh-n2w-08207",
    "zh_00147", "zh_00187", "zh_00333", "zh_00614",
    "zh_00788", "zh_01094", "zh_01209", "zh_01270",
    "zh_01330", "zh_01716", "zh_01750", "zh_02350",
    "zh_02415", "zh_04231", "zh_04695", "zh_04899",
    "zh_07284", "zh_07360", "zh_07827", "zh_08251",
    "zh_09532",
]
for rid in telco:
    set_label(rid, "TRANSACTION")

# === TRANSACTION: E-commerce ===
ecom = [
    "zh-n2w-00235", "zh-n2w-00354", "zh-n2w-00397", "zh-n2w-00446",
    "zh-n2w-01021", "zh-n2w-01665", "zh-n2w-01783", "zh-n2w-02336",
    "zh-n2w-02713", "zh-n2w-02787", "zh-n2w-02958", "zh-n2w-03326",
    "zh-n2w-03393", "zh-n2w-03929", "zh-n2w-04024", "zh-n2w-04869",
    "zh-n2w-05241", "zh-n2w-05467", "zh-n2w-05555", "zh-n2w-06048",
    "zh-n2w-06389", "zh-n2w-07381", "zh-n2w-07504", "zh-n2w-07694",
    "zh-n2w-07902", "zh-n2w-07940", "zh-n2w-08584", "zh-n2w-09260",
    "zh-n2w-09344", "zh-n2w-09997", "zh-n2w-09998",
]
for rid in ecom:
    set_label(rid, "TRANSACTION")

# Mark AD-heavy ones
set_label("zh-n2w-00439", "AD", "宽带全家享礼包限时推广")
set_label("zh-n2w-05241", "AD", "高清盒续约服务推广")
set_label("zh-n2w-07504", "AD", "交通意外险理赔送代金券推广")
set_label("zh-n2w-07611", "AD", "中信银行息费减免方案推广")

# === TRANSACTION: Payment/Repayment ===
payments = [
    "zh-n2w-00142", "zh-n2w-00272", "zh-n2w-00292", "zh-n2w-00307",
    "zh-n2w-00348", "zh-n2w-00364", "zh-n2w-00553", "zh-n2w-00698",
    "zh-n2w-00830", "zh-n2w-00978", "zh-n2w-00986", "zh-n2w-01058",
    "zh-n2w-01103", "zh-n2w-01209", "zh-n2w-01414", "zh-n2w-01551",
    "zh-n2w-01658", "zh-n2w-01731", "zh-n2w-01852", "zh-n2w-01987",
    "zh-n2w-02139", "zh-n2w-02185", "zh-n2w-02243", "zh-n2w-02321",
    "zh-n2w-02576", "zh-n2w-02711", "zh-n2w-02763", "zh-n2w-02855",
    "zh-n2w-02990", "zh-n2w-03034", "zh-n2w-03760", "zh-n2w-04157",
    "zh-n2w-04234", "zh-n2w-04538", "zh-n2w-05198", "zh-n2w-05228",
    "zh-n2w-05245", "zh-n2w-05287", "zh-n2w-05533", "zh-n2w-05586",
    "zh-n2w-05605", "zh-n2w-05608", "zh-n2w-05628", "zh-n2w-05973",
    "zh-n2w-06456", "zh-n2w-06578", "zh-n2w-06619", "zh-n2w-06711",
    "zh-n2w-06947", "zh-n2w-07015", "zh-n2w-07118", "zh-n2w-07282",
    "zh-n2w-07398", "zh-n2w-07557", "zh-n2w-07949", "zh-n2w-07982",
    "zh-n2w-07996", "zh-n2w-08058", "zh-n2w-08208", "zh-n2w-08605",
    "zh-n2w-08664", "zh-n2w-08741", "zh-n2w-08832", "zh-n2w-08880",
    "zh-n2w-09297", "zh-n2w-09553",
    "zh_00073", "zh_00106", "zh_00376", "zh_00448",
    "zh_00533", "zh_02181", "zh_03890", "zh_04473",
    "zh_05282", "zh_07400", "zh_07723", "zh_09393",
    "zh_09727", "zh_10007", "zh_10417",
]
for rid in payments:
    set_label(rid, "TRANSACTION")

# Mark AD-heavy ones
set_label("zh_07400", "AD", "账单分期+星巴克积分推广")
set_label("zh_05282", "AD", "增值业务查询订购列表")

# === AD ===
ads = [
    "zh-n2w-01723", "zh-n2w-03367", "zh-n2w-07310", "zh-n2w-09077",
    "zh-n2w-00025", "zh-n2w-00580", "zh-n2w-00856",
    "zh-n2w-01622", "zh-n2w-01820", "zh-n2w-02340",
    "zh-n2w-04159", "zh-n2w-05310", "zh-n2w-05978",
    "zh-n2w-06392", "zh-n2w-07352", "zh-n2w-08756",
    "zh-n2w-06121", "zh-n2w-09203", "zh-n2w-00439",
    "zh-n2w-05241", "zh-n2w-07504", "zh-n2w-07611",
    "zh-n2w-03612",
    "zh_00211", "zh_00705", "zh_02931", "zh_04573",
    "zh_04635", "zh_07973", "zh_08831", "zh_10386",
    "zh_10868", "zh_03551", "zh_08836", "zh_08993",
    "zh_05491", "zh_06477", "zh_07400", "zh_05282",
]
for rid in ads:
    set_label(rid, "AD")

# === HARASS ===
harass = [
    "zh-n2w-00848", "zh-n2w-04080", "zh-n2w-05697", "zh-n2w-08429",
    "zh-n2w-09995",
    "zh_01409", "zh_04429", "zh_05580", "zh_05155", "zh_01214",
]
for rid in harass:
    set_label(rid, "HARASS")

# === FRAUD ===
fraud = [
    "zh-n2w-01141", "zh-n2w-02538", "zh-n2w-03977",
]
for rid in fraud:
    set_label(rid, "FRAUD")

# === NEEDS_REVIEW ===
review = [
    "zh-n2w-04550", "zh-n2w-03254", "zh-n2w-07202",
    "zh_00713", "zh_05480", "zh_08484", "zh_09139",
    "zh-n2w-00627", "zh-n2w-01426", "zh-n2w-01922",
    "zh-n2w-02003", "zh-n2w-08277", "zh_09470",
    "zh_09418", "zh_06773",
]
for rid in review:
    set_label(rid, "NEEDS_REVIEW")

# Custom notes for specific cases
NOTES = {
    "zh-n2w-04550": "满意度调查非四分类",
    "zh_00713": "续短信内容不完整",
    "zh_05480": "服务通知征求同意非四分类",
    "zh_08484": "仅查询余额语义模糊",
    "zh_09139": "错误提示非四分类",
    "zh-n2w-00627": "满意度评价邀请非四分类",
    "zh-n2w-01426": "通话体验评价邀请非四分类",
    "zh-n2w-01922": "满意度评价邀请非四分类",
    "zh-n2w-02003": "宽带业务评价邀请非四分类",
    "zh-n2w-03254": "学校互动课堂通知非四分类",
    "zh-n2w-07202": "满意度调查非四分类",
    "zh-n2w-08277": "业务订购体验评价非四分类",
    "zh_09470": "满意度评价邀请非四分类",
    "zh_09418": "短信截断内容不完整",
    "zh_06773": "验证码格式异常",
    "zh-n2w-01141": "冒充银行通知兑换手机钓鱼链接",
    "zh-n2w-02538": "可疑还款链接冒充金融平台",
    "zh-n2w-03977": "游戏激活诈骗链接",
    "zh-n2w-07352": "话费流量查询附带增值业务推广",
    "zh-n2w-08756": "卡券到期提醒签到活动推广",
    "zh-n2w-06121": "服务提醒签到福利推广",
    "zh-n2w-09203": "余量查询服务推广",
    "zh_07400": "账单分期星巴克积分推广",
    "zh_05282": "增值业务查询订购列表",
    "zh-n2w-00439": "宽带全家享礼包推广",
    "zh-n2w-05241": "高清盒续约服务推广",
    "zh-n2w-07504": "理赔送代金券推广",
    "zh-n2w-07611": "息费减免方案推广",
    "zh-n2w-03612": "业务营销评价邀请非四分类",
    "zh-n2w-02340": "全球通礼遇+抽奖活动推广",
}

# Apply
count_labeled = 0
for row in rows:
    rid = row["id"]
    if rid in ANNOTATIONS:
        row["label"] = ANNOTATIONS[rid][0]
        count_labeled += 1
    else:
        row["label"] = "NEEDS_REVIEW"
    row["human_annotator_id"] = ANNOTATOR
    row["notes"] = NOTES.get(rid, ANNOTATIONS[rid][1] if rid in ANNOTATIONS else "")

# Write
with open(INPATH, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

# Summary
from collections import Counter
cnt = Counter(r["label"] for r in rows)
print(f"\nTotal: {len(rows)}")
print(f"Labeled from map: {count_labeled}")
for lbl, n in sorted(cnt.items()):
    print(f"  {lbl}: {n}")

# Verify
ids_set = set(r["human_annotator_id"] for r in rows)
print(f"All annotator IDs = {ANNOTATOR}: {ids_set == {ANNOTATOR}}")
print("Done!")