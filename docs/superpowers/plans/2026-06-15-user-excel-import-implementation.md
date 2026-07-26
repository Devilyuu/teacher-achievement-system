# User Excel Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe Excel template download, row-level preview validation, and confirmed batch user creation.

**Architecture:** A focused service creates and parses workbooks, normalizes rows, and stores a short-lived hashed import batch. Admin routes expose template, preview, and confirmation endpoints; templates add upload controls and a preview table.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, openpyxl, itsdangerous, pytest

---

### Task 1: Workbook template and parser

**Files:**
- Create: `app/services/user_import.py`
- Create: `tests/test_user_import.py`

- [ ] Test template headers and example formatting.
- [ ] Test valid rows, empty-row skipping, duplicate usernames, existing usernames, invalid roles, missing fields, and short passwords.
- [ ] Implement workbook creation and parsing until focused tests pass.

### Task 2: Secure preview batch

**Files:**
- Modify: `app/services/user_import.py`
- Test: `tests/test_user_import.py`

- [ ] Test that stored batches contain password hashes but no plaintext passwords.
- [ ] Test signed batch loading and one-time deletion.
- [ ] Implement temporary batch persistence and signed identifiers.

### Task 3: Admin routes and pages

**Files:**
- Modify: `app/routers/admin.py`
- Modify: `app/templates/admin/users.html`
- Create: `app/templates/admin/user_import_preview.html`
- Modify: `app/static/app.css`
- Modify: `tests/test_admin.py`

- [ ] Test admin-only template download, preview, invalid workbook handling, blocked confirmation with errors, and successful import.
- [ ] Add download, preview, and confirm routes.
- [ ] Add upload controls, preview table, status messages, and responsive styling.

### Task 4: Verification

- [ ] Run the full pytest suite.
- [ ] Download and inspect the template workbook.
- [ ] Browser-test upload preview and confirmation controls without importing persistent demo users.
- [ ] Verify desktop and mobile layouts have no page-level horizontal overflow.
