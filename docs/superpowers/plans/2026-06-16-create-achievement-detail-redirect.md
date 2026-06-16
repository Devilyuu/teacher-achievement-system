# Create Achievement Detail Redirect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redirect teachers to the newly created achievement detail page after saving a new achievement.

**Architecture:** Keep achievement creation logic unchanged. After committing the new record, use its generated `id` to return a 303 redirect to `/achievements/{achievement.id}`.

**Tech Stack:** FastAPI, SQLAlchemy, pytest.

---

### Task 1: Redirect After Create

**Files:**
- Modify: `tests/test_achievements.py`
- Modify: `app/routers/achievements.py`

- [ ] **Step 1: Write the failing test**

Update `test_authenticated_admin_can_create_achievement_and_see_it_in_list` so it expects the create response `Location` to start with `/achievements/` and not equal `/achievements`. Then request that detail URL and assert the created title appears.

- [ ] **Step 2: Run test to verify it fails**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_authenticated_admin_can_create_achievement_and_see_it_in_list -q
```

Expected: fail because the route still redirects to `/achievements`.

- [ ] **Step 3: Implement minimal route change**

In `app/routers/achievements.py`, change the final line of `create_achievement` from:

```python
return RedirectResponse("/achievements", status_code=status.HTTP_303_SEE_OTHER)
```

to:

```python
return RedirectResponse(
    f"/achievements/{achievement.id}",
    status_code=status.HTTP_303_SEE_OTHER,
)
```

- [ ] **Step 4: Run focused test**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py::test_authenticated_admin_can_create_achievement_and_see_it_in_list -q
```

Expected: pass.

- [ ] **Step 5: Run verification**

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_achievements.py tests/test_materials.py tests/test_dashboard.py -q
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected: all pass and no whitespace errors.
