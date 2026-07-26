# Material Batch Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let teachers upload multiple support-material files at once, with per-file validation, partial success, and safe upload-size enforcement.

**Architecture:** Move file validation and bounded streaming into `app/services/storage.py`. Keep material ownership checks in `app/routers/materials.py`, but change the upload route to accept a list of files and create one `Material` row per successfully saved file. The achievement detail page stays the single material-management surface and reports upload results from query parameters.

**Tech Stack:** FastAPI `UploadFile`, SQLAlchemy, local filesystem storage, Jinja2, pytest.

---

### Task 1: Bounded Storage Validation

**Files:**
- Modify: `app/services/storage.py`
- Modify: `tests/test_materials.py`

- [ ] Add focused tests for empty files and files above `MAX_UPLOAD_MB`.
- [ ] Run the focused tests and verify failure because storage does not enforce these constraints.
- [ ] Update `save_material_file` to stream in chunks, reject empty files, stop when the size limit is exceeded, and delete partial files.
- [ ] Run the focused storage tests and commit.

### Task 2: Batch Upload Route

**Files:**
- Modify: `app/routers/materials.py`
- Modify: `tests/test_materials.py`

- [ ] Add a failing route test that posts two legal files and expects two `Material` rows named from filenames without extensions.
- [ ] Add a failing route test that posts one legal file and one illegal file and expects partial success with a visible failure message.
- [ ] Add a failing route test that existing material numbers such as `12-1` and `12-3` produce the next number `12-4`.
- [ ] Update `upload_material` to accept `list[UploadFile]`, save each file independently, use filename stems as default names, and redirect with summary query parameters.
- [ ] Run focused material tests and commit.

### Task 3: Detail Page UI

**Files:**
- Modify: `app/templates/achievements/detail.html`
- Modify: `app/static/app.css`
- Modify: `tests/test_materials.py`

- [ ] Add a failing page test for `multiple` file input, format/size guidance, and upload result messages.
- [ ] Update the upload form and message UI.
- [ ] Run focused material tests and commit.

### Task 4: Full Verification

**Files:**
- Modify only if verification exposes a defect.

- [ ] Run `pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Browser-check the achievement detail page on desktop and mobile widths.
- [ ] Confirm no console errors, no text overlap, and upload controls remain usable.

