from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import (
    Achievement,
    AchievementStatus,
    ClaimNature,
    FeishuSyncRecord,
    Role,
    User,
)
from app.security import create_auth_cookie, hash_password
from app.services.feishu_client import FeishuNetworkError, FeishuRecord
from app.services.feishu_sync import SyncResult


FEISHU_CREDENTIAL_VARIABLES = (
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BASE_TOKEN",
    "FEISHU_TABLE_ID",
)


class FakeFeishuClient:
    def __init__(
        self,
        records=(),
        *,
        create_error=None,
        update_error=None,
    ):
        self.records = tuple(records)
        self.create_error = create_error
        self.update_error = update_error
        self.searches = []
        self.creates = []
        self.updates = []

    def search_records_by_platform_id(self, platform_id):
        self.searches.append(platform_id)
        return self.records

    def create_record(self, fields, *, client_token):
        self.creates.append((dict(fields), client_token))
        if self.create_error is not None:
            raise self.create_error
        return FeishuRecord(record_id="rec-created", fields=dict(fields))

    def update_record(self, record_id, fields):
        self.updates.append((record_id, dict(fields)))
        if self.update_error is not None:
            raise self.update_error
        return FeishuRecord(record_id=record_id, fields=dict(fields))

    def close(self):
        pass


def _configure_ready_feishu(monkeypatch, username="personal-user"):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", username)
    for variable in FEISHU_CREDENTIAL_VARIABLES:
        monkeypatch.setenv(variable, f"test-{variable.lower()}")


def _configure_unready_feishu(monkeypatch, username="personal-user"):
    monkeypatch.setenv("FEISHU_SYNC_USERNAME", username)
    for variable in FEISHU_CREDENTIAL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def _create_owner_and_achievement(
    *,
    username="personal-user",
    sync_status=None,
    feishu_record_id=None,
    last_error="",
    last_synced_at=None,
):
    db = SessionLocal()
    try:
        user = User(
            username=username,
            full_name="测试教师",
            department="数字艺术学院",
            role=Role.teacher.value,
            password_hash=hash_password("password123"),
        )
        achievement = Achievement(
            user=user,
            year=2026,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="飞书路由测试成果",
            level="省级",
            personal_role="负责人",
            claimed_score=5,
            status=AchievementStatus.ready.value,
        )
        db.add(achievement)
        db.flush()
        if sync_status is not None:
            db.add(
                FeishuSyncRecord(
                    achievement_id=achievement.id,
                    feishu_record_id=feishu_record_id,
                    sync_status=sync_status,
                    last_error=last_error,
                    last_synced_at=last_synced_at,
                )
            )
        db.commit()
        return user.id, achievement.id
    finally:
        db.close()


def _authenticated_client(app, user_id):
    client = TestClient(app)
    client.cookies.set("user_id", create_auth_cookie(user_id))
    return client


def _create_user(username):
    db = SessionLocal()
    try:
        user = User(
            username=username,
            full_name="另一位测试教师",
            department="数字艺术学院",
            role=Role.teacher.value,
            password_hash=hash_password("password123"),
        )
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _achievement_form_data(title):
    return {
        "year": "2026",
        "category": "教学",
        "subcategory": "教学成果奖申报及获奖",
        "claim_nature": ClaimNature.result.value,
        "title": title,
        "date_range": "2026-06",
        "level": "省级",
        "personal_role": "负责人",
        "current_stage": "已完成",
        "base_score": "1",
        "performance_score": "2",
        "claimed_score": "3",
        "notes": "",
    }


def test_non_configured_user_has_no_feishu_ui_and_retry_is_forbidden(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        username="ordinary-user",
        sync_status="failed",
        last_error="飞书网络连接失败，请稍后重试",
    )
    sync_calls = []
    monkeypatch.setattr(
        "app.routers.achievements.sync_achievement",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)),
        raising=False,
    )
    client = _authenticated_client(app, user_id)

    detail_response = client.get(f"/achievements/{achievement_id}")
    retry_response = client.post(
        f"/achievements/{achievement_id}/feishu-sync",
        follow_redirects=False,
    )

    assert detail_response.status_code == 200
    assert "飞书同步" not in detail_response.text
    assert f"/achievements/{achievement_id}/feishu-sync" not in detail_response.text
    assert retry_response.status_code == 403
    assert sync_calls == []


def test_retry_checks_achievement_owner_before_personal_username_access(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    _, achievement_id = _create_owner_and_achievement(username="owner-user")
    configured_user_id = _create_user("personal-user")
    sync_calls = []
    monkeypatch.setattr(
        "app.routers.achievements.sync_achievement",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)),
    )
    client = _authenticated_client(app, configured_user_id)

    response = client.post(
        f"/achievements/{achievement_id}/feishu-sync",
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert sync_calls == []


@pytest.mark.parametrize(
    ("sync_status", "expected_label"),
    [
        ("synced", "已同步"),
        ("pending", "待同步"),
        ("failed", "同步失败"),
        ("conflict", "数据冲突"),
    ],
)
def test_configured_user_sees_each_feishu_sync_status(
    app,
    monkeypatch,
    sync_status,
    expected_label,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status=sync_status,
        last_error="飞书网络连接失败，请稍后重试",
        last_synced_at=datetime(2026, 7, 26, 9, 30),
    )
    client = _authenticated_client(app, user_id)

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert "飞书同步" in response.text
    assert expected_label in response.text
    if sync_status == "synced":
        assert "2026-07-26 09:30" in response.text
    else:
        assert "飞书网络连接失败，请稍后重试" in response.text


def test_feishu_last_error_is_html_escaped_on_detail_page(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status="failed",
        last_error="<script>alert('secret')</script>",
    )
    client = _authenticated_client(app, user_id)

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert "<script>alert" not in response.text
    assert "&lt;script&gt;alert" in response.text


@pytest.mark.parametrize(
    ("sync_status", "expected_label"),
    [
        ("failed", "同步失败"),
        ("pending", "待同步"),
    ],
)
def test_forged_sync_complete_query_does_not_override_persisted_status(
    app,
    monkeypatch,
    sync_status,
    expected_label,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status=sync_status,
        last_error="飞书网络连接失败，请稍后重试",
    )
    client = _authenticated_client(app, user_id)

    response = client.get(
        f"/achievements/{achievement_id}?feishu=sync-complete"
    )

    assert response.status_code == 200
    assert expected_label in response.text
    assert "飞书同步已完成。" not in response.text


@pytest.mark.parametrize(
    ("sync_status", "expected_notice"),
    [
        ("synced", "飞书同步已完成。"),
        ("pending", "同步任务正在处理中，请稍后再查看。"),
        ("failed", "飞书同步未完成，本地成果不受影响，可稍后重试。"),
        ("conflict", "飞书中存在重复记录，请先人工处理后再重试。"),
    ],
)
def test_attempt_feedback_is_derived_from_persisted_sync_status(
    app,
    monkeypatch,
    sync_status,
    expected_notice,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status=sync_status,
        last_error="安全错误摘要",
    )
    client = _authenticated_client(app, user_id)

    response = client.get(
        f"/achievements/{achievement_id}?feishu=attempted"
    )

    assert response.status_code == 200
    assert expected_notice in response.text


def test_forged_not_ready_query_does_not_override_ready_integration(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status="pending",
    )
    client = _authenticated_client(app, user_id)

    response = client.get(
        f"/achievements/{achievement_id}?feishu=not-ready"
    )

    assert response.status_code == 200
    assert "请联系管理员补充服务器端配置" not in response.text


@pytest.mark.parametrize("sync_status", ["pending", "failed", "conflict"])
def test_retryable_feishu_statuses_show_a_retry_control(
    app,
    monkeypatch,
    sync_status,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status=sync_status,
        last_error="请稍后重试",
    )
    client = _authenticated_client(app, user_id)

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert (
        f'action="/achievements/{achievement_id}/feishu-sync"'
        in response.text
    )
    if sync_status == "conflict":
        assert "人工处理" in response.text


def test_feishu_error_after_create_does_not_undo_local_save(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, _ = _create_owner_and_achievement()
    fake_client = FakeFeishuClient(
        create_error=FeishuNetworkError("private upstream response")
    )
    monkeypatch.setattr(
        "app.services.feishu_sync.FeishuClient",
        lambda: fake_client,
    )
    client = _authenticated_client(app, user_id)

    response = client.post(
        "/achievements",
        data=_achievement_form_data("本地创建仍成功"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    db = SessionLocal()
    try:
        saved = db.query(Achievement).filter_by(title="本地创建仍成功").one()
        sync_record = db.query(FeishuSyncRecord).filter_by(
            achievement_id=saved.id
        ).one()
        assert response.headers["location"] == f"/achievements/{saved.id}"
        assert sync_record.sync_status == "failed"
        assert sync_record.last_error == "飞书网络连接失败，请稍后重试"
        assert fake_client.searches == [saved.id]
        assert len(fake_client.creates) == 1
        assert fake_client.updates == []
    finally:
        db.close()


def test_feishu_error_after_update_does_not_undo_local_changes(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status="synced",
        feishu_record_id="rec-existing",
    )
    fake_client = FakeFeishuClient(
        records=(FeishuRecord(record_id="rec-existing"),),
        update_error=FeishuNetworkError("private upstream response"),
    )
    monkeypatch.setattr(
        "app.services.feishu_sync.FeishuClient",
        lambda: fake_client,
    )
    client = _authenticated_client(app, user_id)

    response = client.post(
        f"/achievements/{achievement_id}/edit",
        data=_achievement_form_data("本地更新仍成功"),
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/achievements/{achievement_id}"
    db = SessionLocal()
    try:
        assert db.get(Achievement, achievement_id).title == "本地更新仍成功"
        sync_record = db.query(FeishuSyncRecord).filter_by(
            achievement_id=achievement_id
        ).one()
        assert sync_record.sync_status == "failed"
        assert sync_record.last_error == "飞书网络连接失败，请稍后重试"
        assert fake_client.searches == [achievement_id]
        assert fake_client.creates == []
        assert len(fake_client.updates) == 1
    finally:
        db.close()


def test_ready_integration_syncs_once_after_each_create_and_update(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, _ = _create_owner_and_achievement()
    sync_calls = []

    def record_sync(db, achievement):
        sync_calls.append((achievement.id, achievement.title))
        return SyncResult(status="synced", record_id="rec-test")

    monkeypatch.setattr(
        "app.routers.achievements.sync_achievement",
        record_sync,
        raising=False,
    )
    client = _authenticated_client(app, user_id)

    create_response = client.post(
        "/achievements",
        data=_achievement_form_data("调用一次创建同步"),
        follow_redirects=False,
    )
    created_id = int(create_response.headers["location"].rsplit("/", 1)[1])
    update_response = client.post(
        f"/achievements/{created_id}/edit",
        data=_achievement_form_data("调用一次更新同步"),
        follow_redirects=False,
    )

    assert create_response.status_code == 303
    assert update_response.status_code == 303
    assert sync_calls == [
        (created_id, "调用一次创建同步"),
        (created_id, "调用一次更新同步"),
    ]


def test_retry_route_changes_failed_sync_to_synced_without_real_network(
    app,
    monkeypatch,
):
    _configure_ready_feishu(monkeypatch)
    user_id, achievement_id = _create_owner_and_achievement(
        sync_status="failed",
        last_error="飞书网络连接失败，请稍后重试",
    )

    class SuccessfulRetryClient:
        def search_records_by_platform_id(self, platform_id):
            assert platform_id == achievement_id
            return ()

        def create_record(self, fields, *, client_token):
            return FeishuRecord(record_id="rec-retried", fields=dict(fields))

        def update_record(self, record_id, fields):
            return FeishuRecord(record_id=record_id, fields=dict(fields))

        def close(self):
            pass

    monkeypatch.setattr(
        "app.services.feishu_sync.FeishuClient",
        SuccessfulRetryClient,
    )
    client = _authenticated_client(app, user_id)

    response = client.post(
        f"/achievements/{achievement_id}/feishu-sync",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/achievements/{achievement_id}?feishu=attempted"
    )
    db = SessionLocal()
    try:
        sync_record = db.query(FeishuSyncRecord).filter_by(
            achievement_id=achievement_id
        ).one()
        assert sync_record.sync_status == "synced"
        assert sync_record.feishu_record_id == "rec-retried"
    finally:
        db.close()


def test_missing_credentials_never_attempt_network_and_show_safe_hint(
    app,
    monkeypatch,
):
    _configure_unready_feishu(monkeypatch)
    user_id, _ = _create_owner_and_achievement()
    sync_calls = []
    monkeypatch.setattr(
        "app.routers.achievements.sync_achievement",
        lambda *args, **kwargs: sync_calls.append((args, kwargs)),
        raising=False,
    )
    client = _authenticated_client(app, user_id)

    create_response = client.post(
        "/achievements",
        data=_achievement_form_data("未配置凭证成果"),
        follow_redirects=False,
    )
    achievement_id = int(create_response.headers["location"].rsplit("/", 1)[1])
    retry_response = client.post(
        f"/achievements/{achievement_id}/feishu-sync",
        follow_redirects=False,
    )
    detail_response = client.get(retry_response.headers["location"])

    assert create_response.status_code == 303
    assert retry_response.status_code == 303
    assert retry_response.headers["location"] == (
        f"/achievements/{achievement_id}?feishu=attempted"
    )
    assert detail_response.status_code == 200
    assert "飞书同步" in detail_response.text
    assert "待同步" in detail_response.text
    assert "尚未配置" in detail_response.text
    assert sync_calls == []
