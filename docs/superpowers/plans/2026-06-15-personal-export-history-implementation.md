# Personal Export History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add owner-scoped annual export records while retaining only the latest package for each user and year.

**Architecture:** Add an `ExportRecord` model with a unique user-year constraint. A focused export-history service wraps the existing ZIP builder, upserts metadata, and marks included achievements as exported. FastAPI routes render a personal record list, regenerate packages through the existing endpoint, and download an existing recorded file after ownership checks.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite, Jinja2, pathlib, pytest.

---

### Task 1: Export Record Persistence

**Files:**
- Modify: `app/models.py`
- Create: `app/services/export_history.py`
- Modify: `tests/test_exports.py`

- [ ] Write a failing test that calls `generate_personal_export`, expects one `ExportRecord`, verifies counts and file metadata, and verifies included achievements have status `已纳入导出`.
- [ ] Run `pytest tests/test_exports.py::test_generate_personal_export_records_latest_package -v` and confirm failure because the model or service does not exist.
- [ ] Add `ExportRecord` with `UniqueConstraint("user_id", "year")` and implement `generate_personal_export(db, user, year)`.
- [ ] Run the focused test and confirm it passes.
- [ ] Write a failing test that adds another achievement, regenerates the same year, and expects the record count to remain one while counts update.
- [ ] Implement the upsert behavior and rerun focused tests.

### Task 2: Personal Record Page And Downloads

**Files:**
- Modify: `app/routers/exports.py`
- Create: `app/templates/exports/list.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/app.css`
- Modify: `tests/test_exports.py`

- [ ] Write failing route tests for authentication, owner-only listing, descending year order, file-missing state, owner download, and cross-user denial.
- [ ] Run the new route tests and confirm the page and download route are missing.
- [ ] Add `GET /exports`, change `GET /exports/{year}/personal` to generate and record, and add `GET /exports/records/{record_id}/download`.
- [ ] Build the record list UI and add the “导出记录” navigation item with active state.
- [ ] Run focused export tests and confirm they pass.

### Task 3: Verification

**Files:**
- Modify only if verification exposes a defect.

- [ ] Run `pytest -q` and confirm the complete suite passes.
- [ ] Run `git diff --check`.
- [ ] Restart or reuse the local server and inspect `/exports` in the in-app browser at desktop and mobile widths.
- [ ] Confirm no browser console errors, no overlapping content, correct active navigation, and clear empty/missing-file states.

