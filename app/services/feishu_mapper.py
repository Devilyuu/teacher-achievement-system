import re
from enum import Enum
from typing import Any


INITIAL_SYNC_NOTE = "由教师成果库自动写入，待确认后进入 Obsidian"

SUBCATEGORY_CATEGORIES = {
    "教科研考核优秀": "综合荣誉",
    "年度考核优秀": "综合荣誉",
    "记功表彰": "综合荣誉",
    "综合表彰": "综合荣誉",
    "教改课题": "教学建设与改革",
    "公共课教学改革": "教学建设与改革",
    "产教融合课题": "教学建设与改革",
    "师资建设课题": "教学建设与改革",
    "教学论文获奖": "教学建设与改革",
    "教学成果奖": "教学建设与改革",
    "教师教学竞赛": "教学建设与改革",
    "专业建设": "教学建设与改革",
    "社科课题": "科研项目",
    "软科学课题": "科研项目",
    "产学研项目": "科研项目",
    "横向课题": "科研项目",
    "科研获奖": "科研项目",
    "纵向课题": "科研项目",
    "期刊论文": "论文著作",
    "EI论文": "论文著作",
    "专著": "论文著作",
    "研究报告": "论文著作",
    "学生竞赛获奖": "指导学生",
    "优秀毕业设计": "指导学生",
    "创新创业项目": "指导学生",
    "学生作品展演": "指导学生",
    "教材建设项目": "教材与课程",
    "课程建设": "教材与课程",
    "教学资源建设": "教材与课程",
    "发明专利": "知识产权与成果转化",
    "实用新型专利": "知识产权与成果转化",
    "软件著作权": "知识产权与成果转化",
    "成果转化": "知识产权与成果转化",
    "社会服务": "社会服务与培训",
    "技术服务": "社会服务与培训",
    "讲座培训": "社会服务与培训",
    "行业服务": "社会服务与培训",
    "其他": "其他成果",
}

# Rules are ordered from the most specific wording to broader wording.
KEYWORD_SUBCATEGORIES = (
    ("软件著作权", ("软件著作权", "软著")),
    ("实用新型专利", ("实用新型", "外观专利")),
    ("发明专利", ("发明专利",)),
    ("成果转化", ("成果转化", "科技成果转化")),
    ("EI论文", ("ei论文", "ei 论文", "ei收录", "ei 收录")),
    ("专著", ("专著",)),
    ("研究报告", ("研究报告", "质量年报")),
    ("教学论文获奖", ("教学论文获奖",)),
    ("期刊论文", ("期刊发表", "期刊论文", "公开发表论文", "普通期刊")),
    ("学生竞赛获奖", ("指导学生大赛", "指导学生竞赛", "学生技能大赛", "学生比赛")),
    ("优秀毕业设计", ("优秀毕业设计", "毕业设计（论文）优秀", "毕业设计优秀")),
    ("创新创业项目", ("创新创业项目", "双创项目")),
    ("学生作品展演", ("学生作品展演", "学生作品展", "作品展布展")),
    (
        "教材建设项目",
        (
            "教材编写",
            "教材建设",
            "教材奖",
            "自编教材",
            "合作教材",
            "校本教材",
            "规划教材",
            "教材出版",
            "教材",
        ),
    ),
    ("教学资源建设", ("教学资源", "资源库", "虚拟仿真")),
    ("课程建设", ("课程建设", "新开课程", "在线课程", "微课")),
    ("公共课教学改革", ("公共课教学改革", "公共课改革")),
    ("产教融合课题", ("产教融合课题", "产教融合案例")),
    ("师资建设课题", ("师资建设", "青蓝工程", "教师帮带")),
    ("教学成果奖", ("教学成果奖",)),
    ("教师教学竞赛", ("教学能力比赛", "教师技能比赛", "教师教学竞赛")),
    ("专业建设", ("专业建设", "新专业开发", "品牌专业")),
    ("教改课题", ("教改课题", "教学改革课题", "教学项目")),
    ("社科课题", ("社科课题", "社会科学课题")),
    ("软科学课题", ("软科学课题",)),
    ("产学研项目", ("产学研项目", "产学研")),
    ("横向课题", ("横向课题", "横向项目")),
    ("纵向课题", ("纵向课题",)),
    ("科研获奖", ("科研获奖", "科研表彰")),
    ("教科研考核优秀", ("教科研考核优秀",)),
    ("年度考核优秀", ("年度考核优秀",)),
    ("记功表彰", ("记功",)),
    ("综合表彰", ("综合性荣誉", "综合荣誉", "先进个人", "表彰")),
    ("技术服务", ("技术服务",)),
    ("讲座培训", ("讲座培训", "培训项目", "社会培训", "党课主讲")),
    ("行业服务", ("行业服务", "行业产教融合共同体", "产业教授")),
    ("社会服务", ("社会服务",)),
)

LOCAL_SUBCATEGORY_MAPPINGS = {
    "实用新型、外观专利授权，软著登记": "实用新型专利",
    "教材编写出版(含双语专业、公开刊号的作品集合、专著)": "教材建设项目",
}

STATUS_LABELS = {
    "draft": "草稿",
    "needs_info": "待完善",
    "ready": "可申报",
    "exported": "已纳入导出",
    "草稿": "草稿",
    "待完善": "待完善",
    "可申报": "可申报",
    "已纳入导出": "已纳入导出",
}

LOCAL_CATEGORY_FALLBACKS = (
    ("育人成效", "指导学生"),
    ("学生工作", "指导学生"),
    ("产教融合", "教学建设与改革"),
    ("教师发展", "综合荣誉"),
    ("教学", "教学建设与改革"),
    ("科研", "科研项目"),
    ("社会服务", "社会服务与培训"),
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Enum):
        value = value.value
    return str(value).strip()


def _keyword_subcategory(value: Any) -> str | None:
    searchable = _text(value).casefold()
    for option, keywords in KEYWORD_SUBCATEGORIES:
        if any(keyword.casefold() in searchable for keyword in keywords):
            return option
    if re.search(r"\bei\b", searchable):
        return "EI论文"
    return None


def _subcategory_for(achievement: Any) -> str:
    subcategory = _text(achievement.subcategory)

    title_match = _keyword_subcategory(achievement.title)
    if title_match is not None:
        return title_match

    if subcategory in SUBCATEGORY_CATEGORIES:
        return subcategory

    explicit_match = LOCAL_SUBCATEGORY_MAPPINGS.get(subcategory)
    if explicit_match is not None:
        return explicit_match

    subcategory_match = _keyword_subcategory(subcategory)
    if subcategory_match is not None:
        return subcategory_match
    return "其他"


def _category_for(achievement: Any, subcategory: str) -> str:
    if subcategory != "其他":
        return SUBCATEGORY_CATEGORIES[subcategory]

    searchable = " ".join(
        (
            _text(achievement.category),
            _text(achievement.subcategory),
            _text(achievement.title),
        )
    )
    for keyword, option in LOCAL_CATEGORY_FALLBACKS:
        if keyword in searchable:
            return option
    return "其他成果"


def _readable_status(status: Any) -> str:
    value = _text(status)
    return STATUS_LABELS.get(value, value)


def _notes_for(achievement: Any) -> str:
    parts = (
        _text(getattr(achievement, "current_stage", "")),
        _text(getattr(achievement, "notes", "")),
    )
    return "；".join(part for part in parts if part)


def build_update_fields(achievement: Any) -> dict[str, Any]:
    subcategory = _subcategory_for(achievement)
    return {
        "成果平台ID": _text(achievement.id),
        "成果名称": _text(achievement.title),
        "成果年度": _text(achievement.year),
        "成果大类": _category_for(achievement, subcategory),
        "成果细类": subcategory,
        "级别": _text(getattr(achievement, "level", "")),
        "本人角色": _text(getattr(achievement, "personal_role", "")),
        "状态": _readable_status(getattr(achievement, "status", "")),
        "备注": _notes_for(achievement),
    }


def build_create_fields(achievement: Any) -> dict[str, Any]:
    return {
        **build_update_fields(achievement),
        "确认同步": False,
        "同步状态": "待确认",
        "同步说明": INITIAL_SYNC_NOTE,
    }
