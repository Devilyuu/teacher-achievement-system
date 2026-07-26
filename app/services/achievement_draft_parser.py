import json
import math
import re
from typing import Any, Sequence

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


AI_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)
LEVEL_VALUES = {option["value"] for option in LEVEL_OPTIONS}
LEVEL_RULE_FIELDS = {
    option["value"]: option["rule_field"]
    for option in LEVEL_OPTIONS
}


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
    base_score: float = Field(default=0, ge=0)
    performance_score: float = Field(default=0, ge=0)
    claimed_score: float = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=2000)
    confidence: float = Field(ge=0, le=1)
    uncertain_fields: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("level")
    @classmethod
    def validate_level(cls, value: str) -> str:
        if value and value not in LEVEL_VALUES:
            raise ValueError("level must be one of the configured level options")
        return value

    @model_validator(mode="after")
    def normalize_claimed_score(self) -> "AchievementDraft":
        expected_total = self.base_score + self.performance_score
        if not math.isclose(self.claimed_score, expected_total):
            self.claimed_score = expected_total
            self.uncertain_fields = list(dict.fromkeys(
                [*self.uncertain_fields, "claimed_score"]
            ))
        return self


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


def _bigrams(value: str) -> set[str]:
    return {value[index:index + 2] for index in range(len(value) - 1)}


def _match_rule(description: str, rules: Sequence[Any]) -> Any | None:
    normalized_description = _normalized_match_text(description)
    description_bigrams = _bigrams(normalized_description)
    ranked: list[tuple[int, Any]] = []
    for rule in rules:
        category = str(_value(rule, "category"))
        subcategory = str(_value(rule, "subcategory"))
        normalized_subcategory = _normalized_match_text(subcategory)
        score = len(description_bigrams & _bigrams(normalized_subcategory))
        if normalized_subcategory and normalized_subcategory in normalized_description:
            score += 20
        if category and category in description:
            score += 5
        if "指导学生" in description and "指导学生" in subcategory:
            score += 10
        ranked.append((score, rule))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 2:
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def _extract_year(description: str) -> int | None:
    match = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", description)
    return int(match.group(1)) if match else None


def _extract_level(description: str) -> str:
    if any(marker in description for marker in ("国家级", "全国", "国家")):
        return "国家级"
    if "省级" in description or re.search(r"[\u4e00-\u9fff]{2,8}省", description):
        return "省级"
    if "市级" in description or re.search(r"[\u4e00-\u9fff]{2,8}市", description):
        return "市级"
    if any(marker in description for marker in ("学院级", "学院")):
        return "学院级"
    if any(marker in description for marker in ("校级", "学校")):
        return "校级"
    return ""


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
        r"^(?:19|20)\d{2}年(?:度)?[，,；;：:\s]*",
        "",
        title,
    )
    title = re.sub(
        r"^我(?:是|作为|担任)(?:第一指导教师|第二指导教师|指导教师|负责人|"
        r"主持人|主持|成员)[，,；;：:\s]*",
        "",
        title,
    )
    title = re.sub(
        r"[，,；;。.\s]*(?:我(?:是|作为|担任)?)(?:第一指导教师|第二指导教师|"
        r"指导教师|负责人|主持人|主持|成员)[。.\s]*$",
        "",
        title,
    )
    return title.strip(" ，,；;。.")


def _current_stage(description: str) -> str:
    return next(
        (
            keyword
            for keyword in ("申报中", "在研", "执行中")
            if keyword in description
        ),
        "",
    )


def _single_number(rule_text: str) -> float | None:
    numbers = re.findall(r"(?<![\d.])\d+(?:\.\d+)?", rule_text)
    if len(numbers) != 1:
        return None
    return float(numbers[0])


def _award_score(rule_text: str, description: str) -> float | None:
    award_rank = next(
        (
            rank
            for label, rank in (
                ("一等奖", "一"),
                ("二等奖", "二"),
                ("三等奖", "三"),
                ("特等奖", "特"),
            )
            if label in description
        ),
        None,
    )
    if award_rank:
        match = re.search(
            rf"(?:国|省|市|校|院)?{award_rank}(?:等(?:奖)?)?\s*(\d+(?:\.\d+)?)",
            rule_text,
        )
        if match:
            return float(match.group(1))
        numbers = re.findall(r"(?<![\d.])\d+(?:\.\d+)?", rule_text)
        rank_index = {"一": 0, "二": 1, "三": 2}.get(award_rank)
        if rank_index is not None and len(numbers) == 3:
            return float(numbers[rank_index])
    return _single_number(rule_text)


def _deterministic_parse(description: str, rules: Sequence[Any]) -> AchievementDraft:
    year = _extract_year(description)
    level = _extract_level(description)
    role = _extract_role(description)
    rule = _match_rule(description, rules)
    category = str(_value(rule, "category")) if rule else ""
    subcategory = str(_value(rule, "subcategory")) if rule else ""
    base_score = _single_number(str(_value(rule, "base_rule"))) if rule else None
    level_rule = LEVEL_RULE_FIELDS.get(level, "")
    performance_score = (
        _award_score(str(_value(rule, level_rule)), description)
        if rule and level_rule
        else None
    )
    title = _clean_title(description)
    uncertain_fields = ["ai_unavailable"]
    if not title:
        title = description.strip(" ，,；;。.")
        uncertain_fields.append("title")
    if len(title) > 255:
        title = title[:255]
        uncertain_fields.append("title")
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
    return AchievementDraft(
        year=year,
        title=title,
        category=category,
        subcategory=subcategory,
        claim_nature=(
            ClaimNature.process
            if any(word in description for word in ("申报中", "在研", "执行中"))
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
        confidence=0.85 if rule else 0.35,
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
) -> AchievementDraft:
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("AI draft must be a JSON object")
    draft = AchievementDraft.model_validate(payload)
    allowed_pairs = {
        (str(_value(rule, "category")), str(_value(rule, "subcategory")))
        for rule in rules
    }
    if (draft.category, draft.subcategory) not in allowed_pairs:
        raise ValueError("AI draft selected an unknown rule")
    return draft


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
            timeout=AI_TIMEOUT,
        )
        response.raise_for_status()
        response_payload = response.json()
        content = response_payload["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("AI response content must be JSON text")
        return _validated_ai_draft(content, rules)
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
    fallback = _deterministic_parse(description, rules)
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
        return fallback

    try:
        return _parse_with_ai(
            description,
            rules,
            integration_config,
            client,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError, IndexError):
        return fallback


parse = parse_achievement_draft
