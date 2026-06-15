# System Backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an administrator-only download that creates a consistent SQLite and upload-material backup ZIP.

**Architecture:** A backup service uses SQLite's backup API to create a database snapshot, inventories files under the upload root, writes a JSON manifest, and builds a ZIP under the export directory. Admin routes provide a minimal page and download endpoint.

**Tech Stack:** Python sqlite3, pathlib, ZipFile, FastAPI, Jinja2, pytest.

---

### Task 1: Backup Builder

**Files:**
- Create: `app/services/backup_builder.py`
- Create: `tests/test_backup.py`

- [ ] Write failing tests for database snapshot, upload entries, manifest counts, export exclusion, and empty upload roots.
- [ ] Run focused tests and confirm the service is missing.
- [ ] Implement `build_system_backup(database_path, upload_dir, export_dir)`.
- [ ] Run focused tests and commit `feat: add system backup builder`.

### Task 2: Admin Backup Page

**Files:**
- Modify: `app/routers/admin.py`
- Create: `app/templates/admin/backup.html`
- Modify: `app/templates/base.html`
- Modify: `app/static/app.css`
- Modify: `tests/test_backup.py`

- [ ] Write failing permission, page, and download tests.
- [ ] Add `GET /admin/backup` and `GET /admin/backup/download`.
- [ ] Add the system-management navigation entry and focused page UI.
- [ ] Run focused tests and commit `feat: add admin system backup`.

### Task 3: Verification

- [ ] Run the full test suite and `git diff --check`.
- [ ] Restart the local server and browser-check desktop/mobile.
- [ ] Push `codex/mvp-implementation`.
