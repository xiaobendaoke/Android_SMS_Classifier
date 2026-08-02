#!/usr/bin/env python3
"""Find remaining unlabeled rows and patch them directly."""
import csv, sys
csv.field_size_limit(sys.maxsize)

INPATH = "training/data/interim/annotation/transaction_specialist/transaction_specialist_annotator_A.csv"
ANNOTATOR = "HUMAN_A_001"

# Read using csv.DictReader
with open(INPATH, "r", encoding="utf-8-sig") as f:
    content = f.read()

lines = content.split("\n")
header_raw = lines[0]
# Handle BOM
if header_raw.startswith("\ufeff"):
    header_raw = header_raw[1:]
# Split header
headers = [h.strip().strip('"') for h in header_raw.split(",")]

# Parse rows manually to avoid DictWriter quoting issues
rows = []
for line in lines[1:]:
    if not line.strip():
        continue
    # Parse CSV line respecting quotes
    values = []
    current = ""
    in_quotes = False
    for ch in line:
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == "," and not in_quotes:
            values.append(current)
            current = ""
        else:
            current += ch
    values.append(current)
    
    if len(values) >= len(headers):
        row = dict(zip(headers, values[:len(headers)]))
        rows.append(row)

print(f"Read {len(rows)} rows")
print(f"Headers: {headers}")

# Find unlabeled or default NEEDS_REVIEW without notes
for row in rows:
    rid = row["id"]
    lbl = row.get("label", "")
    notes = row.get("notes", "")
    hid = row.get("human_annotator_id", "")
    
    # Check if label is empty or default
    if not lbl or lbl.strip() == "":
        print(f"EMPTY LABEL: {rid}")
    elif lbl == "NEEDS_REVIEW" and not notes.strip():
        print(f"NR_NO_NOTE: {rid}: {row.get('text','')[:60]}")

print("\n--- All label counts ---")
from collections import Counter
cnt = Counter(r.get("label","") for r in rows)
for lbl, n in sorted(cnt.items()):
    print(f"  {lbl or 'EMPTY'}: {n}")