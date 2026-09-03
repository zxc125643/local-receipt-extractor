import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const workDir = "F:/project/nixiang/outlook-batch-manager/work";
const data = JSON.parse(await fs.readFile(path.join(workDir, "pricing.json"), "utf8"));

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("报价单");
const termsSheet = workbook.worksheets.add("报价说明");

sheet.showGridLines = false;
termsSheet.showGridLines = false;

const widths = {
  A: 6,
  B: 18,
  C: 22,
  D: 58,
  E: 7,
  F: 8,
  G: 13,
  H: 15,
  I: 15,
  J: 26,
};
for (const [col, w] of Object.entries(widths)) {
  sheet.getRange(`${col}:${col}`).format.columnWidth = w;
}

const colors = {
  dark: "#1F4E5F",
  mid: "#2E6E81",
  light: "#DDEBF0",
  lighter: "#F2F6F8",
  gray: "#F4F4F4",
  border: "#C9D2D9",
  text: "#1F2A30",
};

function setRowHeight(row, height) {
  sheet.getRange(`${row}:${row}`).format.rowHeight = height;
}

function styleMerged(rangeAddr, value, opts = {}) {
  const range = sheet.getRange(rangeAddr);
  range.merge();
  range.values = [[value]];
  const fmt = {
    font: { bold: opts.bold ?? false, size: opts.size ?? 10, color: opts.color ?? colors.text },
    fill: opts.fill ?? "#FFFFFF",
    horizontalAlignment: opts.align ?? "left",
    verticalAlignment: "center",
    wrapText: opts.wrap ?? false,
  };
  range.format = fmt;
  if (opts.rowHeight) setRowHeight(rangeAddr.split(":")[0].replace(/\D/g, ""), opts.rowHeight);
  return range;
}

// ---------- Header ----------
const titleCell = sheet.getRange("A1:J1");
titleCell.merge();
titleCell.values = [[`${data.project}\n工 程 报 价 单`]];
titleCell.format = {
  font: { bold: true, size: 18, color: "#FFFFFF" },
  fill: colors.dark,
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
setRowHeight(1, 52);

styleMerged("A2:J2", "报价单编号：QY-2026-001    报价日期：2026年08月06日    币种：人民币（CNY）", {
  fill: colors.lighter,
  align: "center",
  rowHeight: 24,
});
styleMerged("A3:J3", "报价单位：待填写    联系人：待填写    联系电话：待填写    电子邮箱：待填写", {
  fill: colors.lighter,
  align: "center",
  rowHeight: 24,
});
styleMerged("A4:J4", `项目名称：${data.project}`, {
  fill: colors.lighter,
  align: "center",
  rowHeight: 24,
});
setRowHeight(5, 8);

// Pre-compute section subtotal rows so summary formulas can reference them.
let cursor = 18;
const subRows = {};
for (const sec of data.sections) {
  cursor += 1; // section header
  cursor += sec.rows.length;
  subRows[sec.id] = cursor;
  cursor += 1; // subtotal row
}
const equipmentSubCells = Object.entries(subRows)
  .filter(([id]) => !["s17", "s18", "s19"].includes(id))
  .map(([, row]) => `$H$${row}`)
  .join("+");

// ---------- Summary panel ----------
styleMerged("A6:J6", "报 价 汇 总", {
  bold: true,
  fill: colors.dark,
  color: "#FFFFFF",
  align: "center",
  rowHeight: 26,
});

const summaryRows = [
  ["设备及材料小计（第一至十六项）", `=${equipmentSubCells}`, false],
  ["辅材及配套费用（第十七项）", `=$H$${subRows.s17}`, false],
  ["包装及运输费用（第十八项）", `=$H$${subRows.s18}`, false],
  ["安装调试及技术服务费（第十九项）", `=$H$${subRows.s19}`, false],
  ["未税合计", "=SUM($H$7:$H$10)", true],
  ["增值税税率", 0.13, true],
  ["税额", "=$H$11*$H$12", true],
  ["含税总价", "=$H$11+$H$13", true],
];

summaryRows.forEach(([label, value, total], idx) => {
  const row = 7 + idx;
  const labelRange = sheet.getRange(`A${row}:E${row}`);
  labelRange.merge();
  labelRange.values = [[label]];
  labelRange.format = {
    font: { bold: total, size: 10, color: colors.text },
    fill: total ? colors.light : colors.lighter,
    horizontalAlignment: "left",
    verticalAlignment: "center",
    wrapText: false,
  };
  const valCell = sheet.getRange(`H${row}`);
  if (idx === 5) {
    valCell.values = [[value]];
  } else if (typeof value === "string") {
    valCell.formulas = [[value]];
  } else {
    valCell.values = [[value]];
  }
  valCell.format = {
    font: { bold: total, size: 11, color: total ? "#0B3C49" : colors.text },
    fill: total ? colors.light : colors.lighter,
    horizontalAlignment: "right",
    verticalAlignment: "center",
    numberFormat: idx === 5 ? "0%" : "#,##0.00",
  };
  setRowHeight(row, 24);
});

styleMerged(
  "A15:J15",
  "说明：本报价含设备材料、安装辅材、包装运输、国际海运及保险、泰国当地运输、安装调试和培训；不含土建基础及防腐、甲方一次侧电源进线、给排水接驳、生产线支管、第三方检测及泰国当地关税（如需）。",
  { fill: colors.lighter, wrap: true, rowHeight: 30 }
);

// ---------- Detail table ----------
styleMerged(
  "A16:J16",
  "一、设备及材料清单（依据《汇钻泰国一期废气处理及送新风设计方案-20260717》中“一期设备及材料清单”编制，未遗漏、未改项）",
  { bold: true, fill: colors.light, rowHeight: 26 }
);

const headers = ["序号", "系统/分项", "设备或材料名称", "规格型号及技术参数", "单位", "数量", "未税单价（元）", "未税金额（元）", "品牌或产地", "备注"];
sheet.getRange("A17:J17").values = [headers];
sheet.getRange("A17:J17").format = {
  font: { bold: true, size: 10, color: "#FFFFFF" },
  fill: colors.mid,
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
  borders: { preset: "all", style: "thin", color: colors.border },
};
setRowHeight(17, 30);

let seq = 1;
let r = 18;
const itemRanges = [];

for (const sec of data.sections) {
  // Section header
  styleMerged(`A${r}:J${r}`, sec.title, {
    bold: true,
    fill: "#DCE8ED",
    rowHeight: 24,
  });
  sheet.getRange(`A${r}:J${r}`).format.horizontalAlignment = "left";
  r += 1;

  const start = r;
  for (const row of sec.rows) {
    const [system, name, spec, unit, qty, price, brand, note] = row;
    sheet.getRange(`A${r}`).values = [[seq]];
    sheet.getRange(`B${r}`).values = [[system]];
    sheet.getRange(`C${r}`).values = [[name]];
    sheet.getRange(`D${r}`).values = [[spec]];
    sheet.getRange(`E${r}`).values = [[unit]];
    sheet.getRange(`F${r}`).values = [[qty]];
    sheet.getRange(`G${r}`).values = [[price]];
    sheet.getRange(`H${r}`).formulas = [[`=F${r}*G${r}`]];
    sheet.getRange(`I${r}`).values = [[brand]];
    sheet.getRange(`J${r}`).values = [[note]];

    const rowRange = sheet.getRange(`A${r}:J${r}`);
    rowRange.format = {
      font: { size: 10, color: colors.text },
      horizontalAlignment: "left",
      verticalAlignment: "center",
      wrapText: true,
      borders: { preset: "all", style: "thin", color: colors.border },
    };
    sheet.getRange(`A${r}`).format.horizontalAlignment = "center";
    sheet.getRange(`E${r}`).format.horizontalAlignment = "center";
    sheet.getRange(`F${r}`).format.horizontalAlignment = "center";
    sheet.getRange(`F${r}`).format.numberFormat = "0";
    sheet.getRange(`G${r}`).format = {
      numberFormat: "#,##0.00",
      horizontalAlignment: "right",
      verticalAlignment: "center",
      font: { size: 10, color: colors.text },
    };
    sheet.getRange(`H${r}`).format = {
      numberFormat: "#,##0.00",
      horizontalAlignment: "right",
      verticalAlignment: "center",
      font: { size: 10, color: colors.text },
    };
    sheet.getRange(`I${r}`).format.horizontalAlignment = "center";
    setRowHeight(r, 44);
    itemRanges.push(`A${r}:J${r}`);
    seq += 1;
    r += 1;
  }
  const end = r - 1;

  const subLabel = sheet.getRange(`A${r}:E${r}`);
  subLabel.merge();
  subLabel.values = [[`${sec.title}  小计`]];
  subLabel.format = {
    font: { bold: true, size: 10, color: colors.text },
    fill: colors.gray,
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  const subVal = sheet.getRange(`H${r}`);
  subVal.formulas = [[`=SUM(H${start}:H${end})`]];
  subVal.format = {
    font: { bold: true, size: 10, color: "#0B3C49" },
    fill: colors.gray,
    horizontalAlignment: "right",
    verticalAlignment: "center",
    numberFormat: "#,##0.00",
  };
  sheet.getRange(`A${r}:J${r}`).format.borders = {
    preset: "all",
    style: "thin",
    color: colors.border,
  };
  setRowHeight(r, 24);
  r += 1;
}

// ---------- Bottom totals ----------
const bottomRows = [
  ["一至十六项 设备材料小计", `=${equipmentSubCells}`],
  ["第十七项 辅材及配套费用小计", `=$H$${subRows.s17}`],
  ["第十八项 包装与运输费用小计", `=$H$${subRows.s18}`],
  ["第十九项 安装调试及技术服务费小计", `=$H$${subRows.s19}`],
];

let totalLabelRow = r;
bottomRows.forEach(([label, formula], idx) => {
  const row = r + idx;
  const labelRange = sheet.getRange(`A${row}:E${row}`);
  labelRange.merge();
  labelRange.values = [[label]];
  labelRange.format = {
    font: { bold: true, size: 10, color: colors.text },
    fill: idx === 3 ? colors.light : colors.lighter,
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  const valCell = sheet.getRange(`H${row}`);
  valCell.formulas = [[formula]];
  valCell.format = {
    font: { bold: true, size: 10, color: colors.text },
    fill: idx === 3 ? colors.light : colors.lighter,
    horizontalAlignment: "right",
    verticalAlignment: "center",
    numberFormat: "#,##0.00",
  };
  sheet.getRange(`A${row}:J${row}`).format.borders = {
    preset: "all",
    style: "thin",
    color: colors.border,
  };
  setRowHeight(row, 24);
});

const taxRateRow = r + 4;
const taxRow = r + 5;
const taxTotalRow = r + 6;

const grandRows = [
  ["未税合计", `=SUM(H${r}:H${r + 3})`, true],
  ["税率", "=H12", true],
  ["税额", `=H${r + 4}*H${r + 5}`, true],
  ["含税总价", `=H${r + 4}+H${r + 6}`, true],
];
grandRows.forEach(([label, formula, total], idx) => {
  const row = r + 4 + idx;
  const labelRange = sheet.getRange(`A${row}:E${row}`);
  labelRange.merge();
  labelRange.values = [[label]];
  labelRange.format = {
    font: { bold: true, size: 11, color: "#0B3C49" },
    fill: colors.light,
    horizontalAlignment: "left",
    verticalAlignment: "center",
  };
  const valCell = sheet.getRange(`H${row}`);
  if (idx === 1) {
    valCell.formulas = [[formula]];
    valCell.format.numberFormat = "0%";
  } else {
    valCell.formulas = [[formula]];
    valCell.format.numberFormat = "#,##0.00";
  }
  valCell.format = {
    font: { bold: true, size: 11, color: "#0B3C49" },
    fill: colors.light,
    horizontalAlignment: "right",
    verticalAlignment: "center",
  };
  sheet.getRange(`A${row}:J${row}`).format.borders = {
    preset: "all",
    style: "thin",
    color: colors.border,
  };
  setRowHeight(row, 26);
});

// ---------- Scope notes and signature ----------
const notesStart = taxTotalRow + 2;
const notes = [
  "报价范围说明：",
  "1. 本报价范围以设计方案中“一期设备及材料清单”为准：3F两套酸碱废气处理系统、两套蒸发式送风系统本期投运；含氰系统及1F/2F酸碱、新风干管本期敷设至管井旁并阀后封闭备用。",
  "2. 本报价含设备材料、安装辅材、包装、国内运输、出口报关港杂、国际海运及保险、泰国清关及内陆运输、安装调试、培训与竣工资料。",
  "3. 本报价不含土建基础及防腐、甲方一次侧电源电缆、给排水接驳、生产线支管、第三方检测、泰国当地关税或增值税（如需），以及不可抗力造成的费用。",
  "4. 报价单内金额均由公式自动计算，数量或单价修改后，小计、未税合计、税额和含税总价自动更新；金额统一保留两位小数。",
  "5. 品牌栏暂以“待定”为主，正式对外使用前应由实际出具报价的公司复核品牌、产地、公司信息并签章授权。",
];
notes.forEach((text, idx) => {
  const row = notesStart + idx;
  styleMerged(`A${row}:J${row}`, text, {
    fill: idx === 0 ? colors.light : "#FFFFFF",
    bold: idx === 0,
    wrap: true,
    rowHeight: idx === 0 ? 22 : 24,
  });
});

const signRow = notesStart + notes.length + 1;
sheet.getRange(`A${signRow}:J${signRow + 2}`).format.borders = {
  preset: "outside",
  style: "medium",
  color: colors.mid,
};
styleMerged(`A${signRow}:E${signRow}`, "客户确认（盖章）：", { bold: true });
styleMerged(`F${signRow}:J${signRow}`, "报价单位确认（盖章）：", { bold: true });
styleMerged(`A${signRow + 1}:E${signRow + 1}`, "", {});
styleMerged(`F${signRow + 1}:J${signRow + 1}`, "", {});
styleMerged(`A${signRow + 2}:E${signRow + 2}`, "日期：            审核：", {});
styleMerged(`F${signRow + 2}:J${signRow + 2}`, "日期：            审核：", {});

sheet.freezePanes.freezeRows(17);

// ---------- Terms sheet ----------
const termsWidths = { A: 7, B: 20, C: 95 };
for (const [col, w] of Object.entries(termsWidths)) {
  termsSheet.getRange(`${col}:${col}`).format.columnWidth = w;
}

const tTitle = termsSheet.getRange("A1:C1");
tTitle.merge();
tTitle.values = [[`${data.project}\n报价说明及商务条款`]];
tTitle.format = {
  font: { bold: true, size: 16, color: "#FFFFFF" },
  fill: colors.dark,
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
termsSheet.getRange("1:1").format.rowHeight = 46;

termsSheet.getRange("A2:C2").values = [["报价单编号：QY-2026-001", "报价日期：2026年08月06日", "币种：人民币（CNY）"]];
termsSheet.getRange("A2:C2").format = {
  font: { size: 10, color: colors.text },
  fill: colors.lighter,
  horizontalAlignment: "center",
  verticalAlignment: "center",
  wrapText: true,
};
termsSheet.getRange("2:2").format.rowHeight = 24;

const termRows = [
  ["1", "报价有效期", "自报价之日起60天内有效。逾期报价可能因原材料价格、汇率及海运运价波动而调整，调整前以双方重新书面确认为准。"],
  ["2", "交货周期", "合同生效并收到预付款后，设备及材料生产备货约45天；跨境运输、目的港清关及现场安装调试验收约75天，整体控制在120天以内，具体以合同及技术协议约定为准。"],
  ["3", "付款方式", "合同签订后支付30%预付款；设备发货前支付40%；安装调试验收合格后支付25%；余款5%作为质保金，质保期满后支付。付款比例可按双方协商调整。"],
  ["4", "运输方式", "国内公路运输至起运港，集装箱或散货海运至泰国口岸，目的港清关后公路运输至厂区。大型塔体、烟囱及超限风管采用分段或加固运输，超限件提前报备并办理相关手续。"],
  ["5", "安装调试范围", "包含设备就位、管道及阀件安装、电气自控接线、单机试车、系统联动调试、达标测试配合及人员培训；不含土建基础施工、生产线支管接驳、第三方检测及消防/环保验收审批。"],
  ["6", "质保期限", "自系统安装调试验收合格之日起12个月。风机、水泵等随机部件按原厂质保标准执行；人为损坏、误操作及易损件除外。"],
  ["7", "税率及发票类型", "本报价按人民币未税价编制，税率13%，可开具增值税专用发票。如适用出口退税、免税政策或泰国当地税务要求，按合同约定及两国税务规定执行。"],
  ["8", "报价包含内容", "设备及材料、安装辅材、包装、国内运输、出口报关港杂、国际海运及货运保险、泰国清关及内陆运输、现场卸车、安装调试、技术培训与竣工资料。"],
  ["9", "报价不包含内容", "土建基础及防腐、甲方一次侧电源电缆与给排水接驳、生产线支管及接口、第三方检测费用、泰国当地关税/增值税（如需）、许可证件及不可抗力或甲方原因造成的费用。"],
  ["10", "汇率及海外风险说明", "本报价以人民币计价；如按泰铢或美元结算，汇率按付款日银行中间价折算。海运受班期、油价、港口拥堵及目的港清关政策影响；泰国雨季施工、当地节假日及现场条件可能影响工期。相关风险及费用调整机制由双方在合同中明确。"],
  ["11", "其他说明", "本报价单由独立环保设备及户外工程单位编制，公司名称、地址、联系人、电话暂为“待填写”。正式使用前，报价内容应由实际出具报价的公司独立复核并授权，不得冒用其他企业信息；本报价单与设计方案中的服务范围、实施界面划分共同构成本次报价范围。"],
];

const termsHeader = termsSheet.getRange("A3:C3");
termsHeader.values = [["序号", "条款", "内容"]];
termsHeader.format = {
  font: { bold: true, size: 10, color: "#FFFFFF" },
  fill: colors.mid,
  horizontalAlignment: "center",
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: colors.border },
};
termsSheet.getRange("3:3").format.rowHeight = 24;

termRows.forEach((row, idx) => {
  const r = 4 + idx;
  termsSheet.getRange(`A${r}:C${r}`).values = [row];
  termsSheet.getRange(`A${r}:C${r}`).format = {
    font: { size: 10, color: colors.text },
    verticalAlignment: "center",
    horizontalAlignment: "left",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: colors.border },
  };
  termsSheet.getRange(`A${r}`).format.horizontalAlignment = "center";
  termsSheet.getRange(`B${r}`).format.font.bold = true;
  termsSheet.getRange(`A${r}`).format.fill = colors.lighter;
  termsSheet.getRange(`B${r}`).format.fill = colors.lighter;
  termsSheet.getRange(`${r}:${r}`).format.rowHeight = idx % 2 === 0 ? 52 : 62;
});

const tNoteRow = 4 + termRows.length + 1;
termsSheet.getRange(`A${tNoteRow}:C${tNoteRow}`).merge();
termsSheet.getRange(`A${tNoteRow}:C${tNoteRow}`).values = [["说明：本报价单中所有金额均为人民币未税价，税额及含税总价以报价单首页自动计算为准。" ]];
termsSheet.getRange(`A${tNoteRow}:C${tNoteRow}`).format = {
  font: { size: 10, color: colors.text },
  fill: colors.light,
  verticalAlignment: "center",
  horizontalAlignment: "left",
  wrapText: true,
};
termsSheet.getRange(`${tNoteRow}:${tNoteRow}`).format.rowHeight = 28;

// ---------- Export ----------
const outputDir = "F:/project/nixiang/outlook-batch-manager/outputs/019fd589-6211-7521-bd51-abc36e736c23";
await fs.mkdir(outputDir, { recursive: true });
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
const outputName = "汇钻泰国一期废气处理及送新风工程报价单-20260806.xlsx";
await xlsx.save(path.join(outputDir, outputName));

// Quick verification output
const insp = await workbook.inspect({
  kind: "table",
  range: "报价单!A6:H14",
  include: "values,formulas",
  tableMaxRows: 12,
  tableMaxCols: 8,
});
console.log(insp.ndjson);
console.log("EXPORTED", path.join(outputDir, outputName));
