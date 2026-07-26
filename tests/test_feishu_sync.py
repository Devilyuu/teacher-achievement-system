from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.database import SessionLocal
from app.security import hash_password
from app.services.feishu_client import (
    FeishuNetworkError,
    FeishuPermissionError,
    FeishuRecord,
)
from app.services.feishu_mapper import build_update_fields


class FakeFeishuClient:
    def __init__(self, records=(), *, search_error=None, on_search=None):
        self.records = tuple(records)
        self.search_error = search_error
        self.on_search = on_search
        self.searches = []
        self.creates = []
        self.updates = []

    def search_records_by_platform_id(self, platform_id):
        self.searches.append(platform_id)
        if self.on_search is not None:
            self.on_search(platform_id)
        if self.search_error is not None:
            raise self.search_error
        return self.records

    def create_record(self, fields):
        self.creates.append(fields)
        return FeishuRecord(record_id="rec-created", fields=dict(fields))

    def update_record(self, record_id, fields):
        self.updates.append((record_id, fields))
        return FeishuRecord(record_id=record_id, fields=dict(fields))


class FalseyFakeFeishuClient(FakeFeishuClient):
    def __bool__(self):
        return False


def create_achievement(db, *, title="New Feishu achievement"):
    user = models.User(
        username=f"sync-{uuid4().hex}",
        full_name="Sync Teacher",
        department="Test",
        role=models.Role.teacher.value,
        password_hash=hash_password("password123"),
    )
    achievement = models.Achievement(
        user=user,
        year=2026,
        category="教学",
        subcategory="教学成果奖申报及获奖",
        claim_nature=models.ClaimNature.result.value,
        title=title,
        status=models.AchievementStatus.ready.value,
    )
    db.add(achievement)
    db.commit()
    db.refresh(achievement)
    return achievement


def test_new_achievement_creates_feishu_record_and_persists_synced_state(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient()

        result = sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "synced"
        assert result.record_id == "rec-created"
        assert result.skipped is False
        assert client.searches == [achievement.id]
        assert len(client.creates) == 1
        assert client.updates == []
        assert sync_record.feishu_record_id == "rec-created"
        assert sync_record.sync_status == "synced"
        assert sync_record.last_synced_at is not None
        assert sync_record.last_error == ""
        assert len(sync_record.payload_hash) == 64
        assert db.get(models.Achievement, achievement.id) is not None
    finally:
        db.close()


def test_explicit_falsey_client_is_still_used_for_dependency_injection(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FalseyFakeFeishuClient()

        result = sync_achievement(db, achievement, client=client)

        assert result.status == "synced"
        assert client.searches == [achievement.id]
        assert len(client.creates) == 1
    finally:
        db.close()


def test_pending_state_is_committed_before_the_external_search(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        observed_statuses = []

        def observe_pending(platform_id):
            observer_db = SessionLocal()
            try:
                sync_record = observer_db.query(models.FeishuSyncRecord).filter_by(
                    achievement_id=platform_id
                ).one()
                observed_statuses.append(sync_record.sync_status)
            finally:
                observer_db.close()

        client = FakeFeishuClient(on_search=observe_pending)

        sync_achievement(db, achievement, client=client)

        assert observed_statuses == ["pending"]
    finally:
        db.close()


def test_repeated_sync_updates_the_same_feishu_record(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient()
        first_result = sync_achievement(db, achievement, client=client)
        client.records = (
            FeishuRecord(record_id=first_result.record_id, fields=client.creates[0]),
        )

        achievement.title = "Updated Feishu achievement"
        db.commit()
        second_result = sync_achievement(db, achievement, client=client)

        assert second_result.status == "synced"
        assert second_result.record_id == "rec-created"
        assert len(client.creates) == 1
        assert len(client.updates) == 1
        assert client.updates[0][0] == "rec-created"
        assert db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).count() == 1
    finally:
        db.close()


def test_duplicate_platform_ids_store_conflict_without_writing_feishu(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(
            records=(
                FeishuRecord(record_id="rec-one"),
                FeishuRecord(record_id="rec-two"),
            )
        )

        result = sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "conflict"
        assert result.record_id is None
        assert result.error
        assert client.creates == []
        assert client.updates == []
        assert sync_record.sync_status == "conflict"
        assert sync_record.feishu_record_id is None
        assert sync_record.last_error == result.error
        assert "2" not in result.error
    finally:
        db.close()


def test_feishu_failure_is_safe_and_leaves_committed_achievement_intact(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        achievement_id = achievement.id
        client = FakeFeishuClient(
            search_error=FeishuNetworkError(
                "request failed with tenant_access_token=secret-value"
            )
        )

        result = sync_achievement(db, achievement, client=client)

        db.expire_all()
        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement_id
        ).one()
        assert result.status == "failed"
        assert result.error == "飞书网络连接失败，请稍后重试"
        assert "secret-value" not in result.error
        assert sync_record.sync_status == "failed"
        assert sync_record.last_error == result.error
        assert db.get(models.Achievement, achievement_id) is not None
    finally:
        db.close()


def test_unchanged_synced_payload_skips_all_external_calls(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient()
        first_result = sync_achievement(db, achievement, client=client)
        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        first_synced_at = sync_record.last_synced_at
        first_hash = sync_record.payload_hash
        call_counts = (
            len(client.searches),
            len(client.creates),
            len(client.updates),
        )

        second_result = sync_achievement(db, achievement, client=client)

        db.refresh(sync_record)
        assert second_result.status == "synced"
        assert second_result.record_id == first_result.record_id
        assert second_result.skipped is True
        assert (
            len(client.searches),
            len(client.creates),
            len(client.updates),
        ) == call_counts
        assert sync_record.sync_status == "synced"
        assert sync_record.last_synced_at == first_synced_at
        assert sync_record.payload_hash == first_hash
    finally:
        db.close()


@pytest.mark.parametrize(
    "external_fields",
    [
        {"确认同步": True},
        {"同步状态": "已同步", "Obsidian链接": "obsidian://open?vault=achievements"},
    ],
)
def test_confirmed_existing_record_receives_only_mapper_update_fields(
    app,
    external_fields,
):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(
            records=(
                FeishuRecord(
                    record_id="rec-confirmed",
                    fields=external_fields,
                ),
            )
        )

        result = sync_achievement(db, achievement, client=client)

        assert result.status == "synced"
        assert client.creates == []
        assert client.updates == [
            ("rec-confirmed", build_update_fields(achievement))
        ]
        assert set(external_fields).isdisjoint(client.updates[0][1])
    finally:
        db.close()


def test_permission_error_is_stored_without_sensitive_details(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(
            search_error=FeishuPermissionError(
                "app_secret=secret-value scope=bitable:app"
            )
        )

        result = sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "failed"
        assert result.error == "飞书权限不足，请联系管理员"
        assert "secret-value" not in sync_record.last_error
    finally:
        db.close()


def test_programming_errors_are_not_silently_converted_to_sync_failures(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(search_error=TypeError("fake client bug"))

        with pytest.raises(TypeError, match="fake client bug"):
            sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert sync_record.sync_status == "pending"
    finally:
        db.close()


def test_sync_state_commit_failure_rolls_back_and_keeps_session_usable(
    app,
    monkeypatch,
):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        achievement_id = achievement.id
        client = FakeFeishuClient()
        real_commit = db.commit
        real_rollback = db.rollback
        rollback_calls = []

        def fail_commit():
            db.flush()
            raise SQLAlchemyError("sync state commit failed")

        def track_rollback():
            rollback_calls.append(True)
            real_rollback()

        monkeypatch.setattr(db, "commit", fail_commit)
        monkeypatch.setattr(db, "rollback", track_rollback)

        with pytest.raises(SQLAlchemyError, match="sync state commit failed"):
            sync_achievement(db, achievement, client=client)

        assert rollback_calls == [True]
        assert client.searches == []

        monkeypatch.setattr(db, "commit", real_commit)
        monkeypatch.setattr(db, "rollback", real_rollback)
        assert db.get(models.Achievement, achievement_id) is not None
        assert db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement_id
        ).count() == 0
    finally:
        db.close()


def test_final_sync_state_commit_failure_rolls_back_to_retryable_pending(
    app,
    monkeypatch,
):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        achievement_id = achievement.id
        client = FakeFeishuClient()
        real_commit = db.commit
        real_rollback = db.rollback
        commit_calls = []
        rollback_calls = []

        def fail_second_commit():
            commit_calls.append(True)
            if len(commit_calls) == 2:
                db.flush()
                raise SQLAlchemyError("final sync state commit failed")
            real_commit()

        def track_rollback():
            rollback_calls.append(True)
            real_rollback()

        monkeypatch.setattr(db, "commit", fail_second_commit)
        monkeypatch.setattr(db, "rollback", track_rollback)

        with pytest.raises(SQLAlchemyError, match="final sync state commit failed"):
            sync_achievement(db, achievement, client=client)

        assert rollback_calls == [True]
        assert len(client.creates) == 1

        monkeypatch.setattr(db, "commit", real_commit)
        monkeypatch.setattr(db, "rollback", real_rollback)
        db.expire_all()
        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement_id
        ).one()
        assert sync_record.sync_status == "pending"
        assert sync_record.feishu_record_id is None
        assert db.get(models.Achievement, achievement_id) is not None
    finally:
        db.close()
