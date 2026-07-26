# Export Confirms Annual Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make annual package generation also confirm the teacher's yearly submission so the annual status becomes `已导出` after export.

**Architecture:** Keep the existing `/exports/{year}/personal` route and ZIP builder. Update `generate_personal_export()` to ensure an annual submission record exists before writing the export record, and update the review-page button copy.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy ORM, pytest.

---

## File Structure

- Modify `tests/test_exports.py`
  - Add a regression test for exporting without prior annual confirmation.
  - Extend the review page test to assert the new button copy.
- Modify `app/services/export_history.py`
  - Confirm the annual submission before building the export record.
- Modify `app/templates/exports/review.html`
  - Change the primary button text from `确认生成并下载` to `确认整理并下载`.

### Task 1: Add Export-Confirms-Year Regression Test

**Files:**
- Modify: `tests/test_exports.py`

- [ ] **Step 1: Write failing service test**

Add a test after `test_export_route_requires_auth_and_authenticated_user_can_download`:

```python
def test_personal_export_confirms_year_when_teacher_has_not_submitted(app, tmp_path):
    source_path = tmp_path / "auto-submit-proof.pdf"
    source_path.write_bytes(b"%PDF-1.4 auto submit proof")

    db = SessionLocal()
    try:
        user = _create_user(db, f"export-auto-submit-{uuid4().hex}")
        _add_achievement_with_material(
            db,
            user,
            2026,
            "教学",
            "教学成果",
            source_path,
            "1-1",
        )
        db.commit()

        generate_personal_export(db, user, 2026)
        state = get_annual_submission_state(db, user.id, 2026)
        submission_count = (
            db.query(AnnualSubmission)
            .filter_by(user_id=user.id, year=2026)
            .count()
        )

        assert submission_count == 1
        assert state.status == ANNUAL_STATUS_EXPORTED
        assert state.submitted_at is not None
        assert state.exported_at is not None
    finally:
        db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_personal_export_confirms_year_when_teacher_has_not_submitted -q
```

Expected result: FAIL because no annual submission record is created by export generation yet.

### Task 2: Implement Automatic Annual Confirmation During Export

**Files:**
- Modify: `app/services/export_history.py`
- Test: `tests/test_exports.py`

- [ ] **Step 1: Add minimal service implementation**

In `app/services/export_history.py`, import `confirm_annual_submission`:

```python
from app.services.annual_submission import confirm_annual_submission
```

Then call it at the start of `generate_personal_export()`:

```python
confirm_annual_submission(db, user, year)
```

Keep the rest of export generation unchanged.

- [ ] **Step 2: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_personal_export_confirms_year_when_teacher_has_not_submitted -q
```

Expected result: PASS.

### Task 3: Update Review Button Copy

**Files:**
- Modify: `tests/test_exports.py`
- Modify: `app/templates/exports/review.html`

- [ ] **Step 1: Update review-page test first**

In `test_export_review_page_summarizes_year_before_generation`, assert:

```python
assert "确认整理并下载" in response.text
assert "确认生成并下载" not in response.text
```

- [ ] **Step 2: Run review test to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_export_review_page_summarizes_year_before_generation -q
```

Expected result: FAIL because the old text is still rendered.

- [ ] **Step 3: Update template**

Change the primary action text in `app/templates/exports/review.html` to:

```jinja
确认整理并下载
```

- [ ] **Step 4: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_export_review_page_summarizes_year_before_generation -q
```

Expected result: PASS.

### Task 4: Verification and Commit

**Files:**
- Modify: `tests/test_exports.py`
- Modify: `app/services/export_history.py`
- Modify: `app/templates/exports/review.html`

- [ ] **Step 1: Run related and full tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py tests/test_annual_submission.py tests/test_dashboard.py -q
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected result: both pytest commands exit 0 and `git diff --check` exits 0.

- [ ] **Step 2: Commit**

```powershell
git add tests/test_exports.py app/services/export_history.py app/templates/exports/review.html
git commit -m "feat: confirm annual submission on export"
```

## Self-Review

- Spec coverage: The plan covers service behavior, review-page wording, and regression tests.
- Placeholder scan: No placeholder tasks remain.
- Type consistency: Uses existing `AnnualSubmission`, `ANNUAL_STATUS_EXPORTED`, and `generate_personal_export()` APIs.
