# Dashboard Pending Issues Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight dashboard pending-issues panel that helps teachers find current-year achievements that still need attention.

**Architecture:** Extract the existing missing-reasons logic into a shared readiness service, then let both admin exports and the dashboard consume it. The dashboard route will prepare compact pending item data, and the template/CSS will render it between the annual status and existing overview panels.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2 templates, pytest, plain CSS, lucide icons.

---

### Task 1: Shared Readiness Service

**Files:**
- Create: `app/services/achievement_readiness.py`
- Modify: `app/services/admin_summary.py`
- Test: `tests/test_admin_summary.py`

- [ ] **Step 1: Write the failing test**

Add this import and assertion to the existing `test_summary_keeps_inactive_teacher_history_and_reports_missing_reasons` test:

```python
from app.services.achievement_readiness import missing_reasons as readiness_missing_reasons

assert missing_reasons is readiness_missing_reasons
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_admin_summary.py::test_summary_keeps_inactive_teacher_history_and_reports_missing_reasons -q
```

Expected: fail with `ModuleNotFoundError: No module named 'app.services.achievement_readiness'`.

- [ ] **Step 3: Write minimal implementation**

Create `app/services/achievement_readiness.py` with `missing_reasons(achievement)`, moving the current logic from `admin_summary.py` unchanged.

In `app/services/admin_summary.py`, import the shared function:

```python
from app.services.achievement_readiness import missing_reasons
```

Remove the local `missing_reasons` implementation and any imports that were used only by it.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_admin_summary.py::test_summary_keeps_inactive_teacher_history_and_reports_missing_reasons -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add app/services/achievement_readiness.py app/services/admin_summary.py tests/test_admin_summary.py
git commit -m "refactor: share achievement readiness reasons"
```

### Task 2: Dashboard Pending Context

**Files:**
- Modify: `app/routers/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add a test that logs in, creates one current-year `待完善` achievement, one current-year `可申报` achievement, one previous-year `待完善` achievement, then requests `/`. Assert that the current-year pending title and missing reason appear, while the ready and previous-year titles do not appear in the pending panel.

Use existing enum values from `AchievementStatus` and `ClaimNature`, and assert the response contains `href="/achievements/{pending_id}"`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_dashboard.py::test_dashboard_shows_current_year_pending_items_with_reasons -q
```

Expected: fail because the dashboard template does not render pending items yet.

- [ ] **Step 3: Write minimal route implementation**

Import the shared readiness function in `app/routers/dashboard.py`:

```python
from app.services.achievement_readiness import missing_reasons
```

Build:

```python
pending_achievements = [
    achievement
    for achievement in achievements
    if achievement.status == AchievementStatus.needs_info.value
]
pending_items = [
    {"achievement": achievement, "reasons": missing_reasons(achievement)}
    for achievement in pending_achievements[:6]
]
```

Pass `pending_items` and `pending_total` into the template context.

- [ ] **Step 4: Run test to verify it still fails for template**

Run:

```bash
pytest tests/test_dashboard.py::test_dashboard_shows_current_year_pending_items_with_reasons -q
```

Expected: fail until the template renders the new data.

### Task 3: Dashboard Panel UI

**Files:**
- Modify: `app/templates/dashboard.html`
- Modify: `app/static/app.css`
- Test: `tests/test_dashboard.py`, `tests/test_layout_css.py`

- [ ] **Step 1: Implement template and styles**

Add a `pending-panel` section after `annual-submission-panel` and before `stat-grid`.

The panel must show:

- Title: `待处理事项`
- Total count from `pending_total`
- Empty state text: `本年度暂无待处理事项`
- Item link to `/achievements/{{ item.achievement.id }}`
- Item title, category/subcategory, and joined reasons.
- Link to `/achievements?year={{ selected_year }}&status={{ stats.needs_info_status }}`

Add CSS classes for `.pending-panel`, `.pending-list`, `.pending-item`, `.pending-reasons`, and responsive behavior using existing panel, icon, and list patterns.

- [ ] **Step 2: Run dashboard test**

Run:

```bash
pytest tests/test_dashboard.py::test_dashboard_shows_current_year_pending_items_with_reasons -q
```

Expected: pass.

- [ ] **Step 3: Add/adjust empty-state test**

Add a test asserting an otherwise empty current-year dashboard includes `本年度暂无待处理事项`.

- [ ] **Step 4: Run dashboard tests**

Run:

```bash
pytest tests/test_dashboard.py -q
```

Expected: pass.

- [ ] **Step 5: Add CSS regression assertions**

In `tests/test_layout_css.py`, assert `.pending-panel` and `.pending-item` exist, and that the pending item uses a stable grid or flex layout.

- [ ] **Step 6: Run CSS test**

Run:

```bash
pytest tests/test_layout_css.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```bash
git add app/routers/dashboard.py app/templates/dashboard.html app/static/app.css tests/test_dashboard.py tests/test_layout_css.py
git commit -m "feat: show dashboard pending issues"
```

### Task 4: Verification

**Files:**
- Verify changed behavior and regression surface.

- [ ] **Step 1: Run targeted tests**

```bash
pytest tests/test_dashboard.py tests/test_admin_summary.py tests/test_layout_css.py -q
```

Expected: pass.

- [ ] **Step 2: Run full test suite**

```bash
pytest -q
```

Expected: pass.

- [ ] **Step 3: Run diff check**

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Browser verification**

Open `http://127.0.0.1:8001/` in the in-app browser and verify the dashboard still renders, the pending panel is aligned with the current style, and the page remains usable at desktop width.
