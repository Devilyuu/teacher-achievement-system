from pathlib import Path

from app.models import Achievement, ClaimNature


def missing_reasons(achievement: Achievement) -> list[str]:
    reasons: list[str] = []
    required_text = [
        achievement.category,
        achievement.subcategory,
        achievement.claim_nature,
        achievement.title,
    ]
    if not all(value and str(value).strip() for value in required_text):
        reasons.append("申报信息不完整")
    if achievement.claimed_score is None or achievement.claimed_score <= 0:
        reasons.append("申报积分未填写或不大于零")
    if (
        achievement.claim_nature == ClaimNature.process.value
        and not (achievement.current_stage or "").strip()
    ):
        reasons.append("过程性工作缺少进展说明")
    if not achievement.materials:
        reasons.append("未上传支撑材料")
    elif any(not Path(material.stored_path).is_file() for material in achievement.materials):
        reasons.append("材料文件不存在")
    return reasons
