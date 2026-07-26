# Material Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add permission-aware inline preview for PDF and image support materials.

**Architecture:** Create a small material preview service for supported media types and safe path resolution. Reuse the existing materials router for teacher routes and add an admin preview route for readonly audit views. Render preview links only for supported extensions.

**Tech Stack:** FastAPI, Starlette `FileResponse`, SQLAlchemy, Jinja2, pytest.

---

### Task 1: Teacher Preview Route

**Files:**
- Modify: `tests/test_materials.py`
- Create: `app/services/material_preview.py`
- Modify: `app/routers/materials.py`

- [ ] **Step 1: Write failing tests**

Add tests for owner preview, unsupported extension, other-user access, and missing file.

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/test_materials.py::test_owner_can_preview_pdf_material_inline tests/test_materials.py::test_owner_cannot_preview_unsupported_material tests/test_materials.py::test_user_cannot_preview_another_users_material tests/test_materials.py::test_preview_missing_material_file_returns_404 -q`

Expected: fail because `/materials/{material_id}/preview` does not exist.

- [ ] **Step 3: Implement service and route**

Create `preview_media_type()`, `is_previewable_material()`, and `safe_material_path()` in `app/services/material_preview.py`. Add `GET /materials/{material_id}/preview` that returns `FileResponse(..., content_disposition_type="inline")`.

- [ ] **Step 4: Run tests to verify GREEN**

Run the same pytest command. Expected: pass.

### Task 2: Teacher Detail Page Entry

**Files:**
- Modify: `tests/test_materials.py`
- Modify: `app/routers/achievements.py`
- Modify: `app/templates/achievements/detail.html`

- [ ] **Step 1: Write failing page test**

Add a detail-page test showing that previewable materials render a preview link and non-previewable materials do not.

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/test_materials.py::test_material_detail_shows_preview_only_for_supported_files -q`

Expected: fail because no preview link is rendered.

- [ ] **Step 3: Render preview links**

Pass `preview_extensions` from the achievement detail route and conditionally render a lucide `eye` icon link before download.

- [ ] **Step 4: Run test to verify GREEN**

Run the same pytest command. Expected: pass.

### Task 3: Admin Readonly Preview

**Files:**
- Modify: `tests/test_admin_summary.py`
- Modify: `app/routers/admin.py`
- Modify: `app/templates/admin/achievement_detail.html`

- [ ] **Step 1: Write failing admin tests**

Add tests that an admin can preview a teacher PDF material inline and sees preview links in the admin achievement detail page.

- [ ] **Step 2: Run tests to verify RED**

Run: `pytest tests/test_admin_summary.py::test_admin_can_preview_teacher_material_inline tests/test_admin_summary.py::test_admin_achievement_detail_shows_preview_for_supported_materials -q`

Expected: fail because the admin preview route and links do not exist.

- [ ] **Step 3: Implement admin route and template links**

Add `GET /admin/materials/{material_id}/preview`, require admin, reuse preview service, and render preview links for supported materials.

- [ ] **Step 4: Run test to verify GREEN**

Run the same pytest command. Expected: pass.

### Task 4: Full Verification

**Files:**
- No production changes unless tests reveal a defect.

- [ ] **Step 1: Run material and admin tests**

Run: `pytest tests/test_materials.py tests/test_admin_summary.py -q`

- [ ] **Step 2: Run full test suite**

Run: `pytest -q`

- [ ] **Step 3: Browser verify**

Open `http://127.0.0.1:8001`, visit a detail page with uploaded PDF/image material, confirm the preview icon appears and opens without console errors.

