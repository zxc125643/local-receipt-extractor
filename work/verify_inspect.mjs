import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const outDir = "F:/project/nixiang/outlook-batch-manager/outputs/019fd589-6211-7521-bd51-abc36e736c23";
const fileName = "汇钻泰国一期废气处理及送新风工程报价单-20260806.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(outDir, fileName)));
const sheet = workbook.worksheets.getItem("报价单");

const summary = await workbook.inspect({
  kind: "table",
  range: "报价单!A7:H14",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 8,
});
console.log("SUMMARY");
console.log(summary.ndjson);

const firstItemFormulas = sheet.getRange("F19:H19").formulas;
console.log("FIRST_ITEM_F19:H19", JSON.stringify(firstItemFormulas));
const s01Sub = await workbook.inspect({
  kind: "formula",
  range: "报价单!A37:H37",
  maxChars: 2000,
});
console.log("S01_SUBTOTAL");
console.log(s01Sub.ndjson);

const bottom = await workbook.inspect({
  kind: "formula",
  range: "报价单!A197:H210",
  maxChars: 5000,
  options: { maxResults: 80 },
});
console.log("BOTTOM");
console.log(bottom.ndjson);

const style = await workbook.inspect({
  kind: "computedStyle",
  range: "报价单!A17:J17",
  maxChars: 2500,
});
console.log("HEADER_STYLE");
console.log(style.ndjson);

const terms = await workbook.inspect({
  kind: "table",
  range: "报价说明!A1:C16",
  include: "values",
  tableMaxRows: 16,
  tableMaxCols: 3,
  tableMaxCellChars: 120,
});
console.log("TERMS");
console.log(terms.ndjson);
