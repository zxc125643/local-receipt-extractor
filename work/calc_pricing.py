import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
with open(r"F:\project\nixiang\outlook-batch-manager\work\pricing.json", encoding="utf-8") as f:
    data = json.load(f)

total = 0
for sec in data["sections"]:
    st = sum(row[4] * row[5] for row in sec["rows"])
    total += st
    print(f"{sec['id']} {sec['title']}: {st:,.2f}  rows={len(sec['rows'])}")

eq = sum(
    sum(row[4] * row[5] for row in sec["rows"])
    for sec in data["sections"]
    if sec["id"] in {f"s{i:02d}" for i in range(1, 17)}
)
support = sum(
    sum(row[4] * row[5] for row in sec["rows"])
    for sec in data["sections"]
    if sec["id"] == "s17"
)
transport = sum(
    sum(row[4] * row[5] for row in sec["rows"])
    for sec in data["sections"]
    if sec["id"] == "s18"
)
install = sum(
    sum(row[4] * row[5] for row in sec["rows"])
    for sec in data["sections"]
    if sec["id"] == "s19"
)
print(f"设备材料小计: {eq:,.2f}")
print(f"辅材及配套: {support:,.2f}")
print(f"包装运输: {transport:,.2f}")
print(f"安装调试: {install:,.2f}")
print(f"未税合计: {total:,.2f}")
print(f"税额(13%): {total*0.13:,.2f}")
print(f"含税总价: {total*1.13:,.2f}")
