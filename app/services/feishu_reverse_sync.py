import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Achievement,
    AchievementStatus,
    ClaimNature,
    FeishuSyncRecord,
    User,
)
from app.services.achievement_draft_parser import parse_achievement_draft
from app.services.feishu_client import FeishuError, FeishuRecord


PROCESS_STATUS_TERMS = (
    "申报中",
    "拟申报",
    "在研",
    "建设中",
    "执行中",
    "未入选",
)
LEVEL_ALIASES = {
    "国家级": "国家级",
    "省级": "省级",
    "市级": "市级",
    "市区级": "市级",
    "区级": "市级",
    "校级": "校级",
    "单位级": "校级",
    "学院级": "学院级",
}


@dataclass(frozen=True)
class RemoteAchievementDraft:
    record_id: str
    title: str
    year: int
    category: str
    subcategory: str
    claim_nature: str
    level: str
    personal_role: str
    current_stage: str
    notes: str
    platform_id: int | None


@dataclass(frozen=True)
class ReverseSyncItem:
    record_id: str
    title: str
    action: str
    category: str = ""
    subcategory: str = ""
    achievement_id: int | None = None
    reason: str = ""


@dataclass(frozen=True)
class ReverseSyncResult:
    created: int
    skipped: int
    failed: int
    items: tuple[ReverseSyncItem, ...]


class ReverseSyncClient(Protocol):
    def update_record(
        self,
        record_id: str,
        fields: dict[str, Any],
    ) -> FeishuRecord: ...


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(value).strip()
    if isinstance(value, list):
        parts = [_field_text(item) for item in value]
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        for key in ("text", "name", "value"):
            if key in value:
                return _field_text(value[key])
    return ""


def _normalized_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"(?<!\d)(\d{2})(?=年(?:度)?)", r"20\1", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("年年度", "年度")
    normalized = re.sub(r"^(?:完成|申报|获得|荣获|取得)", "", normalized)
    normalized = normalized.replace("获得", "")
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)


def _award_signature(value: str) -> str:
    normalized = _normalized_title(value)
    match = re.search(r"第.+?(?:特等奖|一等奖|二等奖|三等奖|优秀奖)$", normalized)
    return match.group(0) if match else ""


def find_duplicate(
    title: str,
    achievements: Sequence[Achievement],
) -> Achievement | None:
    normalized = _normalized_title(title)
    signature = _award_signature(title)
    for achievement in achievements:
        if _normalized_title(achievement.title) == normalized:
            return achievement
        local_signature = _award_signature(achievement.title)
        if (
            len(signature) >= 12
            and signature == local_signature
        ):
            return achievement
    return None


def _parse_platform_id(value: Any) -> int | None:
    text = _field_text(value)
    if not text or not text.isdigit():
        return None
    return int(text)


def map_remote_record(
    record: FeishuRecord,
    *,
    year: int,
    rules: Sequence[Any],
) -> RemoteAchievementDraft:
    fields = record.fields
    title = _field_text(fields.get("成果名称"))
    if not title:
        raise ValueError("Feishu record is missing its achievement title")

    remote_year_text = _field_text(fields.get("成果年度"))
    remote_year = int(remote_year_text) if remote_year_text.isdigit() else year
    if remote_year != year:
        raise ValueError("Feishu record belongs to a different year")

    status = _field_text(fields.get("状态"))
    notes = _field_text(fields.get("备注"))
    category_context = " ".join(
        value
        for value in (
            title,
            _field_text(fields.get("成果大类")),
            _field_text(fields.get("成果细类")),
            status,
            notes,
        )
        if value
    )
    parsed = parse_achievement_draft(
        category_context,
        rules,
        integration_config=SimpleNamespace(ai_ready=False),
    )
    raw_level = _field_text(fields.get("级别"))
    level = LEVEL_ALIASES.get(raw_level, parsed.level)
    claim_nature = (
        ClaimNature.process.value
        if any(term in status for term in PROCESS_STATUS_TERMS)
        else ClaimNature.result.value
    )

    return RemoteAchievementDraft(
        record_id=record.record_id,
        title=title,
        year=remote_year,
        category=parsed.category,
        subcategory=parsed.subcategory,
        claim_nature=claim_nature,
        level=level,
        personal_role=_field_text(fields.get("本人角色")),
        current_stage=status,
        notes=notes,
        platform_id=_parse_platform_id(fields.get("成果平台ID")),
    )


def _existing_link_for_achievement(
    db: Session,
    achievement_id: int,
) -> FeishuSyncRecord | None:
    return db.scalar(
        select(FeishuSyncRecord).where(
            FeishuSyncRecord.achievement_id == achievement_id
        )
    )


def _link_existing_achievement(
    db: Session,
    *,
    achievement: Achievement,
    draft: RemoteAchievementDraft,
    client: ReverseSyncClient,
) -> bool:
    link = _existing_link_for_achievement(db, achievement.id)
    if link is not None:
        if link.feishu_record_id != draft.record_id:
            return True
        if link.sync_status == "synced":
            return True
        return _sync_platform_id(db, link=link, draft=draft, client=client)

    link = FeishuSyncRecord(
        achievement_id=achievement.id,
        feishu_record_id=draft.record_id,
        sync_status="pending",
        last_error="",
        payload_hash="",
    )
    db.add(link)
    db.commit()
    return _sync_platform_id(db, link=link, draft=draft, client=client)


def _sync_platform_id(
    db: Session,
    *,
    link: FeishuSyncRecord,
    draft: RemoteAchievementDraft,
    client: ReverseSyncClient,
) -> bool:
    try:
        client.update_record(
            draft.record_id,
            {"成果平台ID": str(link.achievement_id)},
        )
    except FeishuError:
        link.sync_status = "failed"
        link.last_error = "反向同步后写回成果平台ID失败"
        db.commit()
        return False
    link.sync_status = "synced"
    link.last_synced_at = datetime.utcnow()
    link.last_error = ""
    db.commit()
    return True


def import_records(
    db: Session,
    *,
    user: User,
    year: int,
    rules: Sequence[Any],
    records: Sequence[FeishuRecord],
    client: ReverseSyncClient,
    dry_run: bool,
) -> ReverseSyncResult:
    baseline = list(
        db.scalars(
            select(Achievement).where(
                Achievement.user_id == user.id,
                Achievement.year == year,
            )
        )
    )
    linked_remote_records = {
        link.feishu_record_id: link
        for link in db.scalars(
            select(FeishuSyncRecord)
            .join(Achievement)
            .where(
                Achievement.user_id == user.id,
                FeishuSyncRecord.feishu_record_id.is_not(None),
            )
        )
        if link.feishu_record_id
    }
    items: list[ReverseSyncItem] = []

    for record in records:
        try:
            draft = map_remote_record(record, year=year, rules=rules)
        except ValueError as error:
            items.append(
                ReverseSyncItem(
                    record_id=record.record_id,
                    title=_field_text(record.fields.get("成果名称")),
                    action="failed",
                    reason=str(error),
                )
            )
            continue

        linked_record = linked_remote_records.get(draft.record_id)
        if linked_record is not None:
            if (
                not dry_run
                and linked_record.sync_status != "synced"
                and not _sync_platform_id(
                    db,
                    link=linked_record,
                    draft=draft,
                    client=client,
                )
            ):
                items.append(
                    ReverseSyncItem(
                        record_id=draft.record_id,
                        title=draft.title,
                        action="failed",
                        category=draft.category,
                        subcategory=draft.subcategory,
                        achievement_id=linked_record.achievement_id,
                        reason="成果已保存，但成果平台ID写回飞书失败",
                    )
                )
                continue
            items.append(
                ReverseSyncItem(
                    record_id=draft.record_id,
                    title=draft.title,
                    action="skipped",
                    category=draft.category,
                    subcategory=draft.subcategory,
                    reason="飞书记录已经同步",
                )
            )
            continue

        platform_match = next(
            (
                achievement
                for achievement in baseline
                if achievement.id == draft.platform_id
            ),
            None,
        )
        if draft.platform_id is not None and platform_match is None:
            items.append(
                ReverseSyncItem(
                    record_id=draft.record_id,
                    title=draft.title,
                    action="failed",
                    category=draft.category,
                    subcategory=draft.subcategory,
                    reason="成果平台ID不属于当前用户或当前年度",
                )
            )
            continue

        duplicate = platform_match or find_duplicate(draft.title, baseline)
        if duplicate is not None:
            linked = True
            if not dry_run:
                linked = _link_existing_achievement(
                    db,
                    achievement=duplicate,
                    draft=draft,
                    client=client,
                )
            if not linked:
                items.append(
                    ReverseSyncItem(
                        record_id=draft.record_id,
                        title=draft.title,
                        action="failed",
                        category=draft.category,
                        subcategory=draft.subcategory,
                        achievement_id=duplicate.id,
                        reason="重复成果已识别，但成果平台ID写回飞书失败",
                    )
                )
                continue
            items.append(
                ReverseSyncItem(
                    record_id=draft.record_id,
                    title=draft.title,
                    action="skipped",
                    category=draft.category,
                    subcategory=draft.subcategory,
                    achievement_id=duplicate.id,
                    reason="与网站已有成果重复",
                )
            )
            continue

        if dry_run:
            items.append(
                ReverseSyncItem(
                    record_id=draft.record_id,
                    title=draft.title,
                    action="created",
                    category=draft.category,
                    subcategory=draft.subcategory,
                    reason="模拟新增",
                )
            )
            continue

        achievement = Achievement(
            user_id=user.id,
            year=draft.year,
            category=draft.category,
            subcategory=draft.subcategory,
            claim_nature=draft.claim_nature,
            title=draft.title,
            date_range=f"{draft.year}年",
            level=draft.level,
            personal_role=draft.personal_role,
            current_stage=draft.current_stage,
            base_score=0,
            performance_score=0,
            claimed_score=0,
            status=AchievementStatus.needs_info.value,
            notes=draft.notes,
        )
        db.add(achievement)
        db.flush()
        db.add(
            FeishuSyncRecord(
                achievement_id=achievement.id,
                feishu_record_id=draft.record_id,
                sync_status="pending",
                last_error="",
                payload_hash="",
            )
        )
        db.commit()
        link = _existing_link_for_achievement(db, achievement.id)
        assert link is not None
        linked_remote_records[draft.record_id] = link
        if not _sync_platform_id(
            db,
            link=link,
            draft=draft,
            client=client,
        ):
            items.append(
                ReverseSyncItem(
                    record_id=draft.record_id,
                    title=draft.title,
                    action="failed",
                    category=draft.category,
                    subcategory=draft.subcategory,
                    achievement_id=achievement.id,
                    reason="成果已保存，但成果平台ID写回飞书失败",
                )
            )
            continue
        items.append(
            ReverseSyncItem(
                record_id=draft.record_id,
                title=draft.title,
                action="created",
                category=draft.category,
                subcategory=draft.subcategory,
                achievement_id=achievement.id,
            )
        )

    return ReverseSyncResult(
        created=sum(item.action == "created" for item in items),
        skipped=sum(item.action == "skipped" for item in items),
        failed=sum(item.action == "failed" for item in items),
        items=tuple(items),
    )
