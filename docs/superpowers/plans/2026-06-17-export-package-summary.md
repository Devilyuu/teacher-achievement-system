# Export Package Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a human-readable `00_导出说明.txt` file to each personal annual ZIP export package.

**Architecture:** Keep `build_personal_export()` as the export entry point. Add a small helper in `app/services/export_builder.py` that writes summary text directly into the ZIP with `archive.writestr()`.

**Tech Stack:** Python `zipfile`, SQLAlchemy-loaded export data, pytest.

---

## File Structure

- Modify `tests/test_exports.py`
  - Extend the export-builder ZIP test to assert summary-file presence and content.
- Modify `app/services/export_builder.py`
  - Add summary generation and write `00_导出说明.txt` into the ZIP.

### Task 1: Add Failing ZIP Summary Test

**Files:**
- Modify: `tests/test_exports.py`

- [ ] **Step 1: Write failing assertions**

In `test_build_personal_export_creates_zip_workbooks_and_category_materials`, add one incomplete achievement without materials before `db.commit()`:

```python
incomplete = Achievement(
    user_id=user.id,
    year=year,
    category="科研与社会服务工作",
    subcategory="横向课题及项目",
    claim_nature=ClaimNature.result.value,
    title="待完善导出说明成果",
    claimed_score=0,
    status=AchievementStatus.needs_info.value,
)
db.add(incomplete)
```

Then read the summary from the ZIP:

```python
with ZipFile(zip_path) as archive:
    names = archive.namelist()
    summary = archive.read("00_导出说明.txt").decode("utf-8")
```

Assert:

```python
assert "00_导出说明.txt" in names
assert f"年度：{year}" in summary
assert f"教师：{user.full_name}" in summary
assert "成果总数：3" in summary
assert "支撑材料总数：2" in summary
assert "待完善成果：1" in summary
assert "缺少材料成果：1" in summary
assert "待完善导出说明成果" in summary
assert "最终分值和级别认定仍以线下审核为准" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_build_personal_export_creates_zip_workbooks_and_category_materials -q
```

Expected result: FAIL because `00_导出说明.txt` is not currently in the ZIP.

### Task 2: Implement ZIP Summary File

**Files:**
- Modify: `app/services/export_builder.py`
- Test: `tests/test_exports.py`

- [ ] **Step 1: Add summary writer**

In `app/services/export_builder.py`, import `AchievementStatus` and add:

```python
def _summary_text(user: User, year: int, achievements: list[Achievement]) -> str:
    ready_statuses = {
        AchievementStatus.ready.value,
        AchievementStatus.exported.value,
    }
    ready_count = sum(item.status in ready_statuses for item in achievements)
    needs_attention = [item for item in achievements if item.status not in ready_statuses]
    material_count = sum(len(item.materials) for item in achievements)
    missing_materials = [item for item in achievements if not item.materials]

    lines = [
        "教师个人年度绩效材料包导出说明",
        f"年度：{year}",
        f"教师：{user.full_name}",
        f"成果总数：{len(achievements)}",
        f"可导出成果：{ready_count}",
        f"待完善成果：{len(needs_attention)}",
        f"支撑材料总数：{material_count}",
        f"缺少材料成果：{len(missing_materials)}",
        "",
        "说明：最终分值和级别认定仍以线下审核为准。",
    ]
    if needs_attention:
        lines.extend(["", "待完善成果清单："])
        for achievement in needs_attention:
            lines.append(
                f"- {achievement.title}｜{achievement.status}｜{achievement.category} / {achievement.subcategory}"
            )
    return "\n".join(lines) + "\n"
```

Pass `user` and `year` into `_write_zip()` and call:

```python
archive.writestr("00_导出说明.txt", _summary_text(user, year, achievements))
```

- [ ] **Step 2: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_build_personal_export_creates_zip_workbooks_and_category_materials -q
```

Expected result: PASS.

### Task 3: Verification and Commit

**Files:**
- Modify: `tests/test_exports.py`
- Modify: `app/services/export_builder.py`

- [ ] **Step 1: Run export and full tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py -q
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected result: both pytest commands exit 0 and `git diff --check` exits 0.

- [ ] **Step 2: Commit**

```powershell
git add tests/test_exports.py app/services/export_builder.py
git commit -m "feat: add export package summary"
```

## Self-Review

- Spec coverage: The plan adds the summary file, count fields, offline-review reminder, and incomplete-achievement listing.
- Placeholder scan: No placeholder tasks remain.
- Type consistency: Uses existing `Achievement`, `AchievementStatus`, and `User` model names.
