from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

class QARun(Base):
    __tablename__ = "qa_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    period_start: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(32), nullable=True)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    files_json: Mapped[str] = mapped_column(Text, default="{}")
    reconciliation_json: Mapped[str] = mapped_column(Text, default="[]")
    exceptions = relationship("QAException", back_populates="run", cascade="all, delete-orphan")

class QAException(Base):
    __tablename__ = "qa_exceptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("qa_runs.id"), index=True)
    rule_id: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), index=True)
    source: Mapped[str] = mapped_column(String(40))
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    affected_records: Mapped[int] = mapped_column(Integer, default=0)
    evidence_json: Mapped[str] = mapped_column(Text, default="{}")
    why_it_matters: Mapped[str] = mapped_column(Text)
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="Open")
    run = relationship("QARun", back_populates="exceptions")
