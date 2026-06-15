from uuid import uuid4

from app.database import SessionLocal
from app.models import Achievement, AchievementStatus, ClaimNature, Role, User
from app.security import hash_password
from app.services.achievement_search import (
    AchievementFilters,
    search_achievements,
)


def _create_teacher(db, label: str) -> User:
    user = User(
        username=f"search-{uuid4().hex}",
        full_name=label,
        department="搜索测试学院",
        role=Role.teacher.value,
        password_hash=hash_password("password123"),
    )
    db.add(user)
    db.flush()
    return user


def _add_achievement(
    db,
    user: User,
    *,
    title: str,
    subcategory: str = "教学成果奖申报及获奖",
    current_stage: str = "",
    notes: str = "",
    year: int = 2026,
    status: str = AchievementStatus.needs_info.value,
    category: str = "教学",
) -> Achievement:
    achievement = Achievement(
        user_id=user.id,
        year=year,
        category=category,
        subcategory=subcategory,
        claim_nature=ClaimNature.result.value,
        title=title,
        current_stage=current_stage,
        notes=notes,
        claimed_score=3,
        status=status,
    )
    db.add(achievement)
    db.flush()
    return achievement


def test_keyword_search_matches_title_subcategory_stage_and_notes(app):
    db = SessionLocal()
    try:
        teacher = _create_teacher(db, "关键词教师")
        records = [
            _add_achievement(db, teacher, title="数字艺术竞赛二等奖"),
            _add_achievement(
                db,
                teacher,
                title="课程建设",
                subcategory="数字艺术课程资源建设",
            ),
            _add_achievement(
                db,
                teacher,
                title="专业调研",
                current_stage="已完成数字艺术企业访谈",
            ),
            _add_achievement(
                db,
                teacher,
                title="专项支持",
                notes="用于数字艺术专业建设",
            ),
            _add_achievement(db, teacher, title="完全无关"),
        ]
        db.commit()

        result = search_achievements(
            db,
            teacher.id,
            AchievementFilters(year=2026, keyword=" 数字艺术 "),
        )

        assert [item.id for item in result] == [
            records[3].id,
            records[2].id,
            records[1].id,
            records[0].id,
        ]
    finally:
        db.close()


def test_all_filters_intersect_and_other_users_records_are_excluded(app):
    db = SessionLocal()
    try:
        teacher = _create_teacher(db, "筛选教师")
        other = _create_teacher(db, "其他教师")
        matching = _add_achievement(
            db,
            teacher,
            title="在线精品课程建设",
            subcategory="精品在线开放课程建设（含虚拟仿真课程资源）",
            notes="重点项目",
            status=AchievementStatus.ready.value,
        )
        _add_achievement(
            db,
            teacher,
            title="状态不同",
            subcategory=matching.subcategory,
            notes="重点项目",
        )
        _add_achievement(
            db,
            teacher,
            title="大类不同",
            category="科研与社会服务工作",
            subcategory=matching.subcategory,
            notes="重点项目",
            status=AchievementStatus.ready.value,
        )
        _add_achievement(
            db,
            teacher,
            title="年度不同",
            year=2027,
            subcategory=matching.subcategory,
            notes="重点项目",
            status=AchievementStatus.ready.value,
        )
        _add_achievement(
            db,
            other,
            title="他人的同名成果",
            subcategory=matching.subcategory,
            notes="重点项目",
            status=AchievementStatus.ready.value,
        )
        db.commit()

        result = search_achievements(
            db,
            teacher.id,
            AchievementFilters(
                year=2026,
                status=AchievementStatus.ready.value,
                category="教学",
                subcategory=matching.subcategory,
                keyword="重点",
            ),
        )

        assert [item.id for item in result] == [matching.id]
    finally:
        db.close()
