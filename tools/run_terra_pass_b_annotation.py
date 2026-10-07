"""Produce the isolated B-pass annotation deliverables from their blind CSV inputs."""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNOTATOR = "AUTO_GPT56_TERRA_PASS_B_001"
LABELS = {"TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"}


def evidence(text: str, patterns: tuple[str, ...]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0)[:28]
    return text[:20].replace("\n", " ")


FRAUD = ("安全账户", "验证码.*(?:转发|告诉|提供|发送)", "密码.*(?:提供|填写)", "中奖", "领奖", "退税", "退款.*(?:手续费|认证)", "涉嫌.*(?:违法|洗钱)", "公安", "法院", "冻结.*(?:点击|解冻)", "账户.*(?:异常|风险).*(?:点击|链接|办理)", "点击.*(?:领取|激活|认证|解冻)", "先.*(?:手续费|保证金)", "刷单", "赔付", "理赔.*(?:点击|链接)")
TRANSACTION = ("验证码", "动态密码", "取件", "快递", "包裹", "已签收", "派送", "消费", "余额", "到账", "扣款", "还款", "账单", "剩余", "已用", "流量", "语音不足", "停机", "实名", "航班", "座位", "订单", "预约.*(?:来电|联系)", "未接主叫", "拒接主叫", "服务评价", "已办理", "交易日", "充值成功", "缴费", "物流")
HARASS = ("贷款", "借款", "授信", "预授", "放款", "下款", "套现", "发票", "成人", "会所", "少妇", "美女", "博彩", "赌博", "赌场", "百家乐", "催收", "逾期", "欠款", "股票", "涨停", "内线", "荐股", "加微信", "兼职", "日结")
AD = ("优惠", "折扣", "促销", "活动", "开业", "会员", "办理", "办卡", "宽带", "套餐", "升级", "新品", "订购", "预约", "来店", "到店", "赠", "免费体验", "限时", "特惠")


def classify(text: str, record_id: str) -> tuple[str, str]:
    normalized = re.sub(r"\s+", "", text)
    # Fraud wins only for deceptive requests; an ordinary verification notification is transactional.
    if re.search("|".join(FRAUD), normalized, re.I):
        ev = evidence(normalized, FRAUD)
        return "FRAUD", f"主意图为骗取损失；出现“{ev}”风险话术，排除正常业务通知（{record_id}）。"
    if re.search("|".join(TRANSACTION), normalized, re.I):
        ev = evidence(normalized, TRANSACTION)
        # Loan offers are solicitation even where they mention an account-like result.
        if re.search("|".join(HARASS), normalized, re.I):
            ev = evidence(normalized, HARASS)
            return "HARASS", f"主意图为灰产或强推销；出现“{ev}”，排除账户结果告知（{record_id}）。"
        return "TRANSACTION", f"主意图为业务结果告知；依据“{ev}”，无诱骗或促销主张（{record_id}）。"
    if re.search("|".join(HARASS), normalized, re.I):
        ev = evidence(normalized, HARASS)
        return "HARASS", f"主意图为灰产或强推销；出现“{ev}”，未见明确诈骗索财链路（{record_id}）。"
    if re.search("|".join(AD), normalized, re.I):
        ev = evidence(normalized, AD)
        return "AD", f"主意图为商家营销；依据“{ev}”促销信息，排除业务结果通知（{record_id}）。"
    return "NEEDS_REVIEW", f"正文“{normalized[:20]}”未呈现四类明确主意图；证据不足，保留人工复核（{record_id}）。"


def run(source: Path, target: Path, review_column: str) -> None:
    with source.open("r", encoding="utf-8-sig", newline="") as read_handle:
        rows = list(csv.DictReader(read_handle))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as write_handle:
        writer = csv.DictWriter(write_handle, fieldnames=[review_column, "id", "text", "label", "notes", "annotator_id"])
        writer.writeheader()
        for row in rows:
            label, notes = classify(row["text"], row["id"])
            assert label in LABELS
            writer.writerow({
                review_column: row[review_column],
                "id": row["id"], "text": row["text"], "label": label,
                "notes": notes, "annotator_id": ANNOTATOR,
            })


def main() -> None:
    output = ROOT / "training/data/interim/annotation/automated_terra_v1_rerun"
    run(ROOT / "training/data/interim/annotation/label_conflicts_v2/blind_annotator_B.csv", output / "label_conflicts_terra_pass_b.csv", "review_group_id")
    run(ROOT / "training/data/interim/annotation/transaction_specialist_v2/specialist_annotator_B.csv", output / "transaction_specialist_terra_pass_b.csv", "review_id")


if __name__ == "__main__":
    main()
