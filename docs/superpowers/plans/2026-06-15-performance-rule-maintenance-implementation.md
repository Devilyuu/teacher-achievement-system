# Performance Rule Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve administrator-maintained rules across restarts and add administrator CRUD-style maintenance without physical deletion.

**Architecture:** Change catalog seeding to insert missing defaults only. Add validated admin routes for list filtering, create, edit, and active-state toggling, backed by a shared form assignment helper and dedicated templates.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, pytest, TestClient.

---

### Task 1: Preserve Maintained Rules

- [ ] Add failing tests proving edited and custom rules survive `seed_initial_data()`.
- [ ] Change seed behavior to insert missing catalog rules without overwriting or deactivating existing rows.
- [ ] Run seed tests and commit `fix: preserve maintained performance rules`.

### Task 2: Rule Create And Edit

- [ ] Add failing admin tests for permission, create, duplicate validation, edit, assignment mode, and sort order.
- [ ] Add shared rule-form validation and assignment helpers.
- [ ] Add create and edit routes and form template.
- [ ] Run focused tests and commit `feat: add performance rule editor`.

### Task 3: Rule List And Active State

- [ ] Add failing tests for all/status/keyword list filtering and active-state toggle.
- [ ] Update list route and template with filters, status, ordering, and actions.
- [ ] Verify inactive rules leave and re-enter teacher form options after toggling.
- [ ] Run focused tests and commit `feat: manage performance rule status`.

### Task 4: Verification

- [ ] Run full tests and `git diff --check`.
- [ ] Restart server and browser-check desktop/mobile.
- [ ] Push all pending commits to `codex/mvp-implementation`.
