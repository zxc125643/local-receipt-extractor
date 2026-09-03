import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

with open(r"F:\project\nixiang\outlook-batch-manager\work\pricing.json", encoding="utf-8") as f:
    pricing = json.load(f)
with open(r"F:\project\nixiang\outlook-batch-manager\work\docx_dump.json", encoding="utf-8") as f:
    docx = json.load(f)
with open(r"F:\project\nixiang\outlook-batch-manager\work\xlsx_dump.json", encoding="utf-8") as f:
    ref = json.load(f)


def norm(s):
    s = re.sub(r"\s+", "", s or "")
    s = s.replace("（", "(").replace("）", ")").replace("：", ":").replace("，", ",")
    return s


def word_items(table_idx):
    rows = docx["tables"][table_idx]["rows"]
    items = []
    system = ""
    for r in rows[1:]:
        while len(r) < 6:
            r.append("")
        if r[1].strip():
            system = r[1].strip()
        items.append(
            {
                "system": system,
                "name": r[2].strip(),
                "spec": r[3].strip(),
                "unit": r[4].strip(),
                "qty": r[5].strip(),
            }
        )
    return items


section_ids = [f"s{i:02d}" for i in range(1, 17)]
word_table_ids = list(range(19, 35))
mismatches = []
for sid, tid in zip(section_ids, word_table_ids):
    want = word_items(tid)
    got = [
        {"system": r[0], "name": r[1], "spec": r[2], "unit": r[3], "qty": str(r[4])}
        for r in next(s["rows"] for s in pricing["sections"] if s["id"] == sid)
    ]
    if len(want) != len(got):
        mismatches.append(f"{sid}: item count word={len(want)} quote={len(got)}")
        continue
    for i, (a, b) in enumerate(zip(want, got)):
        if norm(a["name"]) != norm(b["name"]):
            mismatches.append(f"{sid}[{i}] name: word={a['name']!r} quote={b['name']!r}")
        if norm(a["spec"]) != norm(b["spec"]):
            mismatches.append(f"{sid}[{i}] spec differs: word={a['spec'][:40]!r} quote={b['spec'][:40]!r}")
        if a["unit"] and a["unit"] != b["unit"]:
            mismatches.append(f"{sid}[{i}] unit: word={a['unit']!r} quote={b['unit']!r}")
        if a["qty"] and a["qty"] != b["qty"]:
            mismatches.append(f"{sid}[{i}] qty: word={a['qty']!r} quote={b['qty']!r}")

print("WORD_MISMATCHES:", len(mismatches))
for m in mismatches:
    print(" -", m)

# Reference price floor check
ws = ref["sheets"][0]
ref_rows = {
    s: [
        (ws["rows"][row - 1][2]["v"], ws["rows"][row - 1][7]["v"])
        for row in range(start, end + 1)
        if ws["rows"][row - 1][7]["v"] is not None
        and ws["rows"][row - 1][2]["v"]
        and ws["rows"][row - 1][2]["v"] != "设备名称"
        and ws["rows"][row - 1][2]["v"] != "人工部分"
    ]
    for s, start, end in [
        ("s01", 8, 26),
        ("s02", 30, 48),
        ("s03", 52, 70),
        ("s04", 74, 79),
        ("s05", 83, 88),
        ("s06", 92, 98),
        ("s07", 102, 107),
        ("s08", 111, 116),
        ("s09", 120, 125),
        ("s10", 129, 135),
        ("s11", 139, 145),
        ("s12", 149, 153),
        ("s13", 157, 161),
        ("s14", 165, 169),
        ("s15", 173, 178),
        ("s16", 182, 187),
    ]
}

price_issues = []
for sid in section_ids:
    quote_rows = next(s["rows"] for s in pricing["sections"] if s["id"] == sid)
    ref_list = ref_rows[sid]
    for qr in quote_rows:
        qname = norm(qr[1])
        for rname, rprice in ref_list:
            if norm(rname) == qname and isinstance(rprice, (int, float)):
                if qr[5] < rprice:
                    price_issues.append(f"{sid} {qr[1]}: quote={qr[5]} < ref={rprice}")
                break

print("PRICE_FLOOR_ISSUES:", len(price_issues))
for m in price_issues:
    print(" -", m)

item_count = sum(len(s["rows"]) for s in pricing["sections"])
print("TOTAL_ITEM_ROWS:", item_count)
