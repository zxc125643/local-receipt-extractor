import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outDir = "F:/project/nixiang/outlook-batch-manager/outputs/019fd589-6211-7521-bd51-abc36e736c23";
const fileName = "汇钻泰国一期废气处理及送新风工程报价单-20260806.xlsx";
const input = await FileBlob.load(path.join(outDir, fileName));
const workbook = await SpreadsheetFile.importXlsx(input);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("FORMULA_ERRORS:", errors.ndjson);

const shots = [
  { sheetName: "报价单", range: "A1:J30", scale: 1.1, name: "quote_top.png" },
  { sheetName: "报价单", range: "A1:J120", scale: 0.75, name: "quote_full.png" },
  { sheetName: "报价说明", range: "A1:C18", scale: 1.3, name: "terms.png" },
];

for (const shot of shots) {
  const blob = await workbook.render({
    sheetName: shot.sheetName,
    range: shot.range,
    scale: shot.scale,
    format: "png",
  });
  await fs.writeFile(path.join(outDir, shot.name), new Uint8Array(await blob.arrayBuffer()));
  console.log("RENDERED", shot.name);
}

const tail = await workbook.inspect({
  kind: "table",
  sheetId: "报价单",
  range: "A200:H220",
  include: "values,formulas",
  tableMaxRows: 25,
  tableMaxCols: 8,
});
console.log("TAIL:");
console.log(tail.ndjson);
