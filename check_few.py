#!/usr/bin/env python3
"""Check specific IDs' labels."""
import csv, sys
csv.field_size_limit(sys.maxsize)

INPATH = "training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv"

with open(INPATH, "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    check = ["zh-n2w-01141", "zh-n2w-02538", "zh-n2w-03977",
             "zh-n2w-04550", "zh-n2w-00627", "zh-n2w-01426"]
    for row in reader:
        if row["id"] in check:
            print(f'{row["id"]}: label={row["label"]!r}, notes={row["notes"]!r}')
            print(f'  text: {row["text"][:70]}')
            print()