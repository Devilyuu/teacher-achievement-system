# Material Upload Status Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the teacher achievement detail page clearly state when an uploaded material makes the achievement meet basic application conditions.

**Architecture:** Reuse the existing upload redirect and the existing `Achievement.status` recalculation. Add one template branch in the upload success message and one regression assertion in the material upload test.

**Tech Stack:** FastAPI, Jinja2 templates, SQLAlchemy models, pytest with FastAPI `TestClient`.

---

## File Structure

- Modify `tests/test_materials.py`
  - Extend the existing owned-achievement upload test to follow the redirect and assert the teacher-facing readiness message.
- Modify `app/templates/achievements/detail.html`
  - Branch the upload success message when `achievement.status == "可申报"`.

### Task 1: Add Regression Test

**Files:**
- Modify: `tests/test_materials.py`

- [ ] **Step 1: Write the failing test**

In `test_authenticated_user_can_upload_material_to_owned_achievement`, after the database assertions and cleanup, add:

```python
    detail_response = client.get(response.headers["location"])

    assert detail_response.status_code == 200
    assert "当前成果已满足基础申报条件" in detail_response.text
    assert "最终认定仍以线下审核为准" in detail_response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_materials.py::test_authenticated_user_can_upload_material_to_owned_achievement -q
```

Expected result: FAIL because the detail page still only says the material was uploaded and does not include the new readiness wording.

### Task 2: Update Detail Template

**Files:**
- Modify: `app/templates/achievements/detail.html`
- Test: `tests/test_materials.py`

- [ ] **Step 1: Write minimal implementation**

Replace the existing upload success `<span>` inside the `request.query_params.get("uploaded")` block with:

```jinja
                {% if achievement.status == "可申报" %}
                <span>已上传 {{ request.query_params.get("uploaded") }} 份材料，当前成果已满足基础申报条件。最终认定仍以线下审核为准。</span>
                {% else %}
                <span>已上传 {{ request.query_params.get("uploaded") }} 份材料。</span>
                {% endif %}
```

- [ ] **Step 2: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_materials.py::test_authenticated_user_can_upload_material_to_owned_achievement -q
```

Expected result: PASS.

- [ ] **Step 3: Run related tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_materials.py tests/test_achievements.py tests/test_dashboard.py -q
```

Expected result: PASS.

- [ ] **Step 4: Run full test suite and whitespace check**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git diff --check
```

Expected result: pytest exits 0 and `git diff --check` exits 0.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_materials.py app/templates/achievements/detail.html
git commit -m "feat: clarify material upload status feedback"
```

## Self-Review

- Spec coverage: The plan covers the ready-state upload message, preserves the existing non-ready upload message, and does not touch admin or workflow state.
- Placeholder scan: No placeholder tasks remain.
- Type consistency: The template uses the existing string status value already used elsewhere in templates.
