# Achievement Readiness Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show system-generated self-check reasons on achievement detail and edit pages.

**Architecture:** Reuse `app.services.achievement_readiness.missing_reasons` in the achievements router and pass `readiness_reasons` to templates. Render a full card on the detail page and a compact inline hint on the edit page, with CSS scoped to readiness hint components.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, pytest, plain CSS, lucide icons.

---

### Task 1: Route Context

**Files:**
- Modify: `app/routers/achievements.py`
- Test: `tests/test_achievements.py`

- [ ] **Step 1: Write the failing detail page test**

Add a test creating a `待完善` achievement with no materials, then request `/achievements/{id}`. Assert that the response contains `待完善原因`, `未上传支撑材料`, and `href="/achievements/{id}/edit"`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_achievement_detail_shows_readiness_reasons_for_pending_record -q
```

Expected: fail because the detail template does not render the readiness panel yet.

- [ ] **Step 3: Add route context**

In `app/routers/achievements.py`, import:

```python
from app.services.achievement_readiness import missing_reasons
```

In `achievement_detail`, add `"readiness_reasons": missing_reasons(achievement)` to the template context.

In `_form_context`, add:

```python
"readiness_reasons": missing_reasons(achievement) if achievement else [],
```

- [ ] **Step 4: Run detail test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_achievement_detail_shows_readiness_reasons_for_pending_record -q
```

Expected: still fail until the template renders the context.

### Task 2: Detail Page Readiness Panel

**Files:**
- Modify: `app/templates/achievements/detail.html`
- Modify: `app/static/app.css`
- Test: `tests/test_achievements.py`

- [ ] **Step 1: Implement detail template and CSS**

Add a `.readiness-panel` section before the existing `.detail-panel`, rendered only when `achievement.status == "待完善"` and `readiness_reasons` is not empty.

The card must include:

- `待完善原因`
- explanatory text that this is a system self-check, not offline review
- one list item per reason
- an `编辑成果` button linking to `/achievements/{{ achievement.id }}/edit`
- a material-area hint if any reason contains `材料`

Add CSS for `.readiness-panel`, `.readiness-list`, `.readiness-actions`, and `.readiness-material-note`.

- [ ] **Step 2: Run detail test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_achievement_detail_shows_readiness_reasons_for_pending_record -q
```

Expected: pass.

- [ ] **Step 3: Add hidden-state test**

Add a test creating a `可申报` achievement with a material file, then request its detail page and assert `待完善原因` is not present.

- [ ] **Step 4: Run focused tests**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_achievement_detail_shows_readiness_reasons_for_pending_record tests/test_achievements.py::test_achievement_detail_hides_readiness_reasons_for_ready_record -q
```

Expected: pass.

### Task 3: Edit Page Inline Hint

**Files:**
- Modify: `app/templates/achievements/form.html`
- Modify: `app/static/app.css`
- Test: `tests/test_achievements.py`

- [ ] **Step 1: Write failing edit page test**

Add a test creating a `待完善` achievement with no materials, then request `/achievements/{id}/edit`. Assert that the response contains `当前待完善原因`, `未上传支撑材料`, and `保存后系统会重新判断状态`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_edit_achievement_shows_readiness_reasons_hint -q
```

Expected: fail because the edit form does not render the hint yet.

- [ ] **Step 3: Implement edit template and CSS**

Add a `.readiness-inline` block before the form panel, rendered only when editing an existing achievement and `readiness_reasons` is not empty.

The block must include:

- `当前待完善原因`
- joined reason text
- `保存后系统会重新判断状态`

- [ ] **Step 4: Run edit page test**

Run:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_edit_achievement_shows_readiness_reasons_hint -q
```

Expected: pass.

### Task 4: Verification

**Files:**
- Verify changed behavior and regression surface.

- [ ] **Step 1: Run achievement tests**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py tests/test_dashboard.py tests/test_layout_css.py -q
```

Expected: pass.

- [ ] **Step 2: Run full test suite**

```bash
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: pass.

- [ ] **Step 3: Run diff check**

```bash
git diff --check
```

Expected: no whitespace errors.

- [ ] **Step 4: Browser verification**

Open a pending achievement detail page from `http://127.0.0.1:8001/` and verify the readiness panel appears above the detail information card. Open its edit page and verify the compact hint appears above the form.
