# Annual Export Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a teacher-facing review page before generating and downloading a yearly export package.

**Architecture:** Keep the existing `/exports/{year}/personal` download route unchanged. Add `/exports/{year}/review` in the existing export router, render a new Jinja template, and update teacher-side entry links to route through the review page.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy ORM, pytest with FastAPI `TestClient`.

---

## File Structure

- Modify `tests/test_exports.py`
  - Add tests for the new review route and export-history links.
- Modify `tests/test_achievements.py`
  - Update list-page export link expectations to point to the review page.
- Modify `app/routers/exports.py`
  - Add summary building and `GET /exports/{year}/review`.
- Create `app/templates/exports/review.html`
  - Render the yearly summary, incomplete list, and action buttons.
- Modify `app/templates/achievements/list.html`
  - Change the header export link to `/exports/{selected_year}/review`.
- Modify `app/templates/exports/list.html`
  - Change generate/regenerate links to `/exports/{year}/review`.

### Task 1: Review Route Tests

**Files:**
- Modify: `tests/test_exports.py`

- [ ] **Step 1: Write failing review-page tests**

Add a test that creates one ready achievement with one material, one incomplete owner achievement, and one incomplete achievement owned by another user. Then request `/exports/2026/review` as the owner and assert:

```python
assert response.status_code == 200
assert "2026 年度导出确认" in response.text
assert "2 项成果" in response.text
assert "1 项可导出" in response.text
assert "1 项待完善" in response.text
assert "1 份材料" in response.text
assert "最终分值和级别认定仍以线下审核为准" in response.text
assert "每个年度仅保留最新生成版本" in response.text
assert "Owner incomplete export item" in response.text
assert "Other incomplete export item" not in response.text
assert 'href="/achievements?year=2026"' in response.text
assert 'href="/exports/2026/personal"' in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_export_review_page_summarizes_year_before_generation -q
```

Expected result: FAIL with 404 because `/exports/2026/review` does not exist yet.

### Task 2: Implement Review Route and Template

**Files:**
- Modify: `app/routers/exports.py`
- Create: `app/templates/exports/review.html`
- Test: `tests/test_exports.py`

- [ ] **Step 1: Add route implementation**

In `app/routers/exports.py`, import `Achievement` and `AchievementStatus`, query the current user's selected-year achievements, calculate:

```python
ready_statuses = {
    AchievementStatus.ready.value,
    AchievementStatus.exported.value,
}
ready_count = sum(item.status in ready_statuses for item in achievements)
needs_attention = [item for item in achievements if item.status not in ready_statuses]
material_count = sum(len(item.materials) for item in achievements)
```

Render `exports/review.html` with `year`, `achievements`, `ready_count`, `needs_attention`, and `material_count`.

- [ ] **Step 2: Add template**

Create `app/templates/exports/review.html` with a page header, four summary metrics, the offline-review/latest-version reminders, an incomplete achievement list, and buttons:

```jinja
<a class="button secondary" href="/achievements?year={{ year }}">返回继续整理</a>
<a class="button primary" href="/exports/{{ year }}/personal">确认生成并下载</a>
```

- [ ] **Step 3: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py::test_export_review_page_summarizes_year_before_generation -q
```

Expected result: PASS.

### Task 3: Update Export Entry Links

**Files:**
- Modify: `tests/test_achievements.py`
- Modify: `tests/test_exports.py`
- Modify: `app/templates/achievements/list.html`
- Modify: `app/templates/exports/list.html`

- [ ] **Step 1: Update list-page tests first**

Change existing assertions in `tests/test_achievements.py` from:

```python
assert 'href="/exports/2026/personal"' in response.text
```

to:

```python
assert 'href="/exports/2026/review"' in response.text
```

Add or update export-history assertions in `tests/test_exports.py` so generation links point to `/exports/{year}/review` while recorded download links remain `/exports/records/{record_id}/download`.

- [ ] **Step 2: Run affected tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_achievement_list_can_filter_and_export_by_year tests/test_achievements.py::test_achievement_list_export_link_ignores_filters tests/test_exports.py::test_export_history_page_lists_only_owner_records_newest_first tests/test_exports.py::test_export_history_page_marks_missing_files_for_regeneration -q
```

Expected result: FAIL because templates still link directly to `/personal`.

- [ ] **Step 3: Update templates**

In `app/templates/achievements/list.html`, change:

```jinja
href="/exports/{{ selected_year }}/personal"
```

to:

```jinja
href="/exports/{{ selected_year }}/review"
```

In `app/templates/exports/list.html`, change generate/regenerate links from `/personal` to `/review`. Do not change recorded download links.

- [ ] **Step 4: Run related tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_exports.py tests/test_achievements.py -q
```

Expected result: PASS.

### Task 4: Final Verification and Commit

**Files:**
- All modified files from Tasks 1-3.

- [ ] **Step 1: Run full verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected result: pytest exits 0 and `git diff --check` exits 0.

- [ ] **Step 2: Commit**

```powershell
git add tests/test_exports.py tests/test_achievements.py app/routers/exports.py app/templates/exports/review.html app/templates/exports/list.html app/templates/achievements/list.html
git commit -m "feat: add annual export review page"
```

## Self-Review

- Spec coverage: The plan adds the review page, summary counts, incomplete list, latest-version reminder, offline-review reminder, and entry-link changes.
- Placeholder scan: No placeholder tasks remain.
- Type consistency: Status strings use existing `AchievementStatus` values.
