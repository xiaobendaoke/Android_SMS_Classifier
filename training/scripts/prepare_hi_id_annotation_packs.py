#!/usr/bin/env python3
"""Prepare Hindi/Indonesian four-class annotation packs from downloaded corpora.

Inputs (local / gitignored under training/data/raw):
  yudiwbs_id_sms_spam_v1/dataset_sms_spam_v1.csv
  spamshield_indonesian/clean-00001.jsonl
  iiitd_sms_spam/{Ham SMSes,Spam SMSes}/*.txt

Outputs (local / gitignored under interim/annotation):
  id_yudiwbs_all_suggested.csv + id_yudiwbs_pilot_500.csv
  id_spamshield_all_suggested.csv + id_spamshield_pilot_500.csv
  iiitd_all_suggested.csv + iiitd_pilot_500.csv
  README_ID_ANNOTATORS.txt + README_HI_ANNOTATORS.txt

Decision order matches docs/labeling-guide.md:
  FRAUD → TRANSACTION → AD → HARASS → NEEDS_REVIEW
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DEFAULT_OUT_DIR = ROOT / "data" / "interim" / "annotation"

FIELDNAMES = [
    "id",
    "text",
    "language",
    "source",
    "orig_label",
    "suggested_label",
    "suggest_reason",
    "label",
    "annotator",
    "template_group",
    "notes",
]

# Indonesian keyword heuristics (coarse; human must confirm)
ID_FRAUD = [
    "hadiah",
    "pemenang",
    "menang",
    "pin:",
    "kode pin",
    "klaim",
    "penipuan",
    "transfer",
    "rekening",
    "otp anda",
    "jangan berikan otp",
    "klik link",
    "bit.ly",
    "grandprize",
    "undian",
    "jackpot",
    "rp.175",
    "rp175",
    "milyar",
    "miliar",
]
ID_TXN = [
    "otp",
    "kode verifikasi",
    "kode otp",
    "kode rahasia",
    "berhasil ditransfer",
    "berhasil masuk",
    "saldo anda",
    "tagihan",
    "pembayaran berhasil",
    "resi",
    "paket anda",
    "sedang dikirim",
    "kode pengambilan",
]
ID_AD = [
    "promo",
    "diskon",
    "gratis",
    "spesial",
    "paket flash",
    "kuota",
    "puls",
    "berlangganan",
    "aktifkan",
    "download",
    "mytelkomsel",
    "iring",
    "rbt",
    "voucher",
    "cashback",
    "beli paket",
]
ID_HARASS = [
    "pinjaman",
    "pinjmn",
    "pinjam",
    "utang",
    "hutang",
    "tagih",
    "kolektor",
    "dewasa",
    "seks",
    "bokep",
    "cantik",
    "temui",
    "wa.",
    "whatsapp",
    "chat wa",
    "dukun",
    "santet",
    "pelet",
]

# Latin-script Indian / Hinglish / English-India heuristics
HI_FRAUD = [
    "you have won",
    "you've won",
    "claim prize",
    "lottery",
    "jackpot",
    "congratulations you",
    "selected as winner",
    "verify account immediately",
    "suspended account",
    "click here to claim",
    "otp mat share",
    "otp share mat",
    "bank account freeze",
    "kyc update urgently",
]
HI_TXN = [
    "otp",
    "one time password",
    "verification code",
    "a/c credited",
    "account credited",
    "debited",
    "txn id",
    "transaction id",
    "delivered",
    "out for delivery",
    "order confirmed",
    "recharge successful",
]
HI_AD = [
    "offer",
    "discount",
    "cashback",
    "recharge now",
    "subscribe",
    "free data",
    "limited period",
    "buy now",
    "apply now",
    "emi",
    "loan offer",
    "tnc apply",
]
HI_HARASS = [
    "get laid",
    "sexy",
    "adult",
    "dating",
    "call girls",
    "debt recovery",
    "overdue",
    "collection agent",
]


def template_group(text: str) -> str:
    key = re.sub(r"\d+", "#", text)
    key = re.sub(r"\s+", "", key)[:40]
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def _has_any(text: str, keys: Sequence[str]) -> bool:
    low = text.lower()
    return any(k.lower() in low for k in keys)


def suggest_id(orig: str, text: str) -> Tuple[str, str]:
    """Suggest four-class label for Indonesian rows."""
    if _has_any(text, ID_FRAUD):
        return "FRAUD", "id-fraud-keywords"
    if _has_any(text, ID_TXN) and not _has_any(text, ID_AD):
        return "TRANSACTION", "id-txn-keywords"
    if _has_any(text, ID_TXN) and any(k in text.lower() for k in ("otp", "kode verifikasi", "kode otp")):
        return "TRANSACTION", "id-otp-over-promo"
    if orig in {"1", "fraud", "penipuan", "spam"} and _has_any(text, ID_FRAUD):
        return "FRAUD", "orig-fraud+keywords"
    if orig in {"2", "promo", "ad"} or (_has_any(text, ID_AD) and not _has_any(text, ID_FRAUD)):
        return "AD", "id-promo-keywords"
    if _has_any(text, ID_HARASS):
        return "HARASS", "id-harass-keywords"
    if orig in {"1", "fraud", "penipuan", "spam"}:
        return "NEEDS_REVIEW", "orig-spam-unclear"
    if orig in {"0", "normal", "ham"}:
        return "NEEDS_REVIEW", "orig-normal-or-chat"
    return "NEEDS_REVIEW", "unclear"


def suggest_hi(orig: str, text: str) -> Tuple[str, str]:
    """Suggest four-class label for IIIT-D / Hinglish-Latin rows."""
    if _has_any(text, HI_FRAUD):
        return "FRAUD", "hi-fraud-keywords"
    if _has_any(text, HI_TXN) and not _has_any(text, HI_AD):
        return "TRANSACTION", "hi-txn-keywords"
    if _has_any(text, HI_AD) and not _has_any(text, HI_FRAUD):
        return "AD", "hi-ad-keywords"
    if _has_any(text, HI_HARASS):
        return "HARASS", "hi-harass-keywords"
    if orig == "spam":
        # IIIT spam often quiz/promo — prefer AD candidate over FRAUD
        if re.search(r"(reply|option|which|who do you|vote)", text, re.I):
            return "AD", "quiz-or-promo-spam"
        return "NEEDS_REVIEW", "spam-unclear"
    return "NEEDS_REVIEW", "ham-personal-or-unclear"


def write_csv(path: Path, records: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        w.writeheader()
        w.writerows(records)


def balanced_pilot(records: List[dict], size: int, seed: int, id_prefix: str) -> List[dict]:
    rng = random.Random(seed)
    by: Dict[str, List[dict]] = defaultdict(list)
    for r in records:
        by[r["suggested_label"]].append(r)
    labels = ["TRANSACTION", "AD", "HARASS", "FRAUD", "NEEDS_REVIEW"]
    # Aim for roughly even mix; leftover filled from remainder.
    per = max(1, size // max(1, sum(1 for lab in labels if by.get(lab))))
    picked: List[dict] = []
    for lab in labels:
        pool = by.get(lab, [])
        n = min(per, len(pool))
        if n:
            picked.extend(rng.sample(pool, n))
    if len(picked) < size:
        remain = [r for r in records if r not in picked]
        need = size - len(picked)
        if remain:
            picked.extend(rng.sample(remain, min(need, len(remain))))
    if len(picked) > size:
        picked = rng.sample(picked, size)
    rng.shuffle(picked)
    out = []
    for i, r in enumerate(picked):
        row = dict(r)
        row["id"] = f"{id_prefix}_{i:04d}"
        out.append(row)
    return out


def load_yudiwbs(path: Path) -> List[dict]:
    records: List[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            text = (row.get("Teks") or row.get("teks") or row.get("text") or "").strip()
            orig = (row.get("label") or "").strip()
            if not text:
                continue
            suggested, reason = suggest_id(orig, text)
            records.append(
                {
                    "id": f"id_yudi_{i:05d}",
                    "text": text,
                    "language": "id",
                    "source": "yudiwbs_id_sms_spam_v1",
                    "orig_label": orig,
                    "suggested_label": suggested,
                    "suggest_reason": reason,
                    "label": "",
                    "annotator": "",
                    "template_group": template_group(text),
                    "notes": "",
                }
            )
    return records


def load_spamshield_id(path: Path) -> List[dict]:
    records: List[dict] = []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            text = str(obj.get("text") or "").strip()
            if not text:
                continue
            lab = obj.get("label")
            cat = str(obj.get("category") or "")
            if lab in (0, "0", "ham"):
                orig = "ham"
            elif lab in (1, "1", "spam"):
                orig = "spam"
            else:
                orig = str(lab)
            suggested, reason = suggest_id(orig if orig != "spam" else "1", text)
            if orig == "ham" and suggested == "NEEDS_REVIEW":
                reason = "orig-ham-chat-or-unclear"
            records.append(
                {
                    "id": f"id_ss_{i:05d}",
                    "text": text,
                    "language": "id",
                    "source": "spamshield_indonesian_v1",
                    "orig_label": f"{orig}:{cat}" if cat else orig,
                    "suggested_label": suggested,
                    "suggest_reason": reason,
                    "label": "",
                    "annotator": "",
                    "template_group": template_group(text),
                    "notes": "may-include-mt-uci-style",
                }
            )
    return records


def load_iiitd(base: Path) -> List[dict]:
    records: List[dict] = []
    pairs: List[Tuple[str, Path]] = []
    ham_dir = base / "Ham SMSes"
    spam_dir = base / "Spam SMSes"
    if ham_dir.is_dir():
        pairs.extend(("ham", p) for p in sorted(ham_dir.glob("*.txt")))
    if spam_dir.is_dir():
        pairs.extend(("spam", p) for p in sorted(spam_dir.glob("*.txt")))
    for i, (orig, path) in enumerate(pairs):
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if not text:
            continue
        suggested, reason = suggest_hi(orig, text)
        records.append(
            {
                "id": f"iiitd_{i:05d}",
                "text": text,
                "language": "hi",
                "source": "iiitd_sms_spam_v1",
                "orig_label": orig,
                "suggested_label": suggested,
                "suggest_reason": reason,
                "label": "",
                "annotator": "",
                "template_group": template_group(text),
                "notes": "latin-script-hinglish-or-en-IN;not-devanagari",
            }
        )
    return records


def write_id_readme(path: Path, counts: Dict[str, object]) -> None:
    path.write_text(
        "\n".join(
            [
                "印尼语四分类标注说明（作业用）",
                "",
                "请优先打开：id_yudiwbs_pilot_500.csv",
                "补充可标：id_spamshield_pilot_500.csv（含较多机翻痕迹，建议次优先）",
                "",
                "你只要填两列：",
                "  1) label = TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW",
                "  2) annotator = 你的名字",
                "",
                "强制判断顺序（与中英文一致）：",
                "  ① 是不是在骗我？ → FRAUD",
                "  ② 是不是账户/订单/认证/物流业务结果？ → TRANSACTION",
                "  ③ 是不是正规商家促销/订阅？ → AD",
                "  ④ 是不是骚扰/灰产/催收？ → HARASS",
                "  ⑤ 不确定 / 私人闲聊 → NEEDS_REVIEW",
                "",
                "orig_label 含义：",
                "  yudiwbs: 0=normal, 1=fraud/penipuan, 2=promo",
                "  spamshield: ham/spam + category",
                "",
                "注意：",
                "  - suggested_label 只是机器建议，请人工写入 label",
                "  - 不要把私人闲聊硬标成 TRANSACTION",
                "  - SpamShield 印尼子集可能含 UCI 机翻句式，拿不准就 NEEDS_REVIEW",
                "",
                f"统计：{counts}",
                "",
                "完整说明：docs/labeling-guide.md",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_hi_readme(path: Path, counts: Dict[str, object]) -> None:
    path.write_text(
        "\n".join(
            [
                "印地/印度短信四分类标注说明（作业用）",
                "",
                "请打开：iiitd_pilot_500.csv",
                "",
                "你只要填两列：",
                "  1) label = TRANSACTION / AD / HARASS / FRAUD / NEEDS_REVIEW",
                "  2) annotator = 你的名字",
                "",
                "重要：",
                "  - 本集 language 记为 hi，但正文多为拉丁文 Hinglish / 印度英语",
                "  - 几乎没有天城文 Devanagari；不能当「纯印地文」验收金标",
                "  - ham 里大量私人闲聊 → NEEDS_REVIEW",
                "  - spam 里很多问答促销/quiz → 倾向 AD，不要一律 FRAUD",
                "",
                "强制判断顺序：FRAUD → TRANSACTION → AD → HARASS → NEEDS_REVIEW",
                "",
                f"统计：{counts}",
                "",
                "完整说明：docs/labeling-guide.md",
                "",
            ]
        ),
        encoding="utf-8",
    )


def emit_pack(
    records: List[dict],
    out_dir: Path,
    all_name: str,
    pilot_name: str,
    pilot_prefix: str,
    pilot_size: int,
    seed: int,
) -> Tuple[Path, Path, Counter]:
    all_path = out_dir / all_name
    pilot_path = out_dir / pilot_name
    write_csv(all_path, records)
    pilot = balanced_pilot(records, min(pilot_size, len(records)), seed, pilot_prefix)
    write_csv(pilot_path, pilot)
    return all_path, pilot_path, Counter(r["suggested_label"] for r in records)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build hi/id annotation CSV packs.")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--pilot-size", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--yudiwbs",
        type=Path,
        default=RAW / "yudiwbs_id_sms_spam_v1" / "dataset_sms_spam_v1.csv",
    )
    p.add_argument(
        "--spamshield",
        type=Path,
        default=RAW / "spamshield_indonesian" / "clean-00001.jsonl",
    )
    p.add_argument("--iiitd", type=Path, default=RAW / "iiitd_sms_spam")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    missing = [str(p) for p in (args.yudiwbs, args.spamshield, args.iiitd) if not p.exists()]
    if missing:
        print("Missing inputs:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 1

    yudi = load_yudiwbs(args.yudiwbs)
    ss = load_spamshield_id(args.spamshield)
    iiitd = load_iiitd(args.iiitd)

    y_all, y_pilot, y_dist = emit_pack(
        yudi, out_dir, "id_yudiwbs_all_suggested.csv", "id_yudiwbs_pilot_500.csv", "id_yudi_pilot", args.pilot_size, args.seed
    )
    s_all, s_pilot, s_dist = emit_pack(
        ss,
        out_dir,
        "id_spamshield_all_suggested.csv",
        "id_spamshield_pilot_500.csv",
        "id_ss_pilot",
        args.pilot_size,
        args.seed + 1,
    )
    i_all, i_pilot, i_dist = emit_pack(
        iiitd, out_dir, "iiitd_all_suggested.csv", "iiitd_pilot_500.csv", "iiitd_pilot", args.pilot_size, args.seed + 2
    )

    write_id_readme(
        out_dir / "README_ID_ANNOTATORS.txt",
        {
            "yudiwbs_all": len(yudi),
            "yudiwbs_suggested": dict(y_dist),
            "spamshield_all": len(ss),
            "spamshield_suggested": dict(s_dist),
        },
    )
    write_hi_readme(
        out_dir / "README_HI_ANNOTATORS.txt",
        {"iiitd_all": len(iiitd), "iiitd_suggested": dict(i_dist)},
    )

    print(f"yudiwbs: {len(yudi)} -> {y_all.name} / {y_pilot.name} dist={dict(y_dist)}")
    print(f"spamshield: {len(ss)} -> {s_all.name} / {s_pilot.name} dist={dict(s_dist)}")
    print(f"iiitd: {len(iiitd)} -> {i_all.name} / {i_pilot.name} dist={dict(i_dist)}")
    print(f"Wrote README_ID_ANNOTATORS.txt / README_HI_ANNOTATORS.txt under {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
