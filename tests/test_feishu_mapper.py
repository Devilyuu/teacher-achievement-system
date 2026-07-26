import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models import AchievementStatus


ALLOWED_CATEGORIES = {
    "综合荣誉",
    "教学建设与改革",
    "科研项目",
    "论文著作",
    "指导学生",
    "教材与课程",
    "知识产权与成果转化",
    "社会服务与培训",
    "其他成果",
}
ALLOWED_SUBCATEGORIES = {
    "教科研考核优秀",
    "年度考核优秀",
    "记功表彰",
    "综合表彰",
    "教改课题",
    "公共课教学改革",
    "产教融合课题",
    "师资建设课题",
    "教学论文获奖",
    "教学成果奖",
    "教师教学竞赛",
    "专业建设",
    "社科课题",
    "软科学课题",
    "产学研项目",
    "横向课题",
    "科研获奖",
    "期刊论文",
    "EI论文",
    "专著",
    "研究报告",
    "学生竞赛获奖",
    "优秀毕业设计",
    "创新创业项目",
    "学生作品展演",
    "教材建设项目",
    "课程建设",
    "教学资源建设",
    "发明专利",
    "实用新型专利",
    "软件著作权",
    "成果转化",
    "社会服务",
    "技术服务",
    "讲座培训",
    "行业服务",
    "纵向课题",
    "其他",
}
EXTERNAL_FIELDS = {
    "确认同步",
    "同步状态",
    "同步说明",
    "关键词",
    "可用于",
    "Obsidian链接",
    "支撑材料",
    "材料",
}
PERFORMANCE_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "performance_rules.json"
)


def achievement(**overrides):
    values = {
        "id": 42,
        "year": 2026,
        "category": "教学",
        "subcategory": "教学成果奖申报及获奖",
        "title": "省级教学成果奖",
        "level": "省级",
        "personal_role": "第一完成人",
        "status": AchievementStatus.ready.value,
        "current_stage": "已完成验收",
        "notes": "等待证书",
        "materials": [SimpleNamespace(original_filename="secret-proof.pdf")],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def real_subcategory_containing(*keywords):
    catalog = json.loads(PERFORMANCE_RULES_PATH.read_text(encoding="utf-8"))
    matches = [
        rule["subcategory"]
        for rule in catalog["rules"]
        if all(keyword in rule["subcategory"] for keyword in keywords)
    ]
    assert len(matches) == 1
    return matches[0]


def test_create_fields_map_owned_values_and_initial_sync_defaults():
    from app.services.feishu_mapper import build_create_fields

    fields = build_create_fields(achievement())

    assert fields == {
        "成果平台ID": "42",
        "成果名称": "省级教学成果奖",
        "成果年度": "2026",
        "成果大类": "教学建设与改革",
        "成果细类": "教学成果奖",
        "级别": "省级",
        "本人角色": "第一完成人",
        "状态": "可申报",
        "备注": "已完成验收；等待证书",
        "确认同步": False,
        "同步状态": "待确认",
        "同步说明": "由教师成果库自动写入，待确认后进入 Obsidian",
    }
    assert "secret-proof.pdf" not in repr(fields)


def test_update_fields_never_include_sync_external_or_material_fields():
    from app.services.feishu_mapper import build_update_fields

    fields = build_update_fields(achievement())

    assert fields["成果平台ID"] == "42"
    assert fields["成果名称"] == "省级教学成果奖"
    assert EXTERNAL_FIELDS.isdisjoint(fields)
    assert "secret-proof.pdf" not in repr(fields)


@pytest.mark.parametrize(
    ("category", "subcategory", "title", "expected_category", "expected_subcategory"),
    [
        ("教师发展", "教师综合性荣誉", "年度先进个人", "综合荣誉", "综合表彰"),
        ("教学", "公共课教学改革", "公共课改革项目", "教学建设与改革", "公共课教学改革"),
        ("产教融合工作", "产教融合案例", "产教融合课题", "教学建设与改革", "产教融合课题"),
        ("科研与社会服务工作", "纵向课题（教科研）", "省级纵向课题", "科研项目", "纵向课题"),
        ("科研与社会服务工作", "普通期刊发表", "发表 EI 收录论文", "论文著作", "EI论文"),
        ("育人成效", "指导学生大赛（包括技能、双创）", "指导学生技能大赛获奖", "指导学生", "学生竞赛获奖"),
        ("教学", "教材编写出版", "校企合作教材", "教材与课程", "教材建设项目"),
        ("科研与社会服务工作", "实用新型、外观专利授权，软著登记", "软件著作权登记", "知识产权与成果转化", "软件著作权"),
        ("科研与社会服务工作", "科技成果转化", "专利成果转化", "知识产权与成果转化", "成果转化"),
        ("科研与社会服务工作", "社会培训服务工作", "行业讲座培训", "社会服务与培训", "讲座培训"),
    ],
)
def test_keyword_mapping_is_deterministic_and_uses_only_existing_options(
    category,
    subcategory,
    title,
    expected_category,
    expected_subcategory,
):
    from app.services.feishu_mapper import build_update_fields

    fields = build_update_fields(
        achievement(
            category=category,
            subcategory=subcategory,
            title=title,
        )
    )

    assert fields["成果大类"] == expected_category
    assert fields["成果细类"] == expected_subcategory
    assert fields["成果大类"] in ALLOWED_CATEGORIES
    assert fields["成果细类"] in ALLOWED_SUBCATEGORIES


@pytest.mark.parametrize(
    ("title", "expected_subcategory"),
    [
        ("实用新型专利授权", "实用新型专利"),
        ("软件著作权登记", "软件著作权"),
        ("知识产权成果登记", "实用新型专利"),
    ],
)
def test_patent_combination_subcategory_prefers_specific_title(
    title,
    expected_subcategory,
):
    from app.services.feishu_mapper import build_update_fields

    real_subcategory = real_subcategory_containing("实用新型", "软著")
    assert real_subcategory == "实用新型、外观专利授权，软著登记"

    fields = build_update_fields(
        achievement(
            category="科研与社会服务工作",
            subcategory=real_subcategory,
            title=title,
        )
    )

    assert fields["成果细类"] == expected_subcategory


@pytest.mark.parametrize(
    ("title", "expected_subcategory"),
    [
        ("正式出版校本教材", "教材建设项目"),
        ("个人学术专著出版", "专著"),
        ("正式出版成果", "教材建设项目"),
    ],
)
def test_book_combination_subcategory_prefers_specific_title(
    title,
    expected_subcategory,
):
    from app.services.feishu_mapper import build_update_fields

    real_subcategory = real_subcategory_containing("教材编写出版", "专著")
    assert real_subcategory == "教材编写出版(含双语专业、公开刊号的作品集合、专著)"

    fields = build_update_fields(
        achievement(
            category="教学",
            subcategory=real_subcategory,
            title=title,
        )
    )

    assert fields["成果细类"] == expected_subcategory


def test_specific_title_precedes_an_exact_local_subcategory():
    from app.services.feishu_mapper import build_update_fields

    real_subcategory = real_subcategory_containing("发明专利")
    assert real_subcategory == "发明专利"

    fields = build_update_fields(
        achievement(
            category="科研与社会服务工作",
            subcategory=real_subcategory,
            title="软件著作权登记",
        )
    )

    assert fields["成果细类"] == "软件著作权"


def test_unmatched_subcategory_falls_back_to_other_without_inventing_an_option():
    from app.services.feishu_mapper import build_update_fields

    fields = build_update_fields(
        achievement(
            category="教学",
            subcategory="完全未知的本地细类",
            title="教学相关日常工作",
        )
    )

    assert fields["成果大类"] == "教学建设与改革"
    assert fields["成果细类"] == "其他"
    assert fields["成果大类"] in ALLOWED_CATEGORIES
    assert fields["成果细类"] in ALLOWED_SUBCATEGORIES


def test_internal_status_name_is_converted_to_readable_text():
    from app.services.feishu_mapper import build_update_fields

    fields = build_update_fields(achievement(status="exported"))

    assert fields["状态"] == "已纳入导出"
