import { readFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const [input, output, deps] = process.argv.slice(2);
const runtimeRequire = createRequire(path.join(deps, "catalog-loader.cjs"));
const { Workbook, SpreadsheetFile } = runtimeRequire("@oai/artifact-tool");
const sheets = JSON.parse(await readFile(input, "utf8"));
const book = Workbook.create();
for (const { area, name, keys, headers, rows, images } of sheets) {
  const sheet = book.worksheets.add(name);
  const data = sheet.getRangeByIndexes(0, 0, rows.length + 1, headers.length);
  data.setNumberFormat("@");
  data.values = [headers, ...rows];
  const table = sheet.tables.add(data.address.split("!").at(-1), true, "Country_" + area);
  table.style = "TableStyleMedium2";
  data.format.rowHeight = 44;
  data.format.verticalAlignment = "center";
  const heading = sheet.getRangeByIndexes(0, 0, 1, headers.length);
  heading.format.rowHeight = 28;
  heading.format.font.bold = true;
  heading.format.font.color = "#FFFFFF";
  heading.format.fill = "#18475A";
  keys.forEach((key, i) => {
    const col = sheet.getRangeByIndexes(0, i, rows.length + 1, 1);
    const widths = {part_id:16, code:16, wva:34, bfmc:17, oem:28, item:35, application:38,
      picture:22, size_raw:26, rivet_dia:28, length_mm:22};
    col.format.columnWidth = widths[key] ?? 16;
    if (["wva","item","application","oem"].includes(key)) col.format.wrapText = true;
  });
  sheet.freezePanes.freezeRows(1);
  const col = keys.indexOf("picture");
  images.forEach(({ b64, width, height }, index) => {
    sheet.images.add({dataUrl:"data:image/png;base64," + b64, anchor:{
      from:{row:index + 1,col},extent:{widthPx:width,heightPx:height}
    }});
  });
}
const file = await SpreadsheetFile.exportXlsx(book);
await file.save(output);
