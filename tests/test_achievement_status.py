from app.models import Achievement, ClaimNature, Material
from app.services.achievement_status import calculate_status


def _complete_achievement() -> Achievement:
    achievement = Achievement(
        user_id=1,
        year=2026,
        category="其他有价值工作（自定义）",
        subcategory="自定义工作事项",
        claim_nature=ClaimNature.process.value,
        title="省级技能大赛裁判工作",
        current_stage="已完成裁判工作并提交总结",
        claimed_score=2,
    )
    achievement.materials = [
        Material(
            material_no="M001",
            display_name="证明材料",
            original_filename="proof.pdf",
            stored_path="/tmp/proof.pdf",
            file_ext=".pdf",
            file_size=128,
        )
    ]
    return achievement


def test_process_record_without_current_stage_is_needs_info():
    achievement = _complete_achievement()
    achievement.current_stage = ""

    assert calculate_status(achievement) == "待完善"


def test_record_missing_required_text_is_needs_info():
    field_names = ["category", "subcategory", "claim_nature", "title"]

    for field_name in field_names:
        achievement = _complete_achievement()
        setattr(achievement, field_name, "")

        assert calculate_status(achievement) == "待完善"


def test_record_without_positive_claimed_score_is_needs_info():
    for claimed_score in [None, 0, -1]:
        achievement = _complete_achievement()
        achievement.claimed_score = claimed_score

        assert calculate_status(achievement) == "待完善"


def test_record_without_materials_is_needs_info():
    achievement = _complete_achievement()
    achievement.materials = []

    assert calculate_status(achievement) == "待完善"


def test_complete_record_with_positive_score_and_material_is_ready():
    achievement = _complete_achievement()

    assert calculate_status(achievement) == "可申报"


def test_result_record_without_current_stage_can_be_ready():
    achievement = _complete_achievement()
    achievement.claim_nature = ClaimNature.result.value
    achievement.current_stage = ""

    assert calculate_status(achievement) == "可申报"
