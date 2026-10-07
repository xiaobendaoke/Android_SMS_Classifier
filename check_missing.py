#!/usr/bin/env python3
"""Check which IDs from the CSV are not in the script's label map."""
import csv, sys, re

csv.field_size_limit(sys.maxsize)

with open('training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    actual_ids = [row['id'] for row in reader]

with open('annotate_a.py', 'r', encoding='utf-8') as f:
    script = f.read()

script_ids = set()

# Extract all set_label('...', ...) calls
for m in re.finditer(r"set_label\(['\"]([^'\"]+)['\"]", script):
    script_ids.add(m.group(1))

# Extract IDs from list assignments (XXX_ids = [...])
for m in re.finditer(r"(\w+_ids)\s*=\s*\[([^\]]+)\]", script):
    block = m.group(2)
    for id_match in re.finditer(r"['\"]([^'\"]+)['\"]", block):
        script_ids.add(id_match.group(1))

# Extract IDs from for-loop lists
for m in re.finditer(r"for rid in \[([^\]]+)\]", script):
    block = m.group(1)
    for id_match in re.finditer(r"['\"]([^'\"]+)['\"]", block):
        script_ids.add(id_match.group(1))

missing = [rid for rid in actual_ids if rid not in script_ids]
print(f"Total actual: {len(actual_ids)}")
print(f"Total in script: {len(script_ids)}")
print(f"Missing: {len(missing)}")
for rid in missing:
    print(f"  MISSING: {rid}")