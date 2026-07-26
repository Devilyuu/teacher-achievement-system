import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy import and_, case, not_, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Achievement, FeishuSyncRecord
from app.services.feishu_client import (
    FeishuAuthenticationError,
    FeishuClient,
    FeishuConfigurationError,
    FeishuConflictError,
    FeishuError,
    FeishuNetworkError,
    FeishuPermissionError,
    FeishuRecord,
)
from app.services.feishu_mapper import build_create_fields, build_update_fields


STALE_PENDING_SECONDS = 300


class FeishuSyncClient(Protocol):
    def search_records_by_platform_id(
        self,
        platform_id: int | str,
    ) -> tuple[FeishuRecord, ...]: ...

    def create_record(
        self,
        fields: dict[str, Any],
        *,
        client_token: str,
    ) -> FeishuRecord: ...

    def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
    ) -> FeishuRecord: ...


@dataclass(frozen=True)
class SyncResult:
    status: str
    record_id: str | None = None
    skipped: bool = False
    busy: bool = False
    error: str = ""


@dataclass(frozen=True)
class _CreateIntent:
    client_token: str
    fields: dict[str, Any]
    matches_current: bool


class _InvalidCreateIntent(ValueError):
    pass


def _canonical_payload_json(fields: dict[str, Any]) -> str:
    return json.dumps(
        fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_json_hash(serialized: str) -> str:
    return sha256(serialized.encode("utf-8")).hexdigest()


def _stable_payload_hash(fields: dict[str, Any]) -> str:
    return _payload_json_hash(_canonical_payload_json(fields))


def _safe_feishu_error(error: FeishuError) -> str:
    if isinstance(error, FeishuConfigurationError):
        return "飞书同步尚未配置"
    if isinstance(error, FeishuAuthenticationError):
        return "飞书认证失败，请联系管理员"
    if isinstance(error, FeishuPermissionError):
        return "飞书权限不足，请联系管理员"
    if isinstance(error, FeishuNetworkError):
        return "飞书网络连接失败，请稍后重试"
    if isinstance(error, FeishuConflictError):
        return "发现多条相同成果平台ID的飞书记录"
    return "飞书服务暂时不可用，请稍后重试"


def _commit_sync_state(db: Session) -> None:
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _busy_result(record_id: str | None = None) -> SyncResult:
    return SyncResult(
        status="pending",
        record_id=record_id,
        busy=True,
    )


def _claim_pending_lease(
    db: Session,
    *,
    achievement_id: int,
    payload_hash: str,
) -> tuple[str | None, SyncResult | None]:
    claim_token = uuid4().hex
    claimed_at = datetime.utcnow()
    stale_before = claimed_at - timedelta(seconds=STALE_PENDING_SECONDS)
    unchanged_synced = and_(
        FeishuSyncRecord.sync_status == "synced",
        FeishuSyncRecord.feishu_record_id.is_not(None),
        FeishuSyncRecord.payload_hash == payload_hash,
    )
    claim = db.execute(
        update(FeishuSyncRecord)
        .where(
            FeishuSyncRecord.achievement_id == achievement_id,
            or_(
                FeishuSyncRecord.sync_status != "pending",
                FeishuSyncRecord.updated_at < stale_before,
            ),
            not_(unchanged_synced),
        )
        .values(
            sync_status="pending",
            last_error="",
            sync_claim_token=claim_token,
            updated_at=claimed_at,
        )
        .execution_options(synchronize_session=False)
    )
    if claim.rowcount == 1:
        _commit_sync_state(db)
        return claim_token, None
    db.rollback()

    existing = db.scalar(
        select(FeishuSyncRecord).where(
            FeishuSyncRecord.achievement_id == achievement_id
        )
    )
    if existing is not None:
        existing_status = existing.sync_status
        existing_record_id = existing.feishu_record_id
        existing_hash = existing.payload_hash
        db.rollback()
        if (
            existing_status == "synced"
            and existing_record_id
            and existing_hash == payload_hash
        ):
            return None, SyncResult(
                status="synced",
                record_id=existing_record_id,
                skipped=True,
            )
        return None, _busy_result(existing_record_id)
    db.rollback()

    db.add(
        FeishuSyncRecord(
            achievement_id=achievement_id,
            sync_status="pending",
            last_error="",
            sync_claim_token=claim_token,
            updated_at=claimed_at,
        )
    )
    try:
        _commit_sync_state(db)
    except IntegrityError:
        existing = db.scalar(
            select(FeishuSyncRecord).where(
                FeishuSyncRecord.achievement_id == achievement_id
            )
        )
        if existing is None:
            db.rollback()
            raise
        existing_status = existing.sync_status
        existing_record_id = existing.feishu_record_id
        existing_hash = existing.payload_hash
        db.rollback()
        if (
            existing_status == "synced"
            and existing_record_id
            and existing_hash == payload_hash
        ):
            return None, SyncResult(
                status="synced",
                record_id=existing_record_id,
                skipped=True,
            )
        return None, _busy_result(existing_record_id)
    return claim_token, None


def _finish_claim(
    db: Session,
    *,
    achievement_id: int,
    claim_token: str,
    values: dict[str, Any],
) -> bool:
    finished = db.execute(
        update(FeishuSyncRecord)
        .where(
            FeishuSyncRecord.achievement_id == achievement_id,
            FeishuSyncRecord.sync_status == "pending",
            FeishuSyncRecord.sync_claim_token == claim_token,
        )
        .values(
            **values,
            sync_claim_token=None,
            updated_at=datetime.utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if finished.rowcount != 1:
        db.rollback()
        return False
    _commit_sync_state(db)
    return True


def _renew_claim(
    db: Session,
    *,
    achievement_id: int,
    claim_token: str,
) -> bool:
    renewed = db.execute(
        update(FeishuSyncRecord)
        .where(
            FeishuSyncRecord.achievement_id == achievement_id,
            FeishuSyncRecord.sync_status == "pending",
            FeishuSyncRecord.sync_claim_token == claim_token,
        )
        .values(updated_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )
    if renewed.rowcount != 1:
        db.rollback()
        return False
    _commit_sync_state(db)
    return True


def _prepare_create(
    db: Session,
    *,
    achievement_id: int,
    claim_token: str,
    current_payload_json: str,
    current_payload_hash: str,
) -> _CreateIntent | None:
    generated_client_token = str(uuid4())
    token_is_missing = FeishuSyncRecord.create_client_token.is_(None)
    prepared = db.execute(
        update(FeishuSyncRecord)
        .where(
            FeishuSyncRecord.achievement_id == achievement_id,
            FeishuSyncRecord.sync_status == "pending",
            FeishuSyncRecord.sync_claim_token == claim_token,
        )
        .values(
            create_client_token=case(
                (token_is_missing, generated_client_token),
                else_=FeishuSyncRecord.create_client_token,
            ),
            create_client_token_payload_hash=case(
                (token_is_missing, current_payload_hash),
                else_=FeishuSyncRecord.create_client_token_payload_hash,
            ),
            create_payload_json=case(
                (token_is_missing, current_payload_json),
                else_=FeishuSyncRecord.create_payload_json,
            ),
            updated_at=datetime.utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    if prepared.rowcount != 1:
        db.rollback()
        return None
    stored_intent = db.execute(
        select(
            FeishuSyncRecord.create_client_token,
            FeishuSyncRecord.create_client_token_payload_hash,
            FeishuSyncRecord.create_payload_json,
        ).where(
            FeishuSyncRecord.achievement_id == achievement_id,
            FeishuSyncRecord.sync_status == "pending",
            FeishuSyncRecord.sync_claim_token == claim_token,
        )
    ).one_or_none()
    if stored_intent is None:
        db.rollback()
        return None
    client_token, stored_payload_hash, stored_payload_json = stored_intent
    _commit_sync_state(db)

    if not all(
        isinstance(value, str) and value
        for value in (
            client_token,
            stored_payload_hash,
            stored_payload_json,
        )
    ):
        raise _InvalidCreateIntent
    try:
        if UUID(client_token).version != 4:
            raise _InvalidCreateIntent
        stored_fields = json.loads(stored_payload_json)
    except (TypeError, ValueError):
        raise _InvalidCreateIntent from None
    if not isinstance(stored_fields, dict):
        raise _InvalidCreateIntent
    canonical_stored_json = _canonical_payload_json(stored_fields)
    if (
        canonical_stored_json != stored_payload_json
        or _payload_json_hash(canonical_stored_json) != stored_payload_hash
    ):
        raise _InvalidCreateIntent
    return _CreateIntent(
        client_token=client_token,
        fields=stored_fields,
        matches_current=(
            stored_payload_hash == current_payload_hash
            and stored_payload_json == current_payload_json
        ),
    )


def sync_achievement(
    db: Session,
    achievement: Achievement,
    client: FeishuSyncClient | None = None,
) -> SyncResult:
    achievement_id = achievement.id
    create_fields = build_create_fields(achievement)
    create_payload_json = _canonical_payload_json(create_fields)
    create_payload_hash = _payload_json_hash(create_payload_json)
    update_fields = build_update_fields(achievement)
    payload_hash = _stable_payload_hash(update_fields)
    claim_token, existing_result = _claim_pending_lease(
        db,
        achievement_id=achievement_id,
        payload_hash=payload_hash,
    )
    if existing_result is not None:
        return existing_result
    assert claim_token is not None

    owns_client = client is None
    active_client = client if client is not None else FeishuClient()
    try:
        records = active_client.search_records_by_platform_id(achievement_id)
        if len(records) > 1:
            error = "发现多条相同成果平台ID的飞书记录"
            if not _finish_claim(
                db,
                achievement_id=achievement_id,
                claim_token=claim_token,
                values={
                    "sync_status": "conflict",
                    "last_error": error,
                },
            ):
                return _busy_result()
            return SyncResult(status="conflict", error=error)
        if records:
            if not _renew_claim(
                db,
                achievement_id=achievement_id,
                claim_token=claim_token,
            ):
                return _busy_result()
            remote_record = active_client.update_record(
                records[0].record_id,
                update_fields,
            )
        else:
            create_intent = _prepare_create(
                db,
                achievement_id=achievement_id,
                claim_token=claim_token,
                current_payload_json=create_payload_json,
                current_payload_hash=create_payload_hash,
            )
            if create_intent is None:
                return _busy_result()
            remote_record = active_client.create_record(
                create_intent.fields,
                client_token=create_intent.client_token,
            )
            if not create_intent.matches_current:
                if not _renew_claim(
                    db,
                    achievement_id=achievement_id,
                    claim_token=claim_token,
                ):
                    return _busy_result()
                remote_record = active_client.update_record(
                    remote_record.record_id,
                    update_fields,
                )

        if not _finish_claim(
            db,
            achievement_id=achievement_id,
            claim_token=claim_token,
            values={
                "feishu_record_id": remote_record.record_id,
                "sync_status": "synced",
                "last_synced_at": datetime.utcnow(),
                "last_error": "",
                "payload_hash": payload_hash,
                "create_client_token": None,
                "create_client_token_payload_hash": None,
                "create_payload_json": None,
            },
        ):
            return _busy_result()
        return SyncResult(status="synced", record_id=remote_record.record_id)
    except _InvalidCreateIntent:
        safe_error = "飞书创建幂等数据损坏，请联系管理员"
        if not _finish_claim(
            db,
            achievement_id=achievement_id,
            claim_token=claim_token,
            values={
                "sync_status": "failed",
                "last_error": safe_error,
            },
        ):
            return _busy_result()
        return SyncResult(status="failed", error=safe_error)
    except FeishuError as error:
        safe_error = _safe_feishu_error(error)
        result_status = (
            "conflict" if isinstance(error, FeishuConflictError) else "failed"
        )
        if not _finish_claim(
            db,
            achievement_id=achievement_id,
            claim_token=claim_token,
            values={
                "sync_status": result_status,
                "last_error": safe_error,
            },
        ):
            return _busy_result()
        return SyncResult(status=result_status, error=safe_error)
    finally:
        if owns_client:
            active_client.close()
