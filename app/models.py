from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StrEnum(str, Enum):
    pass


class Role(StrEnum):
    teacher = "teacher"
    admin = "admin"


class ClaimNature(StrEnum):
    process = "过程性工作"
    result = "成果性工作"


class AchievementStatus(StrEnum):
    draft = "草稿"
    needs_info = "待完善"
    ready = "可申报"
    exported = "已纳入导出"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(80))
    department: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20), default=Role.teacher.value)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PerformanceRule(Base):
    __tablename__ = "performance_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(120), index=True)
    subcategory: Mapped[str] = mapped_column(String(255), index=True)
    base_rule: Mapped[str] = mapped_column(Text, default="")
    national_rule: Mapped[str] = mapped_column(Text, default="")
    provincial_rule: Mapped[str] = mapped_column(Text, default="")
    city_rule: Mapped[str] = mapped_column(Text, default="")
    school_rule: Mapped[str] = mapped_column(Text, default="")
    college_rule: Mapped[str] = mapped_column(Text, default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    is_team: Mapped[bool] = mapped_column(Boolean, default=False)
    is_department_assigned: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Achievement(Base):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    category: Mapped[str] = mapped_column(String(120))
    subcategory: Mapped[str] = mapped_column(String(255))
    claim_nature: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(255))
    date_range: Mapped[str] = mapped_column(String(120), default="")
    level: Mapped[str] = mapped_column(String(80), default="")
    personal_role: Mapped[str] = mapped_column(String(80), default="")
    current_stage: Mapped[str] = mapped_column(Text, default="")
    base_score: Mapped[float] = mapped_column(Float, default=0)
    performance_score: Mapped[float] = mapped_column(Float, default=0)
    claimed_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default=AchievementStatus.draft.value)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    materials = relationship(
        "Material",
        back_populates="achievement",
        cascade="all, delete-orphan",
    )
    feishu_sync_record = relationship(
        "FeishuSyncRecord",
        back_populates="achievement",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id"), index=True)
    material_no: Mapped[str] = mapped_column(String(40), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(255), default="")
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    file_ext: Mapped[str] = mapped_column(String(20))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    achievement = relationship("Achievement", back_populates="materials")


class FeishuSyncRecord(Base):
    __tablename__ = "feishu_sync_records"
    __table_args__ = (
        CheckConstraint(
            "sync_status IN ('pending', 'synced', 'failed', 'conflict')",
            name="ck_feishu_sync_records_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    achievement_id: Mapped[int] = mapped_column(
        ForeignKey("achievements.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    feishu_record_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    sync_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )
    last_error: Mapped[str] = mapped_column(
        Text,
        default="",
        server_default="",
    )
    payload_hash: Mapped[str] = mapped_column(
        String(64),
        default="",
        server_default="",
    )
    sync_claim_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    achievement = relationship(
        "Achievement",
        back_populates="feishu_sync_record",
    )


class AnnualSubmission(Base):
    __tablename__ = "annual_submissions"
    __table_args__ = (
        UniqueConstraint("user_id", "year", name="uq_annual_submissions_user_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(30), default="submitted")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class ExportRecord(Base):
    __tablename__ = "export_records"
    __table_args__ = (
        UniqueConstraint("user_id", "year", name="uq_export_records_user_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(500))
    achievement_count: Mapped[int] = mapped_column(Integer, default=0)
    material_count: Mapped[int] = mapped_column(Integer, default=0)
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class TrialFeedback(Base):
    __tablename__ = "trial_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    issue_type: Mapped[str] = mapped_column(String(40), default="其他")
    current_page: Mapped[str] = mapped_column(String(255), default="")
    related_title: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="待处理")
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user = relationship("User")
