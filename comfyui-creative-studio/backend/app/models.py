"""ORM models. See docs/ARCHITECTURE.md for the schema diagram."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --- association tables ------------------------------------------------------

project_references = Table(
    "project_references",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("reference_id", ForeignKey("references.id", ondelete="CASCADE"), primary_key=True),
)

project_profiles = Table(
    "project_profiles",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("profile_id", ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
)

profile_workflows = Table(
    "profile_workflows",
    Base.metadata,
    Column("profile_id", ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("workflow_id", ForeignKey("workflows.id", ondelete="CASCADE"), primary_key=True),
)


# --- projects ----------------------------------------------------------------


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    client: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|archived
    template_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    cover_reference_id: Mapped[int | None] = mapped_column(
        ForeignKey("references.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    campaigns: Mapped[list[Campaign]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Campaign.id"
    )
    references: Mapped[list[Reference]] = relationship(
        secondary=project_references, back_populates="projects"
    )
    profiles: Mapped[list[Profile]] = relationship(
        secondary=project_profiles, back_populates="projects"
    )


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    project: Mapped[Project] = relationship(back_populates="campaigns")


class Activity(Base):
    __tablename__ = "activity"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# --- references --------------------------------------------------------------


class Reference(Base):
    __tablename__ = "references"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    mime: Mapped[str] = mapped_column(String(64))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    has_alpha: Mapped[bool] = mapped_column(Boolean, default=False)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    phash: Mapped[str] = mapped_column(String(32), default="")
    palette: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(32), default="style", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    projects: Mapped[list[Project]] = relationship(
        secondary=project_references, back_populates="references"
    )


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    items: Mapped[list[CollectionItem]] = relationship(
        cascade="all, delete-orphan", order_by="CollectionItem.position"
    )


class CollectionItem(Base):
    __tablename__ = "collection_items"
    __table_args__ = (UniqueConstraint("collection_id", "reference_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("collections.id", ondelete="CASCADE"))
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    reference: Mapped[Reference] = relationship()


# --- profiles ----------------------------------------------------------------


class Profile(Base):
    """Character or Product profile. Reusable across projects."""

    __tablename__ = "profiles"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)  # character|product
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")  # product category
    # character: hair, eyes, skin, age_range...; product: shape, material, finish, stones...
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    preserve_details: Mapped[list[str]] = mapped_column(JSON, default=list)
    generation_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    images: Mapped[list[ProfileImage]] = relationship(
        cascade="all, delete-orphan", order_by="ProfileImage.position"
    )
    workflows: Mapped[list[Workflow]] = relationship(secondary=profile_workflows)
    projects: Mapped[list[Project]] = relationship(
        secondary=project_profiles, back_populates="profiles"
    )


class ProfileImage(Base):
    __tablename__ = "profile_images"
    __table_args__ = (UniqueConstraint("profile_id", "reference_id", "role"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    reference_id: Mapped[int] = mapped_column(ForeignKey("references.id", ondelete="CASCADE"))
    # primary|face|detail|angle|material|other
    role: Mapped[str] = mapped_column(String(32), default="primary")
    position: Mapped[int] = mapped_column(Integer, default=0)
    reference: Mapped[Reference] = relationship()


# --- workflows -----------------------------------------------------------------


class Workflow(Base):
    __tablename__ = "workflows"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(48), default="product_photography")
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    # Format of the file the user imported: "api" | "ui"
    source_format: Mapped[str] = mapped_column(String(8))
    original_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    # Executable API-format prompt; None if a UI workflow has not been converted yet.
    api_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    api_source: Mapped[str | None] = mapped_column(String(16), nullable=True)  # imported|converted
    conversion_warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    parameters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    node_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    models: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# --- consistency ---------------------------------------------------------------


class ConsistencyConfig(Base):
    __tablename__ = "consistency_configs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    workflow_id: Mapped[int] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    # Detected conditioning methods, e.g. ["ipadapter", "controlnet", "inpaint"]
    methods: Mapped[list[str]] = mapped_column(JSON, default=list)
    # image parameter key -> reference_id
    image_bindings: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    # parameter key -> value (weights, strengths, prompts, ...)
    values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    use_profile_prompt: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    workflow: Mapped[Workflow] = relationship()
    profile: Mapped[Profile | None] = relationship()


# --- jobs & outputs --------------------------------------------------------------


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True
    )
    workflow_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )
    consistency_config_id: Mapped[int | None] = mapped_column(
        ForeignKey("consistency_configs.id", ondelete="SET NULL"), nullable=True
    )
    batch_id: Mapped[str] = mapped_column(String(36), index=True)
    variation_index: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200), default="")
    # pending -> submitted -> running -> completed | failed | interrupted | cancelled | lost
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    server_url: Mapped[str] = mapped_column(String(255), default="")
    comfy_prompt_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    parameter_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    image_bindings: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    submitted_prompt: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status_messages: Mapped[list[Any]] = mapped_column(JSON, default=list)
    execution_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    outputs: Mapped[list[Output]] = relationship(
        back_populates="job", cascade="all, delete-orphan", order_by="Output.id"
    )


class Output(Base):
    __tablename__ = "outputs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    node_id: Mapped[str] = mapped_column(String(32), default="")
    comfy_filename: Mapped[str] = mapped_column(String(255), default="")
    comfy_subfolder: Mapped[str] = mapped_column(String(255), default="")
    comfy_type: Mapped[str] = mapped_column(String(16), default="output")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)  # final selection
    rating: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(Text, default="")
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # reproducibility record
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[Job] = relationship(back_populates="outputs")


class AppSetting(Base):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
