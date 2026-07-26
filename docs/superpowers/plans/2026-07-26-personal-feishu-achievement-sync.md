# Personal Feishu Achievement Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the configured teacher describe an achievement in natural language, review the prefilled form, save it locally, and synchronize its metadata to the existing Feishu Base table.

**Architecture:** Keep local achievement storage authoritative. A dedicated parser produces a validated draft for the existing form, while an isolated Feishu client and one-to-one sync-state model handle idempotent create/update operations after local commits. All external credentials stay in server environment variables, and the feature is enforced server-side for one configured username.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy/SQLite, httpx, Pydantic, vanilla JavaScript, Feishu Open API.

---

### Task 1: Configuration and Personal Access Gate

**Files:**
- Modify: `app/config.py`
- Create: `app/services/personal_integration.py`
- Test: `tests/test_personal_integration.py`

- [ ] **Step 1: Write failing tests for the configured user and feature readiness**

Cover:

```python
def test_only_configured_username_can_use_personal_sync(monkeypatch):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", "1867")
    assert can_use_personal_sync("1867") is True
    assert can_use_personal_sync("other") is False


def test_feishu_is_ready_only_when_all_server_credentials_exist(monkeypatch):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "cli_test_secret")
    monkeypatch.setenv("FEISHU_BASE_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_TABLE_ID", "table_id")
    assert integration_status("1867").feishu_ready is True

    monkeypatch.delenv("FEISHU_APP_SECRET")
    assert integration_status("1867").feishu_ready is False
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests\test_personal_integration.py -q`

Expected: failure because `app.services.personal_integration` does not exist.

- [ ] **Step 3: Add environment-backed settings and the access helper**

Use these environment variables:

```text
FEISHU_SYNC_USERNAME=1867
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BASE_TOKEN=H53dbNZsQalrU6sC8NPcp60QnQf
FEISHU_TABLE_ID=tblh7YcuXoVeWqH4
ACHIEVEMENT_AI_API_KEY=
ACHIEVEMENT_AI_BASE_URL=https://api.deepseek.com
ACHIEVEMENT_AI_MODEL=deepseek-chat
```

The helper must distinguish `user_enabled` from `feishu_ready` and `ai_ready`, so the UI can explain which part is unavailable without exposing secrets.

- [ ] **Step 4: Run the focused tests**

Expected: all tests in `test_personal_integration.py` pass.

- [ ] **Step 5: Commit**

```powershell
git add app/config.py app/services/personal_integration.py tests/test_personal_integration.py
git commit -m "feat: configure personal Feishu integration"
```

### Task 2: Persistent Feishu Sync State

**Files:**
- Modify: `app/models.py`
- Modify: `app/schema_updates.py`
- Test: `tests/test_feishu_sync_model.py`

- [ ] **Step 1: Write failing model and migration tests**

Assert one sync row per achievement and these fields:

```text
achievement_id
feishu_record_id
sync_status
last_synced_at
last_error
payload_hash
created_at
updated_at
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests\test_feishu_sync_model.py -q`

- [ ] **Step 3: Implement `FeishuSyncRecord`**

Use a unique foreign key to `achievements.id`, cascade deletion from the achievement relationship, and status values `pending`, `synced`, `failed`, `conflict`.

- [ ] **Step 4: Add idempotent SQLite schema creation**

`apply_schema_updates()` must create the table and index without altering existing teacher data.

- [ ] **Step 5: Run focused and schema tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_feishu_sync_model.py tests\test_test_database_isolation.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add app/models.py app/schema_updates.py tests/test_feishu_sync_model.py
git commit -m "feat: persist Feishu sync state"
```

### Task 3: Feishu Field Mapping and HTTP Client

**Files:**
- Create: `app/services/feishu_mapper.py`
- Create: `app/services/feishu_client.py`
- Test: `tests/test_feishu_mapper.py`
- Test: `tests/test_feishu_client.py`

- [ ] **Step 1: Write failing mapper tests**

Verify that:

- Local achievement ID becomes text field `成果平台ID`.
- Local categories/subcategories map only to existing Feishu select options.
- Local status becomes readable text.
- New records set `确认同步=false`, `同步状态=待确认`.
- Update payloads never include `确认同步`, `Obsidian链接`, `关键词`, or `可用于`.
- No material attachment is included.

- [ ] **Step 2: Implement the fixed mapper**

Map into the verified Feishu fields:

```text
成果平台ID, 成果名称, 成果年度, 成果大类, 成果细类,
级别, 本人角色, 状态, 备注, 确认同步, 同步状态, 同步说明
```

Unmatched subcategories become `其他`; broad category selection uses deterministic keyword rules and otherwise becomes `其他成果`.

- [ ] **Step 3: Write failing client tests with `httpx.MockTransport`**

Cover token acquisition, exact platform-ID search, create, update, timeout, permission error, no match, one match, and duplicate-match conflict.

- [ ] **Step 4: Implement `FeishuClient`**

Use:

```text
POST /open-apis/auth/v3/tenant_access_token/internal
POST /open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/search
POST /open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records
PUT  /open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/{record_id}
```

Set bounded connection/read timeouts. Raise typed exceptions without including credentials or full response bodies.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_feishu_mapper.py tests\test_feishu_client.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add app/services/feishu_mapper.py app/services/feishu_client.py tests/test_feishu_mapper.py tests/test_feishu_client.py
git commit -m "feat: add Feishu sync client"
```

### Task 4: Idempotent Synchronization Service

**Files:**
- Create: `app/services/feishu_sync.py`
- Test: `tests/test_feishu_sync.py`

- [ ] **Step 1: Write failing service tests**

Cover:

- New local achievement creates one Feishu record.
- Repeated sync updates the same record.
- Duplicate platform IDs create `conflict`.
- Feishu failure leaves the achievement intact and stores `failed`.
- Unchanged payload hash skips unnecessary updates.
- A confirmed existing Feishu record keeps its confirmation and external sync fields.

- [ ] **Step 2: Implement `sync_achievement()`**

The service must:

1. Upsert a local pending sync row.
2. Search by exact `成果平台ID`.
3. Create or update only platform-owned fields.
4. Persist record ID, hash and timestamp on success.
5. Persist a short safe error on failure.
6. Commit sync state independently of the already-committed achievement.

- [ ] **Step 3: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests\test_feishu_sync.py -q`

- [ ] **Step 4: Commit**

```powershell
git add app/services/feishu_sync.py tests/test_feishu_sync.py
git commit -m "feat: synchronize achievements to Feishu"
```

### Task 5: Save Hook, Detail Status and Manual Retry

**Files:**
- Modify: `app/routers/achievements.py`
- Modify: `app/templates/achievements/detail.html`
- Modify: `app/static/app.css`
- Test: `tests/test_achievements.py`
- Test: `tests/test_feishu_routes.py`

- [ ] **Step 1: Write failing route tests**

Verify:

- Other users never see a Feishu status or retry control and receive `403` from retry.
- The configured user sees pending/synced/failed/conflict status.
- Local create/update succeeds even when Feishu fails.
- Retry changes failed state when the client later succeeds.

- [ ] **Step 2: Add post-commit synchronization hooks**

Create/update routes first commit the achievement, then call the sync service only for the configured username and only when Feishu credentials are ready.

- [ ] **Step 3: Add the retry route**

Use:

```text
POST /achievements/{achievement_id}/feishu-sync
```

Server-side authorization must check both achievement ownership and the configured username.

- [ ] **Step 4: Add the compact detail status block**

Show one of `已同步`, `待同步`, `同步失败`, `数据冲突`, with last sync time or safe error summary. Failed/pending states expose a retry button.

- [ ] **Step 5: Run focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_achievements.py tests\test_feishu_routes.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add app/routers/achievements.py app/templates/achievements/detail.html app/static/app.css tests/test_achievements.py tests/test_feishu_routes.py
git commit -m "feat: expose Feishu sync workflow"
```

### Task 6: Natural-Language Draft Parser

**Files:**
- Create: `app/services/achievement_draft_parser.py`
- Test: `tests/test_achievement_draft_parser.py`

- [ ] **Step 1: Write failing parser tests**

Use the example:

```text
2025年指导学生参加江苏省职业技能竞赛数字艺术赛项，获得二等奖，我是第一指导教师。
```

Assert a validated draft with year, title, local category/subcategory, provincial level, role, scores, confidence and uncertain fields. Also test malformed model JSON, unknown categories, excessively long text and AI-unavailable fallback.

- [ ] **Step 2: Implement the deterministic fallback**

Without an AI key, extract year, level, role, result/process nature and match active rule names/keywords. Never invent a local category. Ambiguous values must appear in `uncertain_fields`.

- [ ] **Step 3: Implement the OpenAI-compatible adapter**

Call the configured `/chat/completions` endpoint with JSON response mode, a strict schema-oriented prompt, and active local rules. Validate all output before returning it.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests\test_achievement_draft_parser.py -q`

- [ ] **Step 5: Commit**

```powershell
git add app/services/achievement_draft_parser.py tests/test_achievement_draft_parser.py
git commit -m "feat: parse achievement descriptions"
```

### Task 7: Intelligent Entry UI

**Files:**
- Modify: `app/routers/achievements.py`
- Modify: `app/templates/achievements/form.html`
- Modify: `app/static/app.css`
- Test: `tests/test_feishu_routes.py`
- Test: `tests/test_layout_css.py`

- [x] **Step 1: Write failing access and response tests**

Verify the configured user sees the quick-entry panel, other users do not, unauthorized API calls return `403`, valid text returns a structured draft, and invalid input returns a concise validation error.

- [x] **Step 2: Add the draft endpoint**

Use:

```text
POST /achievements/intelligent-draft
```

Limit descriptions to 2,000 characters and return JSON only.

- [x] **Step 3: Add the quick-entry panel above the form**

Include a textarea, `识别并预填` button, progress/error state, and concise “请确认” indicator. The existing form remains the only save action.

- [x] **Step 4: Prefill the existing form**

JavaScript applies only validated response fields, triggers existing category/subcategory guidance updates, and never automatically submits.

- [x] **Step 5: Run focused UI tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_feishu_routes.py tests\test_layout_css.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add app/routers/achievements.py app/templates/achievements/form.html app/static/app.css tests/test_feishu_routes.py tests/test_layout_css.py
git commit -m "feat: add intelligent achievement entry"
```

### Task 8: Feishu Schema, Full Verification and Deployment

**Files:**
- Modify: `docs/superpowers/plans/2026-07-26-personal-feishu-achievement-sync.md`
- Server: `/etc/teacher-achievement-system.env`
- Feishu Base: app `H53dbNZsQalrU6sC8NPcp60QnQf`, table `tblh7YcuXoVeWqH4`

- [x] **Step 1: Create the missing Feishu field**

First re-list fields. Only if absent, run:

```powershell
lark-cli base +field-create --base-token H53dbNZsQalrU6sC8NPcp60QnQf --table-id tblh7YcuXoVeWqH4 --as user --json '{"name":"成果平台ID","type":"text"}'
```

- [x] **Step 2: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all tests pass.

- [ ] **Step 3: Configure production secrets**

Add the confirmed self-built-app credentials and integration settings to `/etc/teacher-achievement-system.env`. Never commit or print secret values.

- [x] **Step 4: Back up and deploy**

Run the existing production backup first, deploy the tracked source, restart `teacher-achievement.service`, and verify both service and Nginx remain active.

- [ ] **Step 5: Complete one controlled live synchronization**

Create a clearly named temporary achievement through the platform, confirm exactly one Feishu record is created with the same `成果平台ID`, update and resync it, then delete both test records.

- [ ] **Step 6: Verify the production workflow**

Check:

```text
Configured user sees intelligent entry
Other users do not see or access it
Description prefills but does not auto-submit
Local save succeeds before Feishu sync
Detail page shows sync state
Retry works after a simulated failure
Existing Feishu confirmation and Obsidian-managed fields remain untouched
```

- [ ] **Step 7: Commit deployment record and push**

```powershell
git add docs/superpowers/plans/2026-07-26-personal-feishu-achievement-sync.md
git commit -m "docs: record Feishu integration rollout"
git push origin codex/mvp-implementation
```
