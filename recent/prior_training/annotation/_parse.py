import csv, json
entries = []
with open(r'training\data\interim\annotation\iiitd_all_suggested.csv', 'r', encoding='latin-1') as f:
    reader = csv.DictReader(f)
    for row in reader:
        entry_id = row['id']
        num = int(entry_id.split('_')[1])
        if 1000 <= num <= 1699:
            entries.append({'id': entry_id, 'text': row['text'], 'language': row['language'], 'orig_label': row['orig_label']})
entries.sort(key=lambda x: int(x['id'].split('_')[1]))
print(f'Total entries: {len(entries)}')
print(f'First: {entries[0]["id"]}')
print(f'Last: {entries[-1]["id"]}')
for e in entries[:5]:
    print(e['id'], e['text'][:80])
