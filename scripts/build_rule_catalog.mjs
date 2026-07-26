import fs from "node:fs/promises";

const inputPath = process.argv[2];
const outputPath = process.argv[3];
const extracted = JSON.parse((await fs.readFile(inputPath, "utf8")).replace(/^\uFEFF/, ""));

const rules = extracted.map((row, index) => ({
  category: row.category,
  subcategory: row.subcategory,
  base_rule: row.baseRule,
  national_rule: row.nationalRule,
  provincial_rule: row.provincialRule,
  city_rule: row.cityRule,
  school_rule: row.schoolRule,
  college_rule: row.collegeRule,
  remark: row.remark,
  is_team: row.fill === "00B0F0",
  is_department_assigned: row.fill === "FFFF00",
  sort_order: index + 1,
}));

rules.push({
  category: "其他有价值工作（自定义）",
  subcategory: "自定义工作事项",
  base_rule: "",
  national_rule: "",
  provincial_rule: "",
  city_rule: "",
  school_rule: "",
  college_rule: "",
  remark:
    "用于记录现有绩效分类未覆盖但教师认为有必要申报的工作。需填写工作说明、价值说明和支撑材料，最终是否赋分以线下审核为准。",
  is_team: false,
  is_department_assigned: false,
  sort_order: rules.length + 1,
});

const catalog = {
  version: "2025-06-18",
  source: "浮动绩效积分统计.xlsx / 附表1 超额工作绩效积分对照表",
  rules,
};

await fs.mkdir(new URL("../app/data/", import.meta.url), { recursive: true });
await fs.writeFile(outputPath, `${JSON.stringify(catalog, null, 2)}\n`, "utf8");
