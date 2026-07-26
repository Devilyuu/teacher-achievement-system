# User Reporting Years Implementation Plan

> **For agentic workers:** This plan is executed inline by the primary agent. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default the system to the current year and let each teacher safely manage visible and default reporting years.

**Architecture:** Store explicit per-user years in a normalized preference table. Derive visible options from current year, preferences and existing achievement years; keep deletion non-destructive by rejecting years that contain achievements.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite, Jinja2, pytest.

---

### Task 1: Reporting Year Model and Service

- [x] Add `UserReportingYear` with unique `(user_id, year)` and `is_default`.
- [x] Add an idempotent SQLite migration.
- [x] Implement add, set-default, delete-empty and option/default query services.
- [x] Test current-year fallback, ownership, uniqueness, default switching and safe deletion.

### Task 2: Dashboard and Achievement Integration

- [x] Add authenticated POST routes for add/default/delete.
- [x] Use the personal default year on dashboard, achievement list and new form.
- [x] Use current year rather than previous year as the global fallback.
- [x] Add dashboard year-management controls and validation feedback.
- [x] Test end-to-end behavior and responsive layout contracts.

### Task 3: Personal Integration Account

- [x] Update production configuration to `FEISHU_SYNC_USERNAME=1867`.
- [x] Verify account `1867` sees the personal feature gate and other users do not.

### Task 4: Verification and Deployment

- [x] Run the full automated test suite.
- [x] Back up production data.
- [x] Deploy and restart the service.
- [x] Verify the 2026 default and year management using the production UI.
