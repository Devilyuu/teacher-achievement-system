# Material Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let teachers rename a support material's display metadata without changing the uploaded file.

**Architecture:** Add a POST route in `app/routers/materials.py` that reuses existing owner-scoped material lookup, validates a non-empty display name, updates `display_name` and `description`, and redirects to the achievement detail page with a result query parameter. Add a compact rename popover to `app/templates/achievements/detail.html`.

**Tech Stack:** FastAPI forms, SQLAlchemy, Jinja2, pytest.

---

### Task 1: Rename Route

**Files:**
- Modify: `tests/test_materials.py`
- Modify: `app/routers/materials.py`

- [ ] Write a failing test that posts `/materials/{material_id}/rename` and asserts `display_name` and `description` change while `original_filename`, `stored_path`, `material_no`, and file content stay unchanged.
- [ ] Run the focused test and confirm it fails with 404.
- [ ] Add the rename route with owner check and non-empty display-name validation.
- [ ] Run the focused test and confirm it passes.

### Task 2: Validation And Permissions

**Files:**
- Modify: `tests/test_materials.py`
- Modify: `app/routers/materials.py`

- [ ] Write failing tests for blank display names and cross-user rename attempts.
- [ ] Implement redirect error handling for blank names.
- [ ] Run focused tests and confirm they pass.

### Task 3: Detail Page UI

**Files:**
- Modify: `tests/test_materials.py`
- Modify: `app/templates/achievements/detail.html`
- Modify: `app/static/app.css`

- [ ] Write a failing page test for the rename action, form fields, and success/error messages.
- [ ] Add the rename popover beside existing material actions.
- [ ] Reuse existing popover styling with small CSS additions.
- [ ] Run focused material tests and confirm they pass.

### Task 4: Verification

**Files:**
- Modify only if verification exposes a defect.

- [ ] Run `pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Browser-check the material detail page on desktop and mobile widths.

