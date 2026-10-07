#!/usr/bin/env python3
"""Check what specific IDs have as labels."""
import csv, sys

csv.field_size_limit(sys.maxsize)

with open('training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    
    check_ids = ['zh_01157', 'zh_05356', 'zh_05773', 'zh-n2w-03977', 'zh-n2w-04389', 'zh-n2w-01141', 'zh-n2w-02538']
    
    found = []
    for row in reader:
        if row['id'] in check_ids:
            found.append((row['id'], row['label'], row['notes']))
            print(f"ID: {row['id']!r}, Label: {row['label']!r}, Notes: {row['notes']!r}")
    
    print(f"\nFound {len(found)} of {len(check_ids)} check IDs")
    
    if len(found) < len(check_ids):
        not_found = [rid for rid in check_ids if rid not in [f[0] for f in found]]
        print(f"Not found: {not_found}")