"""Platform multi-tenant models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    memberships: Mapped[list["Membership"]] = relationship(
        "Membership",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    broker_accounts: Mapped[list["BrokerAccount"]] = relationship(
        "BrokerAccount",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_view: Mapped[str] = mapped_column(String(20), default="investor", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    membership_status: Mapped[str] = mapped_column(String(20), default="inactive", nullable=False)
    membership_plan: Mapped[str | None] = mapped_column(String(40), nullable=True)
    membership_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    membership_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    membership_source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    membership_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")
    events: Mapped[list["MembershipEvent"]] = relationship(
        "MembershipEvent", back_populates="membership", cascade="all, delete-orphan"
    )


class MembershipEvent(Base):
    __tablename__ = "membership_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    membership_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("memberships.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    old_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    membership: Mapped["Membership"] = relationship("Membership", back_populates="events")


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", name="uq_broker_accounts_tenant_account"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(String(100), nullable=False)
    account_name: Mapped[str] = mapped_column(String(100), nullable=False)
    adapter: Mapped[str] = mapped_column(String(30), default="paper", nullable=False)
    trade_mode: Mapped[str] = mapped_column(String(20), default="paper", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_trade: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_sync_positions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="broker_accounts")
    owner: Mapped["User"] = relationship("User", back_populates="broker_accounts")
