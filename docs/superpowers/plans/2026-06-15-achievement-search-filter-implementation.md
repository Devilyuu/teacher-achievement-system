# Achievement Search And Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add intersecting year, status, category, subcategory, and comprehensive keyword filters to the teacher achievement list.

**Architecture:** Introduce a focused query service that normalizes filter values and applies owner-scoped SQLAlchemy conditions. Keep category grouping in the existing router and add a compact GET filter form with client-side category/subcategory option linking.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, JavaScript, pytest, TestClient.

---

### Task 1: Owner-Scoped Filter Query

**Files:**
- Create: `app/services/achievement_search.py`
- Create: `tests/test_achievement_search.py`

- [ ] Write failing tests proving keyword matching across title, subcategory, current stage, and notes.
- [ ] Write failing tests proving year, status, category, subcategory, and keyword conditions intersect.
- [ ] Write a failing test proving another user's matching record is excluded.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests\test_achievement_search.py -q` and confirm failure because the service is missing.
- [ ] Implement `AchievementFilters` and `search_achievements(db, user_id, filters)`.
- [ ] Run the focused tests and confirm they pass.
- [ ] Commit with `feat: add achievement search service`.

### Task 2: Filter Page And Category Linking

**Files:**
- Modify: `app/routers/achievements.py`
- Modify: `app/templates/achievements/list.html`
- Modify: `app/static/app.css`
- Modify: `tests/test_achievements.py`

- [ ] Write failing page tests for retained filter values, intersecting results, empty filtered state, and export URL independence.
- [ ] Run the focused tests and confirm the page behavior fails.
- [ ] Add `status`, `category`, `subcategory`, and `q` query parameters to the list route.
- [ ] Load active rule options and use the query service for list results.
- [ ] Replace the year-only toolbar with a compact GET filter form.
- [ ] Embed category/subcategory option data and link the controls in JavaScript.
- [ ] Add a filtered empty state and a reset link that retains the year.
- [ ] Add responsive filter styles.
- [ ] Run achievement and search tests.
- [ ] Commit with `feat: add achievement list filters`.

### Task 3: Verification

**Files:** Modify only if verification reveals a defect.

- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`.
- [ ] Run `git diff --check`.
- [ ] Restart the service on port `8001`.
- [ ] Browser-check desktop filtering, selected values, linked subcategories, and export URL.
- [ ] Browser-check `390x844` layout and page-level overflow.
- [ ] Commit any verification fix.
- [ ] Push `codex/mvp-implementation`.
