import csv, sys
sys.stdout.reconfigure(encoding='utf-8')

ids = ['uci_00607','uci_00660','uci_00713','uci_00751','uci_00761','uci_00815','uci_00837','uci_00881']
rows = list(csv.DictReader(open(r'C:\Users\woshinibaba\Documents\oppo的项目\Android_SMS_Classifier\training\data\interim\annotation\chunks\chunk_02.csv','r',encoding='utf-8')))
for r in rows:
    if r['id'] in ids:
        print(f"{r['id']} | label={r['label']} | {r['text'][:150]}")
