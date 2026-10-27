"""SQLAlchemy 2 async models. JSON columns hold the Pydantic payloads verbatim."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    ioc_id: Mapped[str] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    namespace: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)

    ioc_set: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    graph: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    naive_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    verification: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    actions: Mapped[list[ActionRow]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="ActionRow.seq"
    )
    events: Mapped[list[EventRow]] = relationship(
        back_populates="incident", cascade="all, delete-orphan", order_by="EventRow.seq"
    )


class ActionRow(Base):
    __tablename__ = "action_records"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    action_id: Mapped[str] = mapped_column(String(300))
    data: Mapped[dict[str, Any]] = mapped_column(JSON)

    incident: Mapped[IncidentRow] = relationship(back_populates="actions")


class EventRow(Base):
    """Append-only incident event stream; the SSE endpoint tails this by seq."""

    __tablename__ = "events"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"))
    kind: Mapped[str] = mapped_column(String(40))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    message: Mapped[str] = mapped_column(Text, default="")

    incident: Mapped[IncidentRow] = relationship(back_populates="events")


class ArtifactRow(Base):
    """Durable metadata context shared by API workers and child pipeline jobs."""

    __tablename__ = "incident_artifacts"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON)


class ActionLeaseRow(Base):
    """A renewable coordination record; action evidence remains append-only elsewhere."""

    __tablename__ = "action_leases"
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), primary_key=True)
    action_id: Mapped[str] = mapped_column(String(300), primary_key=True)
    owner: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
