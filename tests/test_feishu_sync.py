import json
from datetime import datetime, timedelta
from threading import Barrier, Event, Thread
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
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
    def __init__(
        self,
        records=(),
        *,
        db=None,
        search_error=None,
        create_error=None,
        update_error=None,
        on_search=None,
    ):
        self.records = tuple(records)
        self.db = db
        self.search_error = search_error
        self.create_error = create_error
        self.update_error = update_error
        self.on_search = on_search
        self.searches = []
        self.creates = []
        self.create_tokens = []
        self.updates = []

    def assert_no_db_transaction(self):
        if self.db is not None:
            assert self.db.in_transaction() is False

    def search_records_by_platform_id(self, platform_id):
        self.assert_no_db_transaction()
        self.searches.append(platform_id)
        if self.on_search is not None:
            self.on_search(platform_id)
        if self.search_error is not None:
            raise self.search_error
        return self.records

    def create_record(self, fields, *, client_token):
        self.assert_no_db_transaction()
        self.creates.append(fields)
        self.create_tokens.append(client_token)
        remote_record = FeishuRecord(
            record_id="rec-created",
            fields=dict(fields),
        )
        self.records = (remote_record,)
        if self.create_error is not None:
            raise self.create_error
        return remote_record

    def update_record(self, record_id, fields):
        self.assert_no_db_transaction()
        self.updates.append((record_id, fields))
        remote_record = FeishuRecord(record_id=record_id, fields=dict(fields))
        self.records = (remote_record,)
        if self.update_error is not None:
            raise self.update_error
        return remote_record


class FalseyFakeFeishuClient(FakeFeishuClient):
    def __bool__(self):
        return False


class DelayedVisibilityIdempotentClient:
    def __init__(self, db):
        self.db = db
        self.platform_id = None
        self.searches = []
        self.create_tokens = []
        self.create_fields = []
        self.persisted_tokens = []
        self.remote_records = {}
        self.updates = []
        self.lose_first_create_response = True

    def search_records_by_platform_id(self, platform_id):
        assert self.db.in_transaction() is False
        self.platform_id = platform_id
        self.searches.append(platform_id)
        return ()

    def create_record(self, fields, *, client_token):
        assert self.db.in_transaction() is False
        self.create_tokens.append(client_token)
        self.create_fields.append(dict(fields))
        observer_db = SessionLocal()
        try:
            persisted_intent = observer_db.query(
                models.FeishuSyncRecord.create_client_token,
                models.FeishuSyncRecord.create_client_token_payload_hash,
                models.FeishuSyncRecord.create_payload_json,
            ).filter_by(achievement_id=self.platform_id).one()
            self.persisted_tokens.append(tuple(persisted_intent))
        finally:
            observer_db.close()

        remote_record = self.remote_records.setdefault(
            client_token,
            FeishuRecord(
                record_id="rec-idempotent",
                fields=dict(fields),
            ),
        )
        if self.lose_first_create_response:
            self.lose_first_create_response = False
            raise FeishuNetworkError("response was lost after create")
        return remote_record

    def update_record(self, record_id, fields):
        assert self.db.in_transaction() is False
        self.updates.append((record_id, dict(fields)))
        updated_record = FeishuRecord(record_id=record_id, fields=dict(fields))
        for client_token, remote_record in self.remote_records.items():
            if remote_record.record_id == record_id:
                self.remote_records[client_token] = updated_record
                break
        return updated_record


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
        assert sync_record.create_client_token is None
        assert sync_record.create_client_token_payload_hash is None
        assert sync_record.create_payload_json is None
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


def test_concurrent_sessions_allow_only_one_external_create(app):
    from app.services.feishu_sync import sync_achievement

    setup_db = SessionLocal()
    try:
        achievement_id = create_achievement(setup_db).id
    finally:
        setup_db.close()

    barrier = Barrier(2)
    entered_search = Event()
    first_results = []
    first_errors = []

    def block_first_search(_platform_id):
        entered_search.set()
        barrier.wait(timeout=5)

    first_client = FakeFeishuClient(on_search=block_first_search)
    second_client = FakeFeishuClient()

    def run_first_sync():
        db = SessionLocal()
        db.expire_on_commit = False
        try:
            achievement = db.get(models.Achievement, achievement_id)
            first_results.append(
                sync_achievement(db, achievement, client=first_client)
            )
        except BaseException as error:
            first_errors.append(error)
        finally:
            db.close()

    first_thread = Thread(target=run_first_sync)
    first_thread.start()
    assert entered_search.wait(timeout=5)

    second_db = SessionLocal()
    second_db.expire_on_commit = False
    try:
        second_achievement = second_db.get(models.Achievement, achievement_id)
        second_result = sync_achievement(
            second_db,
            second_achievement,
            client=second_client,
        )
    finally:
        barrier.wait(timeout=5)
        second_db.close()
        first_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert first_errors == []
    assert first_results[0].status == "synced"
    assert second_result.status == "pending"
    assert second_result.busy is True
    assert second_client.searches == []
    assert second_client.creates == []
    assert len(first_client.creates) + len(second_client.creates) == 1


def test_concurrent_initial_insert_uses_unique_constraint_as_lease_fallback(app):
    from app.services.feishu_sync import sync_achievement

    setup_db = SessionLocal()
    try:
        achievement_id = create_achievement(setup_db).id
        test_engine = setup_db.get_bind()
    finally:
        setup_db.close()

    insert_barrier = Barrier(2)
    results = []
    clients = []
    errors = []

    def pause_before_sync_insert(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ):
        if statement.startswith("INSERT INTO feishu_sync_records"):
            insert_barrier.wait(timeout=5)

    def run_sync():
        db = SessionLocal()
        db.expire_on_commit = False
        client = FakeFeishuClient(db=db)
        clients.append(client)
        try:
            achievement = db.get(models.Achievement, achievement_id)
            results.append(sync_achievement(db, achievement, client=client))
        except BaseException as error:
            errors.append(error)
        finally:
            db.close()

    event.listen(test_engine, "before_cursor_execute", pause_before_sync_insert)
    threads = [Thread(target=run_sync), Thread(target=run_sync)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
    finally:
        event.remove(
            test_engine,
            "before_cursor_execute",
            pause_before_sync_insert,
        )

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(results) == 2
    assert sum(len(client.searches) for client in clients) == 1
    assert sum(len(client.creates) for client in clients) == 1
    assert sum(len(client.updates) for client in clients) == 0
    assert sum(
        result.status == "synced" and not result.skipped
        for result in results
    ) == 1
    assert sum(result.busy or result.skipped for result in results) == 1


def test_stale_pending_lease_can_be_claimed(app):
    from app.services.feishu_sync import STALE_PENDING_SECONDS, sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        db.add(
            models.FeishuSyncRecord(
                achievement_id=achievement.id,
                sync_status="pending",
                sync_claim_token="stale-owner",
                updated_at=datetime.utcnow()
                - timedelta(seconds=STALE_PENDING_SECONDS + 1),
            )
        )
        db.commit()
        client = FakeFeishuClient()

        result = sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "synced"
        assert result.busy is False
        assert client.searches == [achievement.id]
        assert len(client.creates) == 1
        assert sync_record.sync_claim_token is None
    finally:
        db.close()


@pytest.mark.parametrize(
    "records",
    [
        (),
        (FeishuRecord(record_id="rec-existing"),),
    ],
)
def test_search_create_and_update_run_without_a_database_transaction(
    app,
    records,
):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(records=records, db=db)

        result = sync_achievement(db, achievement, client=client)

        assert result.status == "synced"
        assert client.searches == [achievement.id]
        if records:
            assert len(client.updates) == 1
            assert client.creates == []
        else:
            assert len(client.creates) == 1
            assert client.updates == []
    finally:
        db.close()


def test_old_lease_owner_cannot_overwrite_a_new_claim(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)

        def replace_claim_token(platform_id):
            stealer_db = SessionLocal()
            try:
                stealer_db.query(models.FeishuSyncRecord).filter_by(
                    achievement_id=platform_id,
                    sync_status="pending",
                ).update(
                    {
                        models.FeishuSyncRecord.sync_claim_token: "new-owner",
                        models.FeishuSyncRecord.updated_at: datetime.utcnow(),
                    }
                )
                stealer_db.commit()
            finally:
                stealer_db.close()

        client = FakeFeishuClient(db=db, on_search=replace_claim_token)

        result = sync_achievement(db, achievement, client=client)

        db.expire_all()
        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "pending"
        assert result.busy is True
        assert sync_record.sync_status == "pending"
        assert sync_record.sync_claim_token == "new-owner"
        assert sync_record.feishu_record_id is None
    finally:
        db.close()


def test_stale_old_owner_cannot_mutate_after_new_owner_finishes(app):
    from app.services.feishu_sync import STALE_PENDING_SECONDS, sync_achievement

    setup_db = SessionLocal()
    try:
        achievement_id = create_achievement(setup_db).id
    finally:
        setup_db.close()

    search_barrier = Barrier(2)
    entered_search = Event()
    old_results = []
    old_errors = []

    def block_old_search(_platform_id):
        entered_search.set()
        search_barrier.wait(timeout=5)

    old_client = FakeFeishuClient(on_search=block_old_search)

    def run_old_sync():
        db = SessionLocal()
        db.expire_on_commit = False
        try:
            achievement = db.get(models.Achievement, achievement_id)
            old_results.append(sync_achievement(db, achievement, client=old_client))
        except BaseException as error:
            old_errors.append(error)
        finally:
            db.close()

    old_thread = Thread(target=run_old_sync)
    old_thread.start()
    assert entered_search.wait(timeout=5)

    lease_db = SessionLocal()
    try:
        lease_db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement_id,
            sync_status="pending",
        ).update(
            {
                models.FeishuSyncRecord.updated_at: datetime.utcnow()
                - timedelta(seconds=STALE_PENDING_SECONDS + 1)
            }
        )
        lease_db.commit()
    finally:
        lease_db.close()

    new_db = SessionLocal()
    new_db.expire_on_commit = False
    try:
        new_achievement = new_db.get(models.Achievement, achievement_id)
        new_client = FakeFeishuClient(db=new_db)
        new_result = sync_achievement(
            new_db,
            new_achievement,
            client=new_client,
        )
    finally:
        new_db.close()

    search_barrier.wait(timeout=5)
    old_thread.join(timeout=5)

    assert not old_thread.is_alive()
    assert old_errors == []
    assert new_result.status == "synced"
    assert len(new_client.creates) == 1
    assert old_results[0].status == "pending"
    assert old_results[0].busy is True
    assert old_client.creates == []
    assert old_client.updates == []


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


def test_remote_create_then_error_is_failed_and_retry_does_not_create_again(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(
            db=db,
            create_error=FeishuNetworkError("response was lost after write"),
        )

        first_result = sync_achievement(db, achievement, client=client)

        failed_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert first_result.status == "failed"
        assert failed_record.sync_status == "failed"
        assert failed_record.sync_claim_token is None
        assert len(client.creates) == 1

        client.create_error = None
        second_result = sync_achievement(db, achievement, client=client)

        assert second_result.status == "synced"
        assert second_result.record_id == "rec-created"
        assert len(client.creates) == 1
        assert len(client.updates) == 1
        assert client.updates[0][0] == "rec-created"
    finally:
        db.close()


def test_ambiguous_create_reuses_persisted_client_token_while_search_is_invisible(
    app,
):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = DelayedVisibilityIdempotentClient(db)

        first_result = sync_achievement(db, achievement, client=client)

        failed_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        first_token = failed_record.create_client_token
        first_create_hash = failed_record.create_client_token_payload_hash
        first_create_json = failed_record.create_payload_json
        assert first_result.status == "failed"
        assert first_token is not None
        assert UUID(first_token).version == 4
        assert first_create_hash is not None
        assert first_create_json is not None
        assert json.loads(first_create_json) == client.create_fields[0]
        assert client.persisted_tokens == [
            (first_token, first_create_hash, first_create_json)
        ]

        achievement.title = "Changed achievement B"
        db.commit()

        second_result = sync_achievement(db, achievement, client=client)

        db.refresh(failed_record)
        assert second_result.status == "synced"
        assert second_result.record_id == "rec-idempotent"
        assert failed_record.create_client_token is None
        assert failed_record.create_client_token_payload_hash is None
        assert failed_record.create_payload_json is None
        assert client.searches == [achievement.id, achievement.id]
        assert client.create_tokens == [first_token, first_token]
        assert client.create_fields == [
            json.loads(first_create_json),
            json.loads(first_create_json),
        ]
        assert client.persisted_tokens == [
            (first_token, first_create_hash, first_create_json),
            (first_token, first_create_hash, first_create_json),
        ]
        assert client.updates == [
            ("rec-idempotent", build_update_fields(achievement))
        ]
        assert len(client.remote_records) == 1
    finally:
        db.close()


def test_corrupt_stored_create_payload_fails_safely_without_remote_mutation(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client_token = str(uuid4())
        db.add(
            models.FeishuSyncRecord(
                achievement_id=achievement.id,
                sync_status="failed",
                create_client_token=client_token,
                create_client_token_payload_hash="0" * 64,
                create_payload_json="{not-valid-json",
            )
        )
        db.commit()
        client = FakeFeishuClient(db=db)

        result = sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "failed"
        assert result.error == "飞书创建幂等数据损坏，请联系管理员"
        assert client.searches == [achievement.id]
        assert client.creates == []
        assert client.updates == []
        assert sync_record.sync_status == "failed"
        assert sync_record.create_client_token == client_token
        assert sync_record.create_client_token_payload_hash == "0" * 64
        assert sync_record.create_payload_json == "{not-valid-json"
    finally:
        db.close()


def test_remote_update_error_is_stored_as_failed(app):
    from app.services.feishu_sync import sync_achievement

    db = SessionLocal()
    try:
        achievement = create_achievement(db)
        client = FakeFeishuClient(
            db=db,
            records=(FeishuRecord(record_id="rec-existing"),),
            update_error=FeishuNetworkError("response was lost after update"),
        )

        result = sync_achievement(db, achievement, client=client)

        sync_record = db.query(models.FeishuSyncRecord).filter_by(
            achievement_id=achievement.id
        ).one()
        assert result.status == "failed"
        assert sync_record.sync_status == "failed"
        assert sync_record.sync_claim_token is None
        assert client.creates == []
        assert len(client.updates) == 1
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

        assert rollback_calls
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

        def fail_final_commit():
            commit_calls.append(True)
            if len(commit_calls) == 3:
                db.flush()
                raise SQLAlchemyError("final sync state commit failed")
            real_commit()

        def track_rollback():
            rollback_calls.append(True)
            real_rollback()

        monkeypatch.setattr(db, "commit", fail_final_commit)
        monkeypatch.setattr(db, "rollback", track_rollback)

        with pytest.raises(SQLAlchemyError, match="final sync state commit failed"):
            sync_achievement(db, achievement, client=client)

        assert rollback_calls
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
