# Annual Submission Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add teacher annual confirmation status and admin annual-status visibility without introducing an online approval workflow.

**Architecture:** Store teacher confirmations in a dedicated `annual_submissions` table keyed by `user_id + year`. Compute display status in `app/services/annual_submission.py` from achievements, materials, submission records, and export records. Wire the computed status into the teacher dashboard and admin summary.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Jinja2, pytest.

---

### Task 1: Annual Submission Model And Status Service

**Files:**
- Modify: `app/models.py`
- Modify: `app/schema_updates.py`
- Create: `app/services/annual_submission.py`
- Test: `tests/test_annual_submission.py`

- [ ] **Step 1: Write failing tests**

Create tests for:

```python
def test_annual_status_is_not_started_without_records_or_submission(app):
    state = get_annual_submission_state(db, user.id, 2026)
    assert state.status == "未开始"

def test_annual_status_is_in_progress_with_records_but_no_submission(app):
    db.add(Achievement(
        user_id=user.id,
        year=2026,
        category="教学",
        subcategory="教学成果",
        claim_nature=ClaimNature.result.value,
        title="A",
        claimed_score=1,
    ))
    db.commit()
    state = get_annual_submission_state(db, user.id, 2026)
    assert state.status == "整理中"

def test_annual_status_is_submitted_after_teacher_confirms(app):
    record = confirm_annual_submission(db, user, 2026)
    state = get_annual_submission_state(db, user.id, 2026)
    assert state.status == "已提交"
    assert state.submitted_at == record.submitted_at

def test_annual_status_returns_to_in_progress_when_record_changes_after_submission(app):
    confirm_annual_submission(db, user, 2026)
    achievement.updated_at = datetime.utcnow()
    db.commit()
    state = get_annual_submission_state(db, user.id, 2026)
    assert state.status == "整理中"

def test_annual_status_is_exported_when_latest_export_follows_submission(app):
    confirm_annual_submission(db, user, 2026)
    db.add(ExportRecord(user_id=user.id, year=2026, generated_at=datetime.utcnow()))
    db.commit()
    state = get_annual_submission_state(db, user.id, 2026)
    assert state.status == "已导出"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_annual_submission.py -q
```

Expected: fail because `AnnualSubmission` and `get_annual_submission_state()` do not exist.

- [ ] **Step 3: Implement model, schema update, and service**

Add `AnnualSubmission` model with `user_id`, `year`, `status`, `submitted_at`, `updated_at`, and a unique constraint on `user_id + year`. Add `apply_schema_updates()` creation SQL for existing SQLite databases. Implement `get_annual_submission_state(db, user_id, year)` and `confirm_annual_submission(db, user, year)`.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add app/models.py app/schema_updates.py app/services/annual_submission.py tests/test_annual_submission.py
git commit -m "feat: add annual submission status service"
```

### Task 2: Teacher Dashboard Confirmation

**Files:**
- Modify: `app/routers/dashboard.py`
- Modify: `app/templates/dashboard.html`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests**

Add tests that:

```python
def test_dashboard_shows_annual_submission_status_and_confirm_button(app):
    response = client.get("/")
    assert "年度整理状态" in response.text
    assert "确认本年度材料已整理完成" in response.text

def test_teacher_can_confirm_current_year_submission_from_dashboard(app):
    response = client.post(f"/annual-submissions/{year}/confirm", follow_redirects=False)
    assert response.status_code == 303
    assert db.query(AnnualSubmission).filter_by(user_id=user_id, year=year).one()

def test_confirming_same_year_updates_existing_submission(app):
    first = confirm_annual_submission(db, user, year)
    response = client.post(f"/annual-submissions/{year}/confirm", follow_redirects=False)
    refreshed = db.query(AnnualSubmission).filter_by(user_id=user.id, year=year).one()
    assert refreshed.id == first.id
    assert refreshed.submitted_at >= first.submitted_at
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_dashboard.py -q
```

Expected: fail because dashboard context, confirmation route, and template panel do not exist.

- [ ] **Step 3: Implement dashboard route and template**

Add `POST /annual-submissions/{year}/confirm` to the dashboard router. Render current annual status, submitted time, a warning about `needs_info`, and a confirmation button.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add app/routers/dashboard.py app/templates/dashboard.html tests/test_dashboard.py
git commit -m "feat: add teacher annual confirmation"
```

### Task 3: Admin Summary Annual Status

**Files:**
- Modify: `app/services/admin_summary.py`
- Modify: `app/routers/admin.py`
- Modify: `app/templates/admin/summary.html`
- Test: `tests/test_admin_summary.py`

- [ ] **Step 1: Write failing tests**

Add tests that:

```python
def test_admin_summary_includes_annual_status_for_each_teacher(app):
    response = client.get("/admin/summary", params={"year": 2026})
    assert "年度状态" in response.text
    assert "整理中" in response.text

def test_admin_summary_filters_not_started_teachers_by_annual_status(app):
    result = build_admin_summary(db, SummaryFilters(year=2026, annual_status="未开始"))
    assert [row.user.id for row in result.teachers] == [not_started_teacher.id]
    assert result.achievements == []

def test_admin_summary_filters_submitted_teachers_and_their_achievements(app):
    result = build_admin_summary(db, SummaryFilters(year=2026, annual_status="已提交"))
    assert [row.user.id for row in result.teachers] == [submitted_teacher.id]
    assert [item.user_id for item in result.achievements] == [submitted_teacher.id]
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_admin_summary.py -q
```

Expected: fail because `SummaryFilters` has no annual-status filter and teacher rows have no annual state.

- [ ] **Step 3: Implement admin summary annual state**

Add `annual_status` to `SummaryFilters`, `submitted_teacher_count` to `SummaryMetrics`, and `annual_state` to `TeacherSummaryRow`. Build teacher rows from teacher accounts, then attach matching achievements. Apply annual status filtering at teacher level and keep achievement details restricted to visible teachers.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same pytest command. Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add app/services/admin_summary.py app/routers/admin.py app/templates/admin/summary.html tests/test_admin_summary.py
git commit -m "feat: show annual submission status in admin summary"
```

### Task 4: Export Interaction And Full Verification

**Files:**
- Modify: `app/services/export_history.py`
- Test: `tests/test_exports.py`

- [ ] **Step 1: Write failing export interaction test**

Add a test that confirms a submitted year becomes `已导出` after generating the personal export and does not immediately fall back to `整理中`.

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_personal_export_marks_submitted_year_as_exported -q
```

Expected: fail until export timestamp ordering works with annual status calculation.

- [ ] **Step 3: Implement export timestamp handling**

Ensure `ExportRecord.generated_at` is set after achievement export status updates, so the annual status service can distinguish export-generated changes from later teacher edits.

- [ ] **Step 4: Run focused and full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_annual_submission.py tests/test_dashboard.py tests/test_admin_summary.py tests/test_exports.py -q
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

- [ ] **Step 5: Browser verify**

Open `http://127.0.0.1:8001`, confirm dashboard shows annual status and admin summary shows annual status filter.

- [ ] **Step 6: Commit**

```powershell
git add app/services/export_history.py tests/test_exports.py
git commit -m "fix: keep annual status exported after personal export"
```
