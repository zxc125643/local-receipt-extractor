import shutil
import re
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

src = r"F:\project\nixiang\outlook-batch-manager\outputs\019fd589-6211-7521-bd51-abc36e736c23\汇钻泰国一期废气处理及送新风工程报价单-20260806.xlsx"
tmp = r"F:\project\nixiang\outlook-batch-manager\work\quote_with_print.xlsx"

sheet_pr = '<x:sheetPr><x:pageSetUpPr fitToPage="1"/></x:sheetPr>'
page_end = (
    '<x:pageMargins left="0.3" right="0.3" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>'
    '<x:pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0" '
    'horizontalDpi="300" verticalDpi="300"/>'
)

with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename in ("xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml"):
            text = data.decode("utf-8")
            if "<x:pageSetup" not in text:
                if "<x:sheetPr>" not in text:
                    text = text.replace("<x:sheetViews>", sheet_pr + "<x:sheetViews>", 1)
                if "<x:pageMargins" in text:
                    text = re.sub(r"<x:pageMargins[^>]*/>", page_end, text, count=1)
                else:
                    text = text.replace("</x:worksheet>", page_end + "</x:worksheet>", 1)
            data = text.encode("utf-8")
        zout.writestr(item, data)

shutil.copyfile(tmp, src)
print("print setup added")
