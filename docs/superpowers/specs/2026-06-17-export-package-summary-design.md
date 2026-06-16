# Export Package Summary Design

## Background

The personal annual ZIP package currently contains:

- `01_个人项目申报表.xlsx`
- `04_材料目录.xlsx`
- `05_支撑材料/`

This is enough for formal materials, but the receiver has to open Excel files before understanding the package status. A lightweight summary file at the ZIP root can make the exported package easier to inspect and forward.

## Goal

Add a plain-text summary file to each personal annual export package:

`00_导出说明.txt`

The file should provide a quick, human-readable overview of the package.

## Content

The summary file should include:

- teacher name;
- export year;
- total achievement count;
- ready/exported achievement count;
- needs-attention achievement count;
- total uploaded material count;
- achievements without materials count;
- a reminder that final score and level recognition remain subject to offline review.

If there are achievements needing attention, list their titles with status and category/subcategory so a teacher or offline reviewer can quickly see what may still need checking.

## Scope

In scope:

- Add `00_导出说明.txt` to personal annual ZIP packages.
- Generate the summary from the same achievements already used by the export builder.
- Cover the ZIP content with tests.

Out of scope:

- Changing existing Excel workbook names or columns.
- Changing material folder structure.
- Blocking export when incomplete items exist.
- Admin export packages.
- Rich formatting or Word/PDF generation.

## Data Rules

- `可申报` and `已纳入导出` count as ready.
- Other statuses count as needing attention.
- Material count is the total number of uploaded files attached to the exported achievements.
- Achievements without materials are counted separately because this is a common offline review concern.

## Testing

Extend the export-builder test to assert that:

- `00_导出说明.txt` exists in the ZIP.
- The summary includes the teacher name, year, achievement count, material count, needs-attention count, offline-review reminder, and the title of an incomplete achievement.
- Existing Excel and material entries remain in the ZIP.
