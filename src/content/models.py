"""
Content pipeline data models.

State machine:
  raw → draft → pending_review → approved → published
                      └──────────→ rejected → draft (re-edit)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ContentStatus(str, Enum):
    RAW = "raw"                         # fetched but not yet processed
    DRAFT = "draft"                     # AI-generated, not yet reviewed
    PENDING_REVIEW = "pending_review"   # in the editorial queue
    APPROVED = "approved"               # approved, ready to publish
    PUBLISHED = "published"             # posted to a platform
    REJECTED = "rejected"               # rejected, needs rework
    ARCHIVED = "archived"               # no longer active


class ContentType(str, Enum):
    NEWS_SUMMARY = "news_summary"           # Summarized news article
    INSTITUTION_EXPLAINER = "institution_explainer"
    FIGURE_PROFILE = "figure_profile"
    TIMELINE = "timeline"
    CONCEPT_EXPLAINER = "concept_explainer"
    CAROUSEL_THREAD = "carousel_thread"     # Instagram carousel copy
    X_THREAD = "x_thread"                  # X/Twitter thread


class Platform(str, Enum):
    INSTAGRAM = "instagram"
    X = "x"
    THREADS = "threads"
    NEWSLETTER = "newsletter"
    WEB = "web"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class ReviewNote(BaseModel):
    reviewer: str
    note: str
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    action: str = ""  # approve | reject | edit | flag


class PublishRecord(BaseModel):
    platform: Platform
    published_at: dt.datetime
    url: Optional[str] = None
    post_id: Optional[str] = None
    metrics: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Core content draft model
# ---------------------------------------------------------------------------


class ContentDraft(BaseModel):
    """A single piece of content at any stage of the pipeline."""

    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    content_type: ContentType
    status: ContentStatus = ContentStatus.DRAFT

    # Content
    title: str
    body: str                           # main generated text
    formatted: Optional[str] = None    # formatter output (carousel / thread)
    language: str = "pt-BR"

    # Source tracing
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    source_article_id: Optional[str] = None  # FeedArticle.id
    related_entity_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    # AI metadata
    ai_model: Optional[str] = None
    ai_provider: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0

    # Timestamps
    created_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at: dt.datetime = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    reviewed_at: Optional[dt.datetime] = None
    published_at: Optional[dt.datetime] = None

    # Editorial
    review_notes: list[ReviewNote] = Field(default_factory=list)
    publish_records: list[PublishRecord] = Field(default_factory=list)
    flagged: bool = False
    flag_reason: Optional[str] = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:12]

    @property
    def word_count(self) -> int:
        return len(self.body.split())

    @field_validator("status", mode="before")
    @classmethod
    def coerce_status(cls, v: object) -> ContentStatus:
        if isinstance(v, str):
            return ContentStatus(v)
        return v  # type: ignore[return-value]

    def touch(self) -> None:
        self.updated_at = dt.datetime.now(dt.timezone.utc)

    def transition_to(self, new_status: ContentStatus) -> None:
        """Apply a state transition with validation."""
        allowed: dict[ContentStatus, set[ContentStatus]] = {
            ContentStatus.RAW: {ContentStatus.DRAFT},
            ContentStatus.DRAFT: {ContentStatus.PENDING_REVIEW, ContentStatus.ARCHIVED},
            ContentStatus.PENDING_REVIEW: {
                ContentStatus.APPROVED,
                ContentStatus.REJECTED,
                ContentStatus.DRAFT,
            },
            ContentStatus.APPROVED: {ContentStatus.PUBLISHED, ContentStatus.DRAFT},
            ContentStatus.PUBLISHED: {ContentStatus.ARCHIVED},
            ContentStatus.REJECTED: {ContentStatus.DRAFT, ContentStatus.ARCHIVED},
            ContentStatus.ARCHIVED: set(),
        }
        if new_status not in allowed[self.status]:
            raise ValueError(
                f"Invalid transition: {self.status.value} → {new_status.value}. "
                f"Allowed: {[s.value for s in allowed[self.status]]}"
            )
        self.status = new_status
        self.touch()

    def add_review_note(self, reviewer: str, note: str, action: str = "") -> None:
        self.review_notes.append(
            ReviewNote(reviewer=reviewer, note=note, action=action)
        )
        self.reviewed_at = dt.datetime.now(dt.timezone.utc)
        self.touch()

    def approve(self, reviewer: str, note: str = "") -> None:
        self.transition_to(ContentStatus.APPROVED)
        self.add_review_note(reviewer, note or "Aprovado.", action="approve")

    def reject(self, reviewer: str, note: str) -> None:
        self.transition_to(ContentStatus.REJECTED)
        self.add_review_note(reviewer, note, action="reject")

    def mark_published(self, platform: Platform, url: str = "", post_id: str = "") -> None:
        self.transition_to(ContentStatus.PUBLISHED)
        self.published_at = dt.datetime.now(dt.timezone.utc)
        self.publish_records.append(
            PublishRecord(
                platform=platform,
                published_at=self.published_at,
                url=url or None,
                post_id=post_id or None,
            )
        )
        self.touch()

    def to_dict(self) -> dict:
        return self.model_dump(mode="json")

    @classmethod
    def from_dict(cls, data: dict) -> "ContentDraft":
        return cls.model_validate(data)
