import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const sheet = workbook.worksheets.getItem("附表1 超额工作绩效积分对照表");
const values = sheet.getRange("A4:I81").values;
const rows = [];
let category = "";

for (let index = 0; index < values.length; index += 1) {
  const excelRow = index + 4;
  const row = values[index];
  if (row[0]) category = String(row[0]).trim();
  const styleResult = await workbook.inspect({
    kind: "computedStyle",
    sheetId: "附表1 超额工作绩效积分对照表",
    range: `B${excelRow}`,
    maxChars: 2000,
  });
  const style = JSON.parse(styleResult.ndjson);
  rows.push({
    excelRow,
    category,
    subcategory: String(row[1] ?? "").trim(),
    baseRule: String(row[2] ?? "").trim(),
    nationalRule: String(row[3] ?? "").trim(),
    provincialRule: String(row[4] ?? "").trim(),
    cityRule: String(row[5] ?? "").trim(),
    schoolRule: String(row[6] ?? "").trim(),
    collegeRule: String(row[7] ?? "").trim(),
    remark: String(row[8] ?? "").trim(),
    fill: style.style?.fill?.color?.value ?? "",
  });
}

console.log(JSON.stringify(rows, null, 2));
