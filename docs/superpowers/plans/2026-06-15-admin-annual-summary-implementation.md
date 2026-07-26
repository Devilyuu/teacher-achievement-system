# Admin Annual Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an administrator-only annual summary page with intersecting filters, readiness metrics, an Excel summary workbook, and a multi-teacher material ZIP.

**Architecture:** Add a focused summary query service that owns filtering, aggregation, and missing-reason calculation. Add a separate admin export service that consumes the summary result and creates workbook/ZIP artifacts. Keep admin routes responsible only for parsing parameters, enforcing administrator access, rendering the page, and returning downloads.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Jinja2, OpenPyXL, ZipFile, pytest, FastAPI TestClient.

---

## File Structure

- Create `app/services/admin_summary.py`: filter data model, query construction, aggregate rows, and missing-reason calculation.
- Create `app/services/admin_export_builder.py`: administrator workbook and multi-teacher ZIP generation.
- Create `app/templates/admin/summary.html`: filter bar, metrics, teacher readiness table, detail table, and export actions.
- Create `tests/test_admin_summary.py`: service, page, permission, filtering, workbook, and ZIP behavior.
- Modify `app/routers/admin.py`: summary page, read-only achievement detail, and administrator export routes.
- Modify `app/templates/base.html`: administrator navigation entry and active state.
- Modify `app/static/app.css`: compact summary filters, metrics, tables, empty state, and responsive behavior.

### Task 1: Summary Query Service

**Files:**
- Create: `tests/test_admin_summary.py`
- Create: `app/services/admin_summary.py`

- [ ] **Step 1: Write failing tests for intersecting filters and aggregates**

Create fixtures that add:

- two teachers in different departments;
- active and inactive accounts;
- achievements in 2026 and 2027;
- `待完善` and `可申报` records;
- records with and without materials.

Test:

```python
def test_summary_filters_by_year_department_teacher_and_status(app):
    result = build_admin_summary(
        db,
        SummaryFilters(
            year=2026,
            department="艺术学院",
            teacher_id=teacher.id,
            status=AchievementStatus.ready.value,
        ),
    )
    assert [item.id for item in result.achievements] == [matching.id]
    assert result.metrics.teacher_count == 1
    assert result.metrics.achievement_count == 1
    assert result.metrics.claimed_score == matching.claimed_score
```

Also assert inactive users' historical achievements remain present when they match.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: import failure for `app.services.admin_summary`.

- [ ] **Step 3: Implement summary types and query**

Implement:

```python
@dataclass(frozen=True)
class SummaryFilters:
    year: int
    department: str = ""
    teacher_id: int | None = None
    status: str = ""


@dataclass(frozen=True)
class SummaryMetrics:
    teacher_count: int
    achievement_count: int
    claimed_score: float
    needs_info_count: int
    material_count: int


@dataclass
class AdminSummary:
    filters: SummaryFilters
    achievements: list[Achievement]
    teachers: list[TeacherSummaryRow]
    metrics: SummaryMetrics
```

Build the SQLAlchemy query by joining `Achievement.user`, applying all non-empty conditions, and ordering by department, teacher name, category, and achievement ID. Aggregate from the filtered achievement list so page and exports use identical data.

- [ ] **Step 4: Add and test missing-reason calculation**

Implement `missing_reasons(achievement)` returning a list from:

- `申报信息不完整`
- `申报积分未填写或不大于零`
- `过程性工作缺少进展说明`
- `未上传支撑材料`
- `材料文件不存在`

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: query and missing-reason tests pass.

- [ ] **Step 5: Commit**

```powershell
git add app/services/admin_summary.py tests/test_admin_summary.py
git commit -m "feat: add admin annual summary service"
```

### Task 2: Administrator Summary Page And Permissions

**Files:**
- Modify: `tests/test_admin_summary.py`
- Modify: `app/routers/admin.py`
- Create: `app/templates/admin/summary.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/app.css`

- [ ] **Step 1: Write failing route and page tests**

Test:

```python
def test_admin_summary_requires_admin(app):
    assert TestClient(app).get("/admin/summary", follow_redirects=False).status_code in {303, 401}
    teacher_client.cookies.set("user_id", str(teacher.id))
    assert teacher_client.get("/admin/summary").status_code == 403


def test_admin_summary_page_renders_filters_metrics_and_rows(app):
    response = admin_client.get("/admin/summary?year=2026&department=艺术学院")
    assert response.status_code == 200
    assert "年度汇总" in response.text
    assert teacher.full_name in response.text
    assert achievement.title in response.text
    assert "待完善" in response.text
```

Assert workbook and ZIP links retain `year`, `department`, `teacher_id`, and `status`.

- [ ] **Step 2: Run route tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: `/admin/summary` returns `404`.

- [ ] **Step 3: Add summary route**

Add a `GET /admin/summary` route with:

```python
year: int | None = Query(default=None)
department: str = Query(default="")
teacher_id: int | None = Query(default=None)
achievement_status: str = Query(default="", alias="status")
```

Default year to `datetime.now().year`. Load distinct years, departments, teachers, and `AchievementStatus` values for filter controls. Call `build_admin_summary()` and render `admin/summary.html`.

- [ ] **Step 4: Build compact page UI**

Create:

- one-line desktop filter bar that wraps on narrow screens;
- five statistic items;
- teacher readiness table;
- achievement detail table inside `.table-scroll`;
- workbook and ZIP buttons carrying the current query string;
- empty state when no achievements match.

Add “年度汇总” to the administrator navigation using the `chart-no-axes-combined` Lucide icon.

- [ ] **Step 5: Add administrator read-only detail**

Add `GET /admin/achievements/{achievement_id}` guarded by `require_admin`. Render the existing detail information in read-only form without edit/delete/upload actions. This keeps summary links useful while preserving ownership boundaries.

- [ ] **Step 6: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: permissions, filters, metrics, links, and page content pass.

- [ ] **Step 7: Commit**

```powershell
git add app/routers/admin.py app/templates/admin/summary.html app/templates/base.html app/static/app.css tests/test_admin_summary.py
git commit -m "feat: add admin annual summary page"
```

### Task 3: Summary Workbook Export

**Files:**
- Modify: `tests/test_admin_summary.py`
- Create: `app/services/admin_export_builder.py`
- Modify: `app/routers/admin.py`

- [ ] **Step 1: Write failing workbook tests**

Build a filtered summary and call:

```python
path = build_admin_summary_workbook(summary)
```

Assert:

- filename includes the selected year and department label;
- sheets are exactly `教师汇总`, `成果明细`, `材料缺失`;
- teacher totals and achievement rows match the filtered summary;
- missing sheet includes the calculated reasons;
- an empty result still exports all headers.

- [ ] **Step 2: Run workbook tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: import or function-not-found failure for the admin export builder.

- [ ] **Step 3: Implement workbook builder**

Create a unique directory under:

```text
data/exports/admin/{year}/{uuid}/
```

Use OpenPyXL to create the three sheets. Freeze the first row, enable filters, apply readable column widths, and write numeric score values as numbers. Return the generated `Path`.

- [ ] **Step 4: Add administrator workbook route**

Add:

```text
GET /admin/summary/export.xlsx
```

Accept the same filter parameters as the page, rebuild the same summary, and return `FileResponse` with the generated filename.

- [ ] **Step 5: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: workbook and route tests pass.

- [ ] **Step 6: Commit**

```powershell
git add app/services/admin_export_builder.py app/routers/admin.py tests/test_admin_summary.py
git commit -m "feat: export admin annual summary workbook"
```

### Task 4: Multi-Teacher Material ZIP

**Files:**
- Modify: `tests/test_admin_summary.py`
- Modify: `app/services/admin_export_builder.py`
- Modify: `app/routers/admin.py`

- [ ] **Step 1: Write failing ZIP tests**

Call:

```python
zip_path = build_admin_material_package(summary)
```

Assert the archive contains:

```text
00_年度教师成果汇总.xlsx
01_教师材料/艺术学院/张老师/03_教学/...
```

Assert the material filename includes achievement index, sanitized achievement title, material number, display name, and extension. Add a database material whose physical file is absent and assert export succeeds while the workbook's `材料缺失` sheet contains `材料文件不存在`.

- [ ] **Step 2: Run ZIP tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: missing `build_admin_material_package`.

- [ ] **Step 3: Implement ZIP builder**

Reuse the workbook builder and `CATEGORY_ORDER`. Sanitize Windows-invalid characters:

```text
< > : " / \ | ? *
```

Write only existing physical files. Include the workbook at archive root even when no materials exist.

- [ ] **Step 4: Add ZIP route**

Add:

```text
GET /admin/summary/materials.zip
```

Guard it with `require_admin`, apply identical filters, and return the ZIP with `application/zip`.

- [ ] **Step 5: Run tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: all administrator summary and export tests pass.

- [ ] **Step 6: Commit**

```powershell
git add app/services/admin_export_builder.py app/routers/admin.py tests/test_admin_summary.py
git commit -m "feat: export multi-teacher material package"
```

### Task 5: Regression And Browser Verification

**Files:**
- Modify only if verification reveals a defect.

- [ ] **Step 1: Run focused tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_admin_summary.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full regression suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 3: Run diff validation**

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files and the pre-existing untracked prototype screenshots appear.

- [ ] **Step 4: Browser-check desktop**

Open:

```text
http://127.0.0.1:8001/admin/summary
```

Verify:

- navigation entry is active;
- filters update the URL and displayed rows;
- all five metrics agree with visible data;
- workbook and ZIP download links preserve filters;
- tables remain readable without page-level horizontal overflow;
- browser console contains no errors.

- [ ] **Step 5: Browser-check mobile**

Set a `390x844` viewport and verify:

- filter controls stack cleanly;
- statistic items do not overlap;
- tables scroll inside their containers;
- the document itself has no horizontal overflow.

- [ ] **Step 6: Final commit**

If verification required adjustments:

```powershell
git add app tests
git commit -m "fix: polish admin annual summary"
```

### Task 6: Push Phase One

**Files:** None.

- [ ] **Step 1: Push the branch**

```powershell
git push origin codex/mvp-implementation
```

If the HTTPS connection is reset, retry with:

```powershell
git -c http.version=HTTP/1.1 push origin codex/mvp-implementation
```

- [ ] **Step 2: Confirm remote state**

```powershell
git status --short --branch
git log -1 --oneline
```

Expected: branch is not ahead of origin; only `docs/prototype/screenshots/` remains untracked.

## Self-Review

- Spec coverage: permissions, filters, inactive-account history, metrics, teacher rows, detail rows, workbook, ZIP, missing files, empty exports, and responsive verification all map to explicit tasks.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps remain.
- Type consistency: page and both export routes use the same `SummaryFilters` and `AdminSummary` data model; workbook and ZIP builders consume the same filtered result.
