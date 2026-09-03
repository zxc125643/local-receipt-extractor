import json
import sys
sys.stdout.reconfigure(encoding="utf-8")
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

src = r"C:\Users\yiliu\Desktop\（空白）汇钻泰国一期废气处理及送新风设计方案-20260717.docx"
doc = Document(src)

body = doc.element.body
out = {"paragraphs": [], "tables": []}


def iter_block_items(parent):
    from docx.document import Document as _Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    if isinstance(parent, _Document):
        parent_elm = parent.element.body
    else:
        parent_elm = parent
    for child in parent_elm.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, parent)
        elif child.tag == qn("w:tbl"):
            yield Table(child, parent)


pi = 0
ti = 0
for block in iter_block_items(doc):
    if isinstance(block, Paragraph):
        text = block.text.strip()
        if text:
            out["paragraphs"].append(
                {
                    "i": pi,
                    "text": text,
                    "style": block.style.name if block.style else "",
                }
            )
        pi += 1
    else:
        rows = []
        for r in block.rows:
            cells = []
            for c in r.cells:
                # Deduplicate merged cell text; python-docx repeats merged cells.
                seen = set()
                txts = []
                for p in c.paragraphs:
                    t = p.text.strip()
                    if t and t not in seen:
                        seen.add(t)
                        txts.append(t)
                cells.append("\n".join(txts))
            rows.append(cells)
        out["tables"].append({"i": ti, "rows": rows})
        ti += 1

print(json.dumps(out, ensure_ascii=False, indent=1))
