import json
from pathlib import Path

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Achievement, FeishuSyncRecord, User
from app.services.feishu_client import FeishuNetworkError, FeishuRecord


@pytest.fixture(scope="module")
def real_rules():
    rules_path = (
        Path(__file__).parents[1] / "app" / "data" / "performance_rules.json"
    )
    return json.loads(rules_path.read_text(encoding="utf-8"))["rules"]


def _achievement(title: str, achievement_id: int = 1) -> Achievement:
    return Achievement(
        id=achievement_id,
        user_id=1,
        year=2026,
        category="教师发展",
        subcategory="教师综合性荣誉",
        claim_nature="成果性工作",
        title=title,
    )


@pytest.mark.parametrize(
    ("remote_title", "local_title"),
    [
        ("2025年度教科研考核优秀", "获得25年度教科研考核优秀"),
        ("2025年度考核优秀", "获得25年 年度考核优秀"),
        (
            "事业单位连续三年考核优秀记功",
            "事业单位连续三年考核优秀，获得记功",
        ),
        (
            "《生成式人工智能赋能高职艺术设计类专业“专创融合”教学模式研究》"
            "获第十六届常州市高等教育和职业教育创新创业大赛双创论文三等奖",
            "论文获第十六届常州市高等教育和职业教育创新创业大赛双创论文三等奖",
        ),
    ],
)
def test_find_duplicate_matches_known_title_variants(remote_title, local_title):
    from app.services.feishu_reverse_sync import find_duplicate

    duplicate = find_duplicate(remote_title, [_achievement(local_title)])

    assert duplicate is not None
    assert duplicate.title == local_title


def test_find_duplicate_does_not_merge_similar_but_distinct_projects():
    from app.services.feishu_reverse_sync import find_duplicate

    duplicate = find_duplicate(
        "高职院校服务常州人工智能产业发展的数字创意人才培养机制研究",
        [
            _achievement(
                "高职院校服务常州人工智能产业发展的数字创意人才产教融合机制研究"
            )
        ],
    )

    assert duplicate is None


def test_map_remote_record_uses_feishu_category_context(real_rules):
    from app.services.feishu_reverse_sync import map_remote_record

    record = FeishuRecord(
        record_id="rec_project",
        fields={
            "成果名称": "生成式人工智能驱动常州文化IP活化的机制研究",
            "成果年度": "2026",
            "成果大类": "课题研究",
            "成果细类": "市社科",
            "级别": "市级",
            "状态": "已立项",
        },
    )

    mapped = map_remote_record(record, year=2026, rules=real_rules)

    assert mapped.title == "生成式人工智能驱动常州文化IP活化的机制研究"
    assert (mapped.category, mapped.subcategory) == (
        "科研与社会服务工作",
        "纵向课题（教科研）",
    )
    assert mapped.claim_nature == "成果性工作"
    assert mapped.level == "市级"


def test_map_remote_record_reads_rich_text_and_marks_process_work(real_rules):
    from app.services.feishu_reverse_sync import map_remote_record

    record = FeishuRecord(
        record_id="rec_process",
        fields={
            "成果名称": [{"type": "text", "text": "AI通识活页教材建设"}],
            "成果年度": 2026,
            "成果细类": ["教材建设"],
            "状态": "申报中",
            "备注": [{"type": "text", "text": "已完成初稿"}],
        },
    )

    mapped = map_remote_record(record, year=2026, rules=real_rules)

    assert mapped.title == "AI通识活页教材建设"
    assert mapped.category == "教学"
    assert mapped.claim_nature == "过程性工作"
    assert mapped.current_stage == "申报中"
    assert mapped.notes == "已完成初稿"


class RecordingFeishuClient:
    def __init__(self, *, fail_updates=0):
        self.updated = []
        self.fail_updates = fail_updates

    def update_record(self, record_id, fields):
        self.updated.append((record_id, fields))
        if self.fail_updates:
            self.fail_updates -= 1
            raise FeishuNetworkError("temporary Feishu failure")
        return FeishuRecord(record_id=record_id, fields=fields)


def _create_user(db, username="1867"):
    user = User(
        username=username,
        full_name="虞斌",
        department="创意设计学院",
        password_hash="test-only",
    )
    db.add(user)
    db.commit()
    return user


def test_import_records_dry_run_reports_without_writing(app, real_rules):
    from app.services.feishu_reverse_sync import import_records

    db = SessionLocal()
    user = _create_user(db)
    client = RecordingFeishuClient()
    records = (
        FeishuRecord(
            record_id="rec_new",
            fields={
                "成果名称": "2026年发表EI论文一篇",
                "成果年度": "2026",
            },
        ),
    )

    result = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=records,
        client=client,
        dry_run=True,
    )

    assert result.created == 1
    assert result.skipped == 0
    assert db.scalars(select(Achievement)).all() == []
    assert client.updated == []
    db.close()


def test_import_records_creates_links_and_is_idempotent(app, real_rules):
    from app.services.feishu_reverse_sync import import_records

    db = SessionLocal()
    user = _create_user(db)
    client = RecordingFeishuClient()
    records = (
        FeishuRecord(
            record_id="rec_new",
            fields={
                "成果名称": "2026年发表EI论文一篇",
                "成果年度": "2026",
                "状态": "已发表",
            },
        ),
    )

    first = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=records,
        client=client,
        dry_run=False,
    )
    second = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=records,
        client=client,
        dry_run=False,
    )

    achievements = db.scalars(select(Achievement)).all()
    links = db.scalars(select(FeishuSyncRecord)).all()
    assert first.created == 1
    assert second.created == 0
    assert second.skipped == 1
    assert len(achievements) == 1
    assert links[0].achievement_id == achievements[0].id
    assert links[0].feishu_record_id == "rec_new"
    assert client.updated == [
        ("rec_new", {"成果平台ID": str(achievements[0].id)})
    ]
    db.close()


def test_import_records_skips_existing_title_variant(app, real_rules):
    from app.services.feishu_reverse_sync import import_records

    db = SessionLocal()
    user = _create_user(db)
    existing = _achievement("获得25年度教科研考核优秀")
    existing.id = None
    existing.user_id = user.id
    db.add(existing)
    db.commit()
    client = RecordingFeishuClient()

    result = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=(
            FeishuRecord(
                record_id="rec_duplicate",
                fields={
                    "成果名称": "2025年度教科研考核优秀",
                    "成果年度": "2026",
                },
            ),
        ),
        client=client,
        dry_run=False,
    )

    assert result.created == 0
    assert result.skipped == 1
    assert len(db.scalars(select(Achievement)).all()) == 1
    link = db.scalar(
        select(FeishuSyncRecord).where(
            FeishuSyncRecord.achievement_id == existing.id
        )
    )
    assert link.feishu_record_id == "rec_duplicate"
    assert client.updated == [
        ("rec_duplicate", {"成果平台ID": str(existing.id)})
    ]
    db.close()


def test_import_records_keeps_distinct_remote_projects(app, real_rules):
    from app.services.feishu_reverse_sync import import_records

    db = SessionLocal()
    user = _create_user(db)
    client = RecordingFeishuClient()
    records = (
        FeishuRecord(
            record_id="rec_a",
            fields={
                "成果名称": "数字创意人才产教融合机制研究",
                "成果年度": "2026",
                "成果细类": "市社科",
            },
        ),
        FeishuRecord(
            record_id="rec_b",
            fields={
                "成果名称": "数字创意人才培养机制研究",
                "成果年度": "2026",
                "成果细类": "市社科",
            },
        ),
    )

    result = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=records,
        client=client,
        dry_run=False,
    )

    assert result.created == 2
    assert len(db.scalars(select(Achievement)).all()) == 2
    db.close()


def test_import_records_retries_platform_id_after_remote_update_failure(
    app,
    real_rules,
):
    from app.services.feishu_reverse_sync import import_records

    db = SessionLocal()
    user = _create_user(db)
    client = RecordingFeishuClient(fail_updates=1)
    records = (
        FeishuRecord(
            record_id="rec_retry",
            fields={
                "成果名称": "2026年发表EI论文一篇",
                "成果年度": "2026",
            },
        ),
    )

    first = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=records,
        client=client,
        dry_run=False,
    )
    second = import_records(
        db,
        user=user,
        year=2026,
        rules=real_rules,
        records=records,
        client=client,
        dry_run=False,
    )

    assert first.failed == 1
    assert second.skipped == 1
    assert len(db.scalars(select(Achievement)).all()) == 1
    link = db.scalar(select(FeishuSyncRecord))
    assert link.sync_status == "synced"
    assert len(client.updated) == 2
    db.close()
