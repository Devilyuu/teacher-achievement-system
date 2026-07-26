from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Achievement, AchievementStatus, ClaimNature, User
from app.services.reporting_year import default_reporting_year


def test_authenticated_admin_can_create_achievement_and_see_it_in_list(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.post(
        "/achievements",
        data={
            "year": "2026",
            "category": "其他有价值工作（自定义）",
            "subcategory": "自定义工作事项",
            "claim_nature": "过程性工作",
            "title": "省级技能大赛裁判工作",
            "date_range": "2026-05",
            "level": "省级",
            "personal_role": "裁判",
            "current_stage": "已完成裁判工作并提交总结",
            "base_score": "0",
            "performance_score": "0",
            "claimed_score": "2",
            "notes": "说明该工作对专业建设的价值",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    detail_location = response.headers["location"]
    assert detail_location.startswith("/achievements/")
    assert detail_location != "/achievements"

    list_response = client.get("/achievements?year=2026")

    assert list_response.status_code == 200
    assert "省级技能大赛裁判工作" in list_response.text
    assert "待完善" in list_response.text

    detail_response = client.get(detail_location)
    assert detail_response.status_code == 200
    assert f'href="{detail_location}/edit"' in detail_response.text


def test_achievements_requires_authentication(app):
    client = TestClient(app)

    response = client.get("/achievements", follow_redirects=False)

    assert response.status_code in {401, 303}
    if response.status_code == 303:
        assert response.headers["location"] == "/login"


def test_new_achievement_form_shows_level_and_offline_review_guidance(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/achievements/new")

    assert response.status_code == 200
    assert 'option value="国家级"' in response.text
    assert 'option value="学院级"' in response.text
    assert "最终以线下审核认定为准" in response.text


def test_new_achievement_form_shows_base_and_performance_score_inputs(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/achievements/new")

    assert response.status_code == 200
    assert "<span>基本分</span>" in response.text
    assert 'type="number" step="0.01" min="0" name="base_score"' in response.text
    assert "<span>绩效分</span>" in response.text
    assert 'type="number" step="0.01" min="0" name="performance_score"' in response.text
    assert "基本分规则" in response.text
    assert "绩效分规则" in response.text
    assert 'id="base-rule-text"' in response.text
    assert 'id="performance-rule-text"' in response.text


def test_new_achievement_form_allows_selecting_reporting_year(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/achievements/new?year=2025")

    assert response.status_code == 200
    assert '<select name="year" required>' in response.text
    assert '<option value="2025" selected>2025 年</option>' in response.text
    assert '<option value="2026"' in response.text


def test_achievement_list_offers_previous_year_and_preserves_year_for_new_record(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/achievements?year=2025")

    assert response.status_code == 200
    assert '<option value="2025" selected>2025 年</option>' in response.text
    assert '<option value="2026"' in response.text
    assert 'href="/achievements/new?year=2025"' in response.text


def test_achievement_list_defaults_to_previous_reporting_year(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get("/achievements")

    assert response.status_code == 200
    assert f"{default_reporting_year()} 年度成果" in response.text
    assert f'href="/achievements/new?year={default_reporting_year()}"' in response.text


def test_achievement_detail_shows_matching_rule_and_assignment_mode(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = Achievement(
            user_id=admin.id,
            year=2026,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="江苏省职业技能竞赛数字艺术赛项二等奖",
            level="省级",
            personal_role="团队成员",
            claimed_score=5,
        )
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert "团队负责人申报并分配" in response.text
    assert "申报级别" in response.text
    assert "省级" in response.text
    assert "线下审核" in response.text


def test_achievement_detail_shows_readiness_reasons_for_pending_record(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = Achievement(
            user_id=admin.id,
            year=2026,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="详情页待完善提示成果",
            claimed_score=3,
            status=AchievementStatus.needs_info.value,
        )
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert "待完善原因" in response.text
    assert "未上传支撑材料" in response.text
    assert f'href="/achievements/{achievement_id}/edit"' in response.text


def test_achievement_detail_hides_readiness_reasons_for_ready_record(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = Achievement(
            user_id=admin.id,
            year=2026,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="详情页可申报成果",
            claimed_score=3,
            status=AchievementStatus.ready.value,
        )
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.get(f"/achievements/{achievement_id}")

    assert response.status_code == 200
    assert "待完善原因" not in response.text


def test_edit_achievement_shows_readiness_reasons_hint(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        achievement = Achievement(
            user_id=admin.id,
            year=2026,
            category="教学",
            subcategory="教学成果奖申报及获奖",
            claim_nature=ClaimNature.result.value,
            title="编辑页待完善提示成果",
            claimed_score=3,
            status=AchievementStatus.needs_info.value,
        )
        db.add(achievement)
        db.commit()
        achievement_id = achievement.id
    finally:
        db.close()

    response = client.get(f"/achievements/{achievement_id}/edit")

    assert response.status_code == 200
    assert "当前待完善原因" in response.text
    assert "未上传支撑材料" in response.text
    assert "保存后系统会重新判断状态" in response.text


def test_achievement_list_can_filter_and_export_by_year(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        db.add_all(
            [
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="教学",
                    subcategory="教学成果奖申报及获奖",
                    claim_nature=ClaimNature.result.value,
                    title="2026年度成果",
                    claimed_score=3,
                ),
                Achievement(
                    user_id=admin.id,
                    year=2027,
                    category="教学",
                    subcategory="教学成果奖申报及获奖",
                    claim_nature=ClaimNature.result.value,
                    title="2027年度成果",
                    claimed_score=4,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/achievements?year=2026")

    assert response.status_code == 200
    assert "2026年度成果" in response.text
    assert "2027年度成果" not in response.text
    assert 'href="/exports/2026/review"' in response.text


def test_achievement_list_groups_records_in_performance_category_order(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        db.add_all(
            [
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="科研与社会服务工作",
                    subcategory="横向课题及项目",
                    claim_nature=ClaimNature.result.value,
                    title="科研成果甲",
                    claimed_score=3,
                ),
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="教学",
                    subcategory="教学成果奖申报及获奖",
                    claim_nature=ClaimNature.result.value,
                    title="教学成果甲",
                    claimed_score=4,
                ),
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="教学",
                    subcategory="新开课程",
                    claim_nature=ClaimNature.result.value,
                    title="教学成果乙",
                    claimed_score=2,
                ),
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="其他有价值工作（自定义）",
                    subcategory="自定义工作事项",
                    claim_nature=ClaimNature.process.value,
                    title="自定义成果甲",
                    current_stage="进行中",
                    claimed_score=1,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get("/achievements?year=2026")

    assert response.status_code == 200
    assert response.text.count('class="category-section"') >= 3
    assert response.text.count("<h2>教学</h2>") == 1
    assert response.text.index("<h2>教学</h2>") < response.text.index(
        "<h2>科研与社会服务工作</h2>"
    )
    assert response.text.index("<h2>科研与社会服务工作</h2>") < response.text.index(
        "<h2>其他有价值工作（自定义）</h2>"
    )
    teaching_section = response.text.split("<h2>教学</h2>", 1)[1].split(
        'class="category-section"', 1
    )[0]
    assert "教学成果甲" in teaching_section
    assert "教学成果乙" in teaching_section


def test_achievement_list_filters_and_retains_selected_values(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )
    keyword = f"检索词{uuid4().hex[:6]}"
    matching_title = f"{keyword}成果"
    excluded_title = f"排除成果{uuid4().hex[:6]}"
    subcategory = "教学成果奖申报及获奖"

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(username="admin").one()
        db.add_all(
            [
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="教学",
                    subcategory=subcategory,
                    claim_nature=ClaimNature.result.value,
                    title=matching_title,
                    claimed_score=5,
                    status=AchievementStatus.ready.value,
                ),
                Achievement(
                    user_id=admin.id,
                    year=2026,
                    category="教学",
                    subcategory=subcategory,
                    claim_nature=ClaimNature.result.value,
                    title=excluded_title,
                    notes=keyword,
                    claimed_score=2,
                    status=AchievementStatus.needs_info.value,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/achievements",
        params={
            "year": 2026,
            "status": AchievementStatus.ready.value,
            "category": "教学",
            "subcategory": subcategory,
            "q": keyword,
        },
    )

    assert response.status_code == 200
    assert matching_title in response.text
    assert excluded_title not in response.text
    assert f'value="{AchievementStatus.ready.value}" selected' in response.text
    assert 'value="教学" selected' in response.text
    assert (
        f'value="{subcategory}" data-category="教学" selected'
        in response.text
    )
    assert f'value="{keyword}"' in response.text
    assert 'href="/exports/2026/review"' in response.text
    assert "/exports/2026/review?" not in response.text
    assert 'href="/achievements?year=2026"' in response.text


def test_achievement_list_shows_filtered_empty_state_and_active_rule_options(app):
    client = TestClient(app)
    client.post(
        "/login",
        data={"username": "admin", "password": "admin123456"},
        follow_redirects=False,
    )

    response = client.get(
        "/achievements",
        params={"year": 2026, "q": f"不存在{uuid4().hex}"},
    )

    assert response.status_code == 200
    assert "没有符合条件的成果" in response.text
    assert "清除筛选" in response.text
    assert 'data-category="教学"' in response.text
    assert "教学成果奖申报及获奖" in response.text
