import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
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


class FeishuSyncClient(Protocol):
    def search_records_by_platform_id(
        self,
        platform_id: int | str,
    ) -> tuple[FeishuRecord, ...]: ...

    def create_record(self, fields: dict[str, Any]) -> FeishuRecord: ...

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
    error: str = ""


def _stable_payload_hash(fields: dict[str, Any]) -> str:
    serialized = json.dumps(
        fields,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(serialized.encode("utf-8")).hexdigest()


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


def sync_achievement(
    db: Session,
    achievement: Achievement,
    client: FeishuSyncClient | None = None,
) -> SyncResult:
    update_fields = build_update_fields(achievement)
    payload_hash = _stable_payload_hash(update_fields)
    sync_record = db.scalar(
        select(FeishuSyncRecord).where(
            FeishuSyncRecord.achievement_id == achievement.id
        )
    )
    if (
        sync_record is not None
        and sync_record.sync_status == "synced"
        and sync_record.feishu_record_id
        and sync_record.payload_hash == payload_hash
    ):
        return SyncResult(
            status="synced",
            record_id=sync_record.feishu_record_id,
            skipped=True,
        )
    if sync_record is None:
        sync_record = FeishuSyncRecord(achievement_id=achievement.id)
        db.add(sync_record)
    sync_record.sync_status = "pending"
    sync_record.last_error = ""
    _commit_sync_state(db)

    owns_client = client is None
    active_client = client if client is not None else FeishuClient()
    try:
        records = active_client.search_records_by_platform_id(achievement.id)
        if len(records) > 1:
            error = "发现多条相同成果平台ID的飞书记录"
            sync_record.sync_status = "conflict"
            sync_record.last_error = error
            _commit_sync_state(db)
            return SyncResult(status="conflict", error=error)
        if records:
            remote_record = active_client.update_record(
                records[0].record_id,
                update_fields,
            )
        else:
            remote_record = active_client.create_record(
                build_create_fields(achievement)
            )

        sync_record.feishu_record_id = remote_record.record_id
        sync_record.sync_status = "synced"
        sync_record.last_synced_at = datetime.utcnow()
        sync_record.last_error = ""
        sync_record.payload_hash = payload_hash
        _commit_sync_state(db)
        return SyncResult(status="synced", record_id=remote_record.record_id)
    except FeishuError as error:
        safe_error = _safe_feishu_error(error)
        result_status = (
            "conflict" if isinstance(error, FeishuConflictError) else "failed"
        )
        sync_record.sync_status = result_status
        sync_record.last_error = safe_error
        _commit_sync_state(db)
        return SyncResult(status=result_status, error=safe_error)
    finally:
        if owns_client:
            active_client.close()
