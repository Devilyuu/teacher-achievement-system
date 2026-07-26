import json
import math
import re
from dataclasses import dataclass
from typing import Annotated, Any, Sequence

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app import config
from app.models import ClaimNature
from app.services.performance_rule_guidance import LEVEL_OPTIONS


MAX_SCORE = 100_000.0
LEVEL_VALUES = {option["value"] for option in LEVEL_OPTIONS}
LEVEL_RULE_FIELDS = {
    option["value"]: option["rule_field"]
    for option in LEVEL_OPTIONS
}
CUSTOM_RULE_PAIR = (
    "其他有价值工作（自定义）",
    "自定义工作事项",
)
SEMANTIC_RULE_ALIASES = {
    ("教师发展", "教师综合性荣誉"): (
        "年度考核优秀",
        "教科研考核优秀",
        "考核优秀记功",
    ),
    ("科研与社会服务工作", "纵向课题（教科研）"): (
        "纵向课题",
        "教科研课题",
        "软科学研究课题",
        "社科研究课题",
        "社科课题",
        "市社科",
    ),
    ("科研与社会服务工作", "普通期刊发表"): (
        "发表论文",
        "论文发表",
        "论文收录",
        "EI收录",
        "SCI收录",
        "CSSCI收录",
    ),
    (
        "教学",
        "教材编写出版(含双语专业、公开刊号的作品集合、专著)",
    ): (
        "编写教材",
        "教材编写",
        "出版教材",
        "教材出版",
        "教材建设",
    ),
    (
        "科研与社会服务工作",
        "实用新型、外观专利授权，软著登记",
    ): (
        "实用新型",
        "外观专利",
        "软件著作权",
        "软著登记",
    ),
    (
        "教学",
        "教学项目（包括劳动教育、思政教育等案例）申报及获奖",
    ): (
        "教学典型案例",
        "教学模式案例",
        "课程典型案例",
        "教学项目申报",
    ),
    ("教学", "教学成果奖申报及获奖"): (
        "教学质量优秀",
        "教学成果奖",
    ),
    ("科研与社会服务工作", "科研表彰"): (
        "论文获奖",
        "科研获奖",
        "科研表彰",
    ),
    ("科研与社会服务工作", "社会培训服务工作"): (
        "专题培训",
        "开展培训",
        "社会培训",
    ),
    ("师德师风及党建思政工作", "宣传工作"): (
        "媒体报道",
        "新闻报道",
        "宣传报道",
    ),
    ("科研与社会服务工作", "横向课题及项目"): (
        "横向课题",
        "横向项目",
    ),
}
PROCESS_STAGE_KEYWORDS = (
    "申报中",
    "正在申报",
    "拟申报",
    "申报阶段",
    "在研",
    "执行中",
    "建设中",
)
RESULT_CONTEXT_TERMS = (
    "立项",
    "认定",
    "批准",
    "授予",
    "结项",
    "验收",
    "比赛结果",
    "竞赛结果",
)
ACHIEVEMENT_ENTITY_PATTERN = (
    r"(?:竞赛|大赛|比赛|赛项|项目|课题|成果奖|奖项|获奖)"
)
PROVINCE_LEVEL_REGIONS = (
    "北京市",
    "天津市",
    "上海市",
    "重庆市",
    "河北省",
    "山西省",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "海南省",
    "四川省",
    "贵州省",
    "云南省",
    "陕西省",
    "甘肃省",
    "青海省",
    "台湾省",
    "内蒙古自治区",
    "广西壮族自治区",
    "西藏自治区",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
    "香港特别行政区",
    "澳门特别行政区",
)
MUNICIPALITIES = ("北京市", "天津市", "上海市", "重庆市")
NEGATION_PATTERN = re.compile(
    r"(?:尚未|未|没有|不是|并非|不属于|不符合|非).{0,2}$"
)
UNCERTAIN_FIELD_NAMES = {
    "year",
    "title",
    "category",
    "subcategory",
    "claim_nature",
    "date_range",
    "level",
    "personal_role",
    "current_stage",
    "base_score",
    "performance_score",
    "claimed_score",
    "notes",
    "confidence",
}
AI_REASON_CODES = {
    "ai_not_configured",
    "ai_timeout",
    "ai_network_error",
    "ai_invalid_response",
}
ALLOWED_UNCERTAIN_FIELDS = UNCERTAIN_FIELD_NAMES | AI_REASON_CODES
AWARD_LABEL_RANKS = {
    "特等奖": "特",
    "一等奖": "一",
    "二等奖": "二",
    "三等奖": "三",
}
AWARD_LABEL_PATTERN = "|".join(AWARD_LABEL_RANKS)
AWARD_EVENT_PATTERN = re.compile(
    rf"(?:"
    rf"(?P<labelled_verb>获得|获评|获奖|荣获|取得|斩获|获)"
    rf"(?P<modifier>[^，,。；;！？!?\n]{{0,4}}?)"
    rf"(?P<label>{AWARD_LABEL_PATTERN})"
    rf"|"
    rf"(?P<generic_event>"
    rf"获奖(?!条件|名单|结果|信息|情况|要求|标准|资格)"
    rf"|获得(?:奖项|奖励)"
    rf")"
    rf")"
)
AWARD_EVENT_NEGATION_PATTERN = re.compile(
    r"(?:未能|没能|尚未|没有|并未|未曾|不曾|未|没)"
    r"(?:(?:最终|成功|正式|实际|真正|顺利|能够|能)){0,2}$"
)
AWARD_MODIFIER_TOKENS = (
    "国家级",
    "学院级",
    "等级为",
    "省级",
    "市级",
    "校级",
    "最终",
    "成功",
    "评为",
    "了",
)
BARE_AWARD_MODIFIER_TOKENS = (
    "国家级",
    "学院级",
    "省级",
    "市级",
    "校级",
    "了",
)
CLAUSE_PATTERN = re.compile(r"[^，,。；;！？!?\n]+")
NEGATED_CITY_PATTERN = re.compile(
    r"(?:尚未|未能|没有|并未|未曾|不曾|不是|并非|不属于|不符合|未|非)"
    r"(?P<city>[\u4e00-\u9fff]{2,4}市)(?!级)"
)


@dataclass(frozen=True)
class _AwardEvent:
    label: str | None
    affirmed: bool
    event_position: int
    label_position: int | None


class AchievementDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    year: int | None = Field(default=None, ge=1900, le=2100)
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(max_length=120)
    subcategory: str = Field(max_length=255)
    claim_nature: ClaimNature
    date_range: str = Field(default="", max_length=120)
    level: str = Field(default="", max_length=80)
    personal_role: str = Field(default="", max_length=80)
    current_stage: str = Field(default="", max_length=2000)
    base_score: float = Field(default=0, ge=0, le=MAX_SCORE)
    performance_score: float = Field(default=0, ge=0, le=MAX_SCORE)
    claimed_score: float = Field(default=0, ge=0, le=MAX_SCORE)
    notes: str = Field(default="", max_length=2000)
    confidence: float = Field(ge=0, le=1)
    uncertain_fields: list[Annotated[str, Field(max_length=32)]] = Field(
        default_factory=list,
        max_length=32,
    )

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        if value and value not in LEVEL_VALUES:
            raise ValueError("level must be one of the configured level options")
        return value

    @model_validator(mode="before")
    @classmethod
    def normalize_claimed_score(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        uncertain_fields = normalized.get("uncertain_fields", [])
        if not isinstance(uncertain_fields, (list, tuple)):
            raise ValueError("uncertain_fields must be a list or tuple")
        if any(
            not isinstance(field_name, str)
            or field_name not in ALLOWED_UNCERTAIN_FIELDS
            for field_name in uncertain_fields
        ):
            raise ValueError("uncertain_fields contains an unknown field")
        normalized["uncertain_fields"] = list(dict.fromkeys(uncertain_fields))

        scores = {}
        for field_name in ("base_score", "performance_score", "claimed_score"):
            score = float(normalized.get(field_name, 0))
            if not math.isfinite(score) or not 0 <= score <= MAX_SCORE:
                raise ValueError(f"{field_name} is outside the safe score range")
            scores[field_name] = score
        expected_total = scores["base_score"] + scores["performance_score"]
        if not math.isfinite(expected_total) or expected_total > MAX_SCORE:
            raise ValueError("combined score is outside the safe score range")
        if not math.isclose(scores["claimed_score"], expected_total):
            normalized["uncertain_fields"] = list(dict.fromkeys(
                [*normalized["uncertain_fields"], "claimed_score"]
            ))
        normalized.update(scores)
        normalized["claimed_score"] = expected_total
        return normalized


def _value(rule: Any, field_name: str, default: Any = "") -> Any:
    if isinstance(rule, dict):
        return rule.get(field_name, default)
    return getattr(rule, field_name, default)


def _active_rules(rules: Sequence[Any]) -> list[Any]:
    return [
        rule
        for rule in rules
        if _value(rule, "category")
        and _value(rule, "subcategory")
        and _value(rule, "is_active", True)
    ]


def _rule_payload(rule: Any) -> dict[str, Any]:
    field_names = (
        "category",
        "subcategory",
        "base_rule",
        "national_rule",
        "provincial_rule",
        "city_rule",
        "school_rule",
        "college_rule",
        "remark",
    )
    return {
        field_name: _value(rule, field_name)
        for field_name in field_names
    }


def _normalized_match_text(value: str) -> str:
    return re.sub(r"\W+", "", value.replace("竞赛", "大赛").replace("比赛", "大赛"))


def _semantic_rule_score(description: str, rule: Any) -> int:
    normalized_description = _normalized_match_text(description)
    subcategory = str(_value(rule, "subcategory"))
    normalized_subcategory = _normalized_match_text(subcategory)
    if (
        normalized_subcategory
        and normalized_subcategory in normalized_description
    ):
        return 200 + len(normalized_subcategory)

    main_phrase = re.split(r"[（(、/\n]", subcategory, maxsplit=1)[0]
    normalized_main_phrase = _normalized_match_text(main_phrase)
    if (
        len(normalized_main_phrase) >= 4
        and normalized_main_phrase in normalized_description
    ):
        return 100 + len(normalized_main_phrase)

    rule_pair = (
        str(_value(rule, "category")),
        subcategory,
    )
    normalized_aliases = (
        _normalized_match_text(alias)
        for alias in SEMANTIC_RULE_ALIASES.get(rule_pair, ())
    )
    matched_alias_lengths = [
        len(alias)
        for alias in normalized_aliases
        if alias and alias.casefold() in normalized_description.casefold()
    ]
    if matched_alias_lengths:
        return 190 + max(matched_alias_lengths)

    if rule_pair == (
        "教学",
        "教材编写出版(含双语专业、公开刊号的作品集合、专著)",
    ) and "教材" in description and any(
        word in description for word in ("编写", "出版", "建设")
    ):
        return 195

    if rule_pair == (
        "科研与社会服务工作",
        "科研表彰",
    ) and "论文" in description and any(
        label in description for label in AWARD_LABEL_RANKS
    ) and any(
        verb in description for verb in ("获得", "获评", "获奖", "荣获", "获")
    ):
        return 195

    if rule_pair == (
        "科研与社会服务工作",
        "普通期刊发表",
    ) and "论文" in description and any(
        word in description for word in ("发表", "刊发", "收录")
    ):
        return 195

    if (
        rule_pair[0] == "教师发展"
        and subcategory.startswith("教师参加其他比赛")
        and "指导学生" not in description
        and "参加" in description
        and any(
        word in description for word in ("竞赛", "大赛", "比赛", "赛项")
        )
    ):
        return 185

    if (
        "指导学生大赛" in subcategory
        and "指导学生" in description
        and any(word in description for word in ("竞赛", "大赛", "比赛", "赛项"))
    ):
        return 180
    if (
        "专业教学资源库" in subcategory
        and "专业教学资源库" in description
    ):
        return 180
    if (
        "精品在线开放课程" in subcategory
        and any(word in description for word in ("在线精品课程", "在线开放课程"))
    ):
        return 170
    return 0


def _match_rule(
    description: str,
    rules: Sequence[Any],
) -> tuple[Any | None, bool]:
    ranked = [
        (_semantic_rule_score(description, rule), rule)
        for rule in rules
        if (
            str(_value(rule, "category")),
            str(_value(rule, "subcategory")),
        )
        != CUSTOM_RULE_PAIR
    ]
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked and ranked[0][0] > 0:
        if len(ranked) == 1 or ranked[0][0] > ranked[1][0]:
            return ranked[0][1], False

    custom_rule = next(
        (
            rule
            for rule in rules
            if (
                str(_value(rule, "category")),
                str(_value(rule, "subcategory")),
            )
            == CUSTOM_RULE_PAIR
        ),
        None,
    )
    return custom_rule, custom_rule is not None


def _extract_year(description: str) -> int | None:
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", description)
    return int(match.group(1)) if match else None


def _city_candidate_spans(description: str) -> list[tuple[int, int, str]]:
    candidates = []
    negated_city_ends = set()
    for match in NEGATED_CITY_PATTERN.finditer(description):
        start, end = match.span("city")
        candidates.append((start, end, match.group("city")))
        negated_city_ends.add(end)

    for match in re.finditer(r"[\u4e00-\u9fff]{2,8}市(?!级)", description):
        if match.end() not in negated_city_ends:
            candidates.append((match.start(), match.end(), match.group(0)))
    return candidates


def _select_level_from_result_context(
    description: str,
    candidates: Sequence[tuple[int, str]],
) -> str:
    positions_by_level: dict[str, list[int]] = {}
    for position, level in candidates:
        positions_by_level.setdefault(level, []).append(position)
    if len(positions_by_level) == 1:
        return next(iter(positions_by_level))

    result_positions = [
        match.start()
        for term in RESULT_CONTEXT_TERMS
        for match in re.finditer(term, description)
        if not _is_negated(description, match.start())
    ]
    award_events = _award_events(description)
    if award_events and award_events[-1].affirmed:
        result_positions.append(award_events[-1].event_position)
    if not result_positions:
        return ""

    final_result_position = max(result_positions)
    ranked = sorted(
        (
            min(
                abs(position - final_result_position)
                for position in positions
            ),
            level,
        )
        for level, positions in positions_by_level.items()
    )
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return ""
    return ranked[0][1]


def _extract_level(description: str) -> str:
    candidates: list[tuple[int, str]] = []
    for level in ("国家级", "省级", "市级", "学院级", "校级"):
        candidates.extend(
            (match.start(), level)
            for match in re.finditer(level, description)
            if not _is_negated(description, match.start())
        )

    for match in re.finditer(r"(?:全国|国家)", description):
        if (
            not _is_negated(description, match.start())
            and re.search(
                ACHIEVEMENT_ENTITY_PATTERN,
                description[match.end():match.end() + 20],
            )
        ):
            candidates.append((match.start(), "国家级"))

    for region in PROVINCE_LEVEL_REGIONS:
        start = description.find(region)
        while start >= 0:
            end = start + len(region)
            if (
                not _is_negated(description, start)
                and re.search(
                    ACHIEVEMENT_ENTITY_PATTERN,
                    description[end:end + 20],
                )
            ):
                candidates.append((start, "省级"))
            start = description.find(region, start + 1)

    for start, end, city_text in _city_candidate_spans(description):
        if any(city_text.endswith(region) for region in MUNICIPALITIES):
            continue
        if (
            not _is_negated(description, start)
            and re.search(
                ACHIEVEMENT_ENTITY_PATTERN,
                description[end:end + 20],
            )
        ):
            candidates.append((start, "市级"))
    if not candidates:
        return ""
    return _select_level_from_result_context(description, candidates)


def _extract_role(description: str) -> str:
    roles = (
        "第一指导教师",
        "第二指导教师",
        "指导教师",
        "负责人",
        "主持人",
        "主持",
        "成员",
    )
    return next((role for role in roles if role in description), "")


def _clean_title(description: str) -> str:
    title = description.strip()
    title = re.sub(
        r"^(?:于)?(?:19|20)\d{2}年(?:度)?[，,；;：:\s]*",
        "",
        title,
    )
    title = re.sub(
        r"^(?:我)?(?:是|作为|担任)(?:第一指导教师|第二指导教师|指导教师|负责人|"
        r"主持人|主持|成员)[，,；;：:\s]*",
        "",
        title,
    )
    title = re.sub(
        r"[，,；;。.\s]*(?:(?:我(?:是|作为|担任)?)|(?:担任|作为))"
        r"(?:第一指导教师|第二指导教师|"
        r"指导教师|负责人|主持人|主持|成员)[。.\s]*$",
        "",
        title,
    )
    return title.strip(" ，,；;。.")


def _current_stage(description: str) -> str:
    return next(
        (
            keyword
            for keyword in PROCESS_STAGE_KEYWORDS
            if keyword in description
        ),
        "",
    )


def _single_number(rule_text: str) -> float | None:
    numbers = re.findall(r"(?<![\d.])\d+(?:\.\d+)?", rule_text)
    if len(numbers) != 1:
        return None
    score = float(numbers[0])
    if not math.isfinite(score) or not 0 <= score <= MAX_SCORE:
        return None
    return score


def _is_negated(text: str, start: int, *, lookback: int = 5) -> bool:
    prefix = text[max(0, start - lookback):start]
    return NEGATION_PATTERN.search(prefix) is not None


def _has_affirmed_phrase(description: str, phrases: Sequence[str]) -> bool:
    for phrase in phrases:
        start = description.find(phrase)
        while start >= 0:
            if not _is_negated(description, start):
                return True
            start = description.find(phrase, start + 1)
    return False


def _modifier_uses_only(
    modifier: str,
    allowed_tokens: Sequence[str],
) -> bool:
    remainder = modifier
    while remainder:
        token = next(
            (token for token in allowed_tokens if remainder.startswith(token)),
            None,
        )
        if token is None:
            return False
        remainder = remainder[len(token):]
    return True


def _award_events(text: str) -> list[_AwardEvent]:
    events: list[_AwardEvent] = []
    for clause_match in CLAUSE_PATTERN.finditer(text):
        clause = clause_match.group(0)
        clause_start = clause_match.start()
        previous_event_end = 0
        for match in AWARD_EVENT_PATTERN.finditer(clause):
            labelled_verb = match.group("labelled_verb")
            if labelled_verb:
                modifier = match.group("modifier")
                allowed_tokens = (
                    BARE_AWARD_MODIFIER_TOKENS
                    if labelled_verb == "获"
                    else AWARD_MODIFIER_TOKENS
                )
                if not _modifier_uses_only(modifier, allowed_tokens):
                    continue
                event_group = "labelled_verb"
            else:
                event_group = "generic_event"

            event_start = match.start(event_group)
            event_position = clause_start + event_start
            label_position = (
                clause_start + match.start("label")
                if match.group("label")
                else None
            )
            event_prefix = clause[previous_event_end:event_start]
            events.append(
                _AwardEvent(
                    label=match.group("label"),
                    affirmed=(
                        AWARD_EVENT_NEGATION_PATTERN.search(event_prefix)
                        is None
                    ),
                    event_position=event_position,
                    label_position=label_position,
                )
            )
            previous_event_end = match.end()
    return events


def _condition_is_met(condition: str, description: str) -> bool:
    if "获奖" in condition:
        award_events = _award_events(description)
        if not award_events or not award_events[-1].affirmed:
            return False
    requirements = (
        ("验收通过", ("验收通过", "通过验收", "验收合格")),
        ("立项", ("已立项", "获批立项", "立项")),
        ("结项", ("已结项", "结项", "结题")),
    )
    for marker, evidence in requirements:
        if marker in condition and not _has_affirmed_phrase(description, evidence):
            return False
    return True


def _last_award_event_rank(description: str) -> str | None:
    events = _award_events(description)
    if not events or not events[-1].affirmed:
        return None
    return AWARD_LABEL_RANKS.get(events[-1].label)


def _score_from_rule_text(rule_text: str, description: str) -> float | None:
    conditions = re.findall(r"[（(]([^）)]*)[）)]", rule_text)
    if any(not _condition_is_met(condition, description) for condition in conditions):
        return None

    award_rank = _last_award_event_rank(description)
    if award_rank:
        match = re.search(
            rf"(?:国|省|市|校|院)?{award_rank}(?:等(?:奖)?)?\s*(\d+(?:\.\d+)?)",
            rule_text,
        )
        if match:
            score = float(match.group(1))
            if math.isfinite(score) and 0 <= score <= MAX_SCORE:
                return score
            return None
    return _single_number(rule_text)


def _calibrated_confidence(
    base_confidence: float,
    uncertain_fields: Sequence[str],
) -> float:
    field_uncertainty_count = sum(
        not field_name.startswith("ai_")
        for field_name in uncertain_fields
    )
    return round(
        max(0.1, min(0.95, base_confidence - 0.04 * field_uncertainty_count)),
        2,
    )


def _deterministic_parse(
    description: str,
    rules: Sequence[Any],
    *,
    ai_reason: str,
) -> AchievementDraft:
    year = _extract_year(description)
    level = _extract_level(description)
    role = _extract_role(description)
    rule, used_custom_fallback = _match_rule(description, rules)
    category = str(_value(rule, "category")) if rule else ""
    subcategory = str(_value(rule, "subcategory")) if rule else ""
    base_score = (
        _score_from_rule_text(str(_value(rule, "base_rule")), description)
        if rule
        else None
    )
    level_rule = LEVEL_RULE_FIELDS.get(level, "")
    performance_score = (
        _score_from_rule_text(str(_value(rule, level_rule)), description)
        if rule and level_rule
        else None
    )
    title = _clean_title(description)
    uncertain_fields = [ai_reason]
    if not title:
        title = description.strip(" ，,；;。.")
        uncertain_fields.append("title")
    if len(title) > 255:
        title = title[:255]
        uncertain_fields.append("title")
    if used_custom_fallback:
        uncertain_fields.extend(("category", "subcategory"))
    for field_name, value in (
        ("year", year),
        ("category", category),
        ("subcategory", subcategory),
        ("level", level),
        ("personal_role", role),
    ):
        if not value:
            uncertain_fields.append(field_name)
    if base_score is None:
        uncertain_fields.append("base_score")
    if performance_score is None:
        uncertain_fields.append("performance_score")

    base_score = base_score or 0
    performance_score = performance_score or 0
    uncertain_fields = list(dict.fromkeys(uncertain_fields))
    base_confidence = (
        0.45 if used_custom_fallback else (0.9 if rule else 0.4)
    )
    return AchievementDraft(
        year=year,
        title=title,
        category=category,
        subcategory=subcategory,
        claim_nature=(
            ClaimNature.process
            if any(word in description for word in PROCESS_STAGE_KEYWORDS)
            else ClaimNature.result
        ),
        date_range=f"{year}年" if year else "",
        level=level,
        personal_role=role,
        current_stage=_current_stage(description),
        base_score=base_score,
        performance_score=performance_score,
        claimed_score=base_score + performance_score,
        notes="",
        confidence=_calibrated_confidence(
            base_confidence,
            uncertain_fields,
        ),
        uncertain_fields=uncertain_fields,
    )


def _ai_prompt(description: str, rules: Sequence[Any]) -> list[dict[str, str]]:
    schema = AchievementDraft.model_json_schema()
    rule_options = [_rule_payload(rule) for rule in rules]
    return [
        {
            "role": "system",
            "content": (
                "Extract one achievement draft as strict JSON. Use exactly the "
                "provided schema. category and subcategory must be one exact pair "
                "from active_rules. level must be empty or one allowed enum value. "
                "All scores must be non-negative and claimed_score must equal "
                "base_score + performance_score. Mark uncertain fields instead of "
                "inventing facts.\n"
                f"schema={json.dumps(schema, ensure_ascii=False)}\n"
                f"active_rules={json.dumps(rule_options, ensure_ascii=False)}"
            ),
        },
        {"role": "user", "content": description},
    ]


def _validated_ai_draft(
    content: str,
    rules: Sequence[Any],
    description: str,
) -> AchievementDraft:
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("AI draft must be a JSON object")
    draft = AchievementDraft.model_validate(payload)
    selected_rule = next(
        (
            rule
            for rule in rules
            if (
                str(_value(rule, "category")),
                str(_value(rule, "subcategory")),
            )
            == (draft.category, draft.subcategory)
        ),
        None,
    )
    if selected_rule is None:
        raise ValueError("AI draft selected an unknown rule")

    evidence_rule, evidence_is_custom_fallback = _match_rule(
        description,
        rules,
    )
    evidence_pair = (
        (
            str(_value(evidence_rule, "category")),
            str(_value(evidence_rule, "subcategory")),
        )
        if evidence_rule is not None
        else ("", "")
    )
    ai_pair = (draft.category, draft.subcategory)
    classification_is_supported = (
        evidence_rule is not None
        and not evidence_is_custom_fallback
        and evidence_pair == ai_pair
    )
    if not classification_is_supported:
        selected_rule = evidence_rule

    verified_level = _extract_level(description)
    uncertain_fields = [
        field_name
        for field_name in draft.uncertain_fields
        if not field_name.startswith("ai_")
    ]
    if not classification_is_supported:
        uncertain_fields.extend(("category", "subcategory"))
    if draft.level != verified_level:
        uncertain_fields.append("level")

    base_score = (
        _score_from_rule_text(
            str(_value(selected_rule, "base_rule")),
            description,
        )
        if selected_rule is not None
        else None
    )
    level_rule_field = LEVEL_RULE_FIELDS.get(verified_level, "")
    performance_score = (
        _score_from_rule_text(
            str(_value(selected_rule, level_rule_field)),
            description,
        )
        if selected_rule is not None and level_rule_field
        else None
    )
    if base_score is None:
        uncertain_fields.append("base_score")
    if performance_score is None:
        uncertain_fields.append("performance_score")
    uncertain_fields = list(dict.fromkeys(uncertain_fields))
    if classification_is_supported:
        confidence_base = 0.9
    elif evidence_is_custom_fallback:
        confidence_base = 0.45
    else:
        confidence_base = 0.55 if evidence_rule is not None else 0.4

    normalized = draft.model_dump()
    normalized.update(
        {
            "category": evidence_pair[0] if not classification_is_supported else draft.category,
            "subcategory": (
                evidence_pair[1]
                if not classification_is_supported
                else draft.subcategory
            ),
            "level": verified_level,
            "base_score": base_score or 0,
            "performance_score": performance_score or 0,
            "claimed_score": (base_score or 0) + (performance_score or 0),
            "confidence": _calibrated_confidence(
                confidence_base,
                uncertain_fields,
            ),
            "uncertain_fields": uncertain_fields,
        }
    )
    return AchievementDraft.model_validate(normalized)


def _timeout_for_config(integration_config: Any) -> httpx.Timeout:
    try:
        seconds = float(integration_config.ai_timeout_seconds)
    except (AttributeError, TypeError, ValueError, OverflowError):
        seconds = 30.0
    if not math.isfinite(seconds):
        seconds = 30.0
    seconds = min(120.0, max(5.0, seconds))
    return httpx.Timeout(seconds)


def _parse_with_ai(
    description: str,
    rules: Sequence[Any],
    integration_config: Any,
    client: Any | None,
) -> AchievementDraft:
    request_payload = {
        "model": integration_config.ai_model,
        "messages": _ai_prompt(description, rules),
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {integration_config.ai_api_key}",
        "Content-Type": "application/json",
    }
    url = (
        f"{integration_config.ai_base_url.rstrip('/')}/chat/completions"
    )
    owns_client = client is None
    http_client = client or httpx.Client()
    try:
        response = http_client.post(
            url,
            headers=headers,
            json=request_payload,
            timeout=_timeout_for_config(integration_config),
        )
        response.raise_for_status()
        response_payload = response.json()
        content = response_payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("AI response content must be JSON text")
        return _validated_ai_draft(content, rules, description)
    finally:
        if owns_client:
            http_client.close()


def parse_achievement_draft(
    description: str,
    active_rules: Sequence[Any],
    *,
    integration_config: Any | None = None,
    client: Any | None = None,
) -> AchievementDraft:
    if not isinstance(description, str):
        raise TypeError("description must be a string")
    description = description.strip()
    if not 1 <= len(description) <= 2000:
        raise ValueError("description must contain 1 to 2000 characters")

    rules = _active_rules(active_rules)
    integration_config = (
        integration_config
        if integration_config is not None
        else config.get_personal_integration_config()
    )
    ai_values = (
        getattr(integration_config, "ai_api_key", ""),
        getattr(integration_config, "ai_base_url", ""),
        getattr(integration_config, "ai_model", ""),
    )
    if not getattr(integration_config, "ai_ready", False) or not all(ai_values):
        return _deterministic_parse(
            description,
            rules,
            ai_reason="ai_not_configured",
        )

    try:
        return _parse_with_ai(
            description,
            rules,
            integration_config,
            client,
        )
    except httpx.TimeoutException:
        return _deterministic_parse(
            description,
            rules,
            ai_reason="ai_timeout",
        )
    except httpx.RequestError:
        return _deterministic_parse(
            description,
            rules,
            ai_reason="ai_network_error",
        )
    except (
        httpx.HTTPError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        IndexError,
    ):
        return _deterministic_parse(
            description,
            rules,
            ai_reason="ai_invalid_response",
        )


parse = parse_achievement_draft
