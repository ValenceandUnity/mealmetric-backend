from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from mealmetric.db.base import Base


class AuthFailureTracker(Base):
    __tablename__ = "auth_failure_trackers"

    subject: Mapped[str] = mapped_column(String(320), primary_key=True)
    failure_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    window_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    alert_emitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
