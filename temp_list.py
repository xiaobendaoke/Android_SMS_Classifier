import json, re, sys

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\WOSHIN~1\AppData\Local\Temp\opencode\chunk_6.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total messages: {len(data)}")

# Print all messages with index for review
for i, item in enumerate(data):
    mid, text = item[0], item[1]
    print(f"{i}\t{mid}\t{text}")
