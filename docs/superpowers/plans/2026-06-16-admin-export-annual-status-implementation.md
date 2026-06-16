# Admin Export Annual Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Include each teacher's annual submission status in administrator summary workbooks.

**Architecture:** Reuse `AdminSummary.teachers[*].annual_state.status`, which already powers the admin summary page. Add one `年度状态` column to the `教师汇总` worksheet in `app/services/admin_export_builder.py`; the standalone workbook and the workbook embedded in material ZIP packages share that writer.

**Tech Stack:** Python, FastAPI service layer, openpyxl, pytest.

---

### Task 1: Add Annual Status To Admin Summary Workbook

**Files:**
- Modify: `tests/test_admin_summary.py`
- Modify: `app/services/admin_export_builder.py`

- [ ] **Step 1: Write failing workbook tests**

Add assertions to `test_admin_summary_workbook_contains_three_filtered_sheets`:

```python
confirm_annual_submission(db, teacher, 2026)
summary = build_admin_summary(
    db,
    SummaryFilters(year=2026, department=department),
)
workbook = load_workbook(build_admin_summary_workbook(summary))
teacher_sheet = workbook["教师汇总"]
assert teacher_sheet.cell(1, 4).value == "年度状态"
assert teacher_sheet.cell(2, 4).value == "已提交"
assert teacher_sheet.cell(2, 5).value == 2
assert teacher_sheet.cell(2, 9).value == 9
```

Add assertions to `test_empty_admin_summary_workbook_still_contains_headers`:

```python
assert "年度状态" in [
    workbook["教师汇总"].cell(1, column).value
    for column in range(1, workbook["教师汇总"].max_column + 1)
]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_admin_summary.py::test_admin_summary_workbook_contains_three_filtered_sheets tests/test_admin_summary.py::test_empty_admin_summary_workbook_still_contains_headers -q
```

Expected: fail because `教师汇总` has no `年度状态` column.

- [ ] **Step 3: Implement workbook column**

Update `TEACHER_HEADERS` in `app/services/admin_export_builder.py` to insert `年度状态` after `账号状态`. Update teacher row appends to write `row.annual_state.status` in the same position.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same pytest command. Expected: pass.

### Task 2: Verify Material Package Embedded Workbook

**Files:**
- Modify: `tests/test_admin_summary.py`

- [ ] **Step 1: Write package assertion**

In `test_admin_material_package_groups_files_and_reports_missing_physical_file`, add:

```python
teacher_sheet = workbook["教师汇总"]
assert "年度状态" in [teacher_sheet.cell(1, column).value for column in range(1, teacher_sheet.max_column + 1)]
```

- [ ] **Step 2: Run focused package test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_admin_summary.py::test_admin_material_package_groups_files_and_reports_missing_physical_file -q
```

Expected: pass after Task 1 because the material package reuses the same workbook writer.

### Task 3: Full Verification

**Files:**
- No production changes unless verification reveals a defect.

- [ ] **Step 1: Run admin summary tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_admin_summary.py -q
```

- [ ] **Step 2: Run full test suite and diff check**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

- [ ] **Step 3: Commit**

```powershell
git add app/services/admin_export_builder.py tests/test_admin_summary.py
git commit -m "feat: include annual status in admin export"
```
