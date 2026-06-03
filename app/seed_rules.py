from app.database import SessionLocal
from app.models import PerformanceRule, Role, User
from app.security import hash_password


INITIAL_RULES = [
    (
        "师德师风及党建思政工作",
        "政治学习、党员学习、党课主题、各类讲座会议主旨发言等",
        "0",
        "10/次",
        "5/次",
        "2/次",
        "1/次",
        "0.5/次",
        "个人申报",
        False,
        False,
    ),
    (
        "教师发展",
        "教师企业实践",
        "2/月",
        "",
        "",
        "",
        "",
        "",
        "个人申报，以学院派驻为准",
        False,
        False,
    ),
    (
        "教学",
        "精品在线开放课程建设（含虚拟仿真课程资源）",
        "2/门",
        "",
        "10/门",
        "",
        "3/门",
        "",
        "个人申报，验收通过；如获校级资助则无分",
        False,
        False,
    ),
    (
        "科研与社会服务工作",
        "纵向课题（教科研）",
        "3/项",
        "25/项",
        "15/项",
        "10/项（市级）/5/项（区级）",
        "3/项",
        "",
        "个人申报",
        False,
        False,
    ),
    (
        "教学",
        "教学成果奖申报及获奖",
        "10/项",
        "",
        "",
        "15/项",
        "10/项",
        "",
        "团队项目，负责人赋分",
        True,
        False,
    ),
    (
        "其他有价值工作（自定义）",
        "自定义工作事项",
        "",
        "",
        "",
        "",
        "",
        "",
        "用于记录现有绩效分类未覆盖但教师认为有必要申报的工作，例如省级职业技能大赛裁判、专家评审、专项支持等。需填写工作说明、价值说明和支撑材料，最终是否赋分以线下审核为准。",
        False,
        False,
    ),
]


def seed_initial_data() -> None:
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(username="admin").first():
            db.add(
                User(
                    username="admin",
                    full_name="系统管理员",
                    department="管理",
                    role=Role.admin.value,
                    password_hash=hash_password("admin123456"),
                )
            )

        for index, row in enumerate(INITIAL_RULES, start=1):
            exists = (
                db.query(PerformanceRule)
                .filter_by(category=row[0], subcategory=row[1])
                .first()
            )
            if not exists:
                db.add(
                    PerformanceRule(
                        category=row[0],
                        subcategory=row[1],
                        base_rule=row[2],
                        national_rule=row[3],
                        provincial_rule=row[4],
                        city_rule=row[5],
                        school_rule=row[6],
                        college_rule=row[7],
                        remark=row[8],
                        is_team=row[9],
                        is_department_assigned=row[10],
                        sort_order=index,
                    )
                )

        db.commit()
    finally:
        db.close()
