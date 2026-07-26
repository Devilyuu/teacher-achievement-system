from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app import models, schema_updates
from app.database import Base, SessionLocal
from app.security import hash_password


EXPECTED_SYNC_COLUMNS = {
    "achievement_id",
    "feishu_record_id",
    "sync_status",
    "last_synced_at",
    "last_error",
    "payload_hash",
    "created_at",
    "updated_at",
}
VALID_SYNC_STATUSES = {"pending", "synced", "failed", "conflict"}


def _create_achievement(db, *, title: str | None = None):
    user = models.User(
        username=f"feishu-{uuid4().hex}",
        full_name="Feishu Sync Teacher",
        department="Test",
        role=models.Role.teacher.value,
        password_hash=hash_password("password123"),
    )
    achievement = models.Achievement(
        user=user,
        year=2026,
        category="Teaching",
        subcategory="Achievement",
        claim_nature=models.ClaimNature.result.value,
        title=title or f"Feishu achievement {uuid4().hex[:8]}",
    )
    db.add(achievement)
    db.flush()
    return achievement


def _sync_record_type():
    assert hasattr(models, "FeishuSyncRecord"), "FeishuSyncRecord model is missing"
    return models.FeishuSyncRecord


def test_feishu_sync_record_has_required_columns_and_unique_foreign_key():
    _sync_record_type()
    table = Base.metadata.tables["feishu_sync_records"]

    assert EXPECTED_SYNC_COLUMNS <= set(table.columns.keys())
    assert table.c.last_synced_at.nullable
    assert {
        foreign_key.target_fullname
        for foreign_key in table.c.achievement_id.foreign_keys
    } == {"achievements.id"}
    assert any(
        index.unique
        and tuple(column.name for column in index.columns) == ("achievement_id",)
        for index in table.indexes
    )


def test_one_achievement_cannot_have_two_sync_records(app):
    sync_record_type = _sync_record_type()
    db = SessionLocal()
    try:
        achievement = _create_achievement(db)
        db.add(sync_record_type(achievement_id=achievement.id))
        db.commit()

        db.add(sync_record_type(achievement_id=achievement.id))

        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_sync_status_accepts_only_supported_values(app):
    sync_record_type = _sync_record_type()
    db = SessionLocal()
    try:
        for sync_status in VALID_SYNC_STATUSES:
            achievement = _create_achievement(db)
            db.add(
                sync_record_type(
                    achievement_id=achievement.id,
                    sync_status=sync_status,
                )
            )
        db.commit()

        statuses = {
            row.sync_status
            for row in db.query(sync_record_type).all()
        }
        assert statuses == VALID_SYNC_STATUSES

        invalid_achievement = _create_achievement(db)
        db.add(
            sync_record_type(
                achievement_id=invalid_achievement.id,
                sync_status="unknown",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_achievement_sync_record_relationship_is_one_to_one_and_cascades(app):
    sync_record_type = _sync_record_type()
    db = SessionLocal()
    try:
        achievement = _create_achievement(db)
        achievement.feishu_sync_record = sync_record_type(
            sync_status="pending",
            payload_hash="abc123",
        )
        db.commit()

        sync_record_id = achievement.feishu_sync_record.id
        assert achievement.feishu_sync_record.achievement is achievement

        db.delete(achievement)
        db.commit()

        assert db.get(sync_record_type, sync_record_id) is None
    finally:
        db.close()


def test_apply_schema_updates_is_idempotent_and_preserves_existing_data(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "existing.sqlite3"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER NOT NULL PRIMARY KEY,
                    username VARCHAR(80) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE achievements (
                    id INTEGER NOT NULL PRIMARY KEY,
                    title VARCHAR(255) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text("INSERT INTO users (id, username) VALUES (1, 'existing-teacher')")
        )
        connection.execute(
            text("INSERT INTO achievements (id, title) VALUES (1, 'Existing result')")
        )

    monkeypatch.setattr(schema_updates, "engine", engine)

    schema_updates.apply_schema_updates()
    schema_updates.apply_schema_updates()

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("feishu_sync_records")}
    indexes = {
        index["name"]: index
        for index in inspector.get_indexes("feishu_sync_records")
    }
    with engine.connect() as connection:
        existing_title = connection.scalar(
            text("SELECT title FROM achievements WHERE id = 1")
        )

    assert EXPECTED_SYNC_COLUMNS <= columns
    assert indexes["ix_feishu_sync_records_achievement_id"]["unique"] == 1
    assert existing_title == "Existing result"

    engine.dispose()


def test_feishu_sync_record_timestamp_fields_accept_datetime_values(app):
    sync_record_type = _sync_record_type()
    db = SessionLocal()
    timestamp = datetime.utcnow()
    try:
        achievement = _create_achievement(db)
        record = sync_record_type(
            achievement_id=achievement.id,
            last_synced_at=timestamp,
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        assert record.last_synced_at == timestamp
        assert record.created_at == timestamp
        assert record.updated_at == timestamp
    finally:
        db.close()
