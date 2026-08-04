from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Zone(Base):
    __tablename__ = "zones"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    coordinates: Mapped[list] = mapped_column(JSON)
    zone_type: Mapped[str] = mapped_column(String(20), default="polygon")
    colour: Mapped[str] = mapped_column(String(20), default="#22d3ee")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    mappings: Mapped[list["ZoneRelayMapping"]] = relationship(cascade="all, delete-orphan", back_populates="zone")


class Relay(Base):
    __tablename__ = "relays"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    gpio_pin: Mapped[int] = mapped_column(Integer)
    state: Mapped[bool] = mapped_column(Boolean, default=False)
    active_low: Mapped[bool] = mapped_column(Boolean, default=True)
    appliance_type: Mapped[str] = mapped_column(String(30), default="prototype")
    rated_wattage: Mapped[float] = mapped_column(Float, default=9.0)
    esp32_device_id: Mapped[str] = mapped_column(String(100), default="visualec-esp32-s3")
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    mappings: Mapped[list["ZoneRelayMapping"]] = relationship(cascade="all, delete-orphan", back_populates="relay")


class ZoneRelayMapping(Base):
    __tablename__ = "zone_relay_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id", ondelete="CASCADE"))
    relay_id: Mapped[int] = mapped_column(ForeignKey("relays.id", ondelete="CASCADE"))
    auto_control_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    zone: Mapped[Zone] = relationship(back_populates="mappings")
    relay: Mapped[Relay] = relationship(back_populates="mappings")


class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    people_count: Mapped[int] = mapped_column(Integer)
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tracking_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class OccupancyEvent(Base):
    __tablename__ = "occupancy_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    zone_id: Mapped[int] = mapped_column(ForeignKey("zones.id"))
    previous_state: Mapped[bool] = mapped_column(Boolean)
    new_state: Mapped[bool] = mapped_column(Boolean)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RelayEvent(Base):
    __tablename__ = "relay_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    relay_id: Mapped[int] = mapped_column(ForeignKey("relays.id"))
    previous_state: Mapped[bool] = mapped_column(Boolean)
    new_state: Mapped[bool] = mapped_column(Boolean)
    source: Mapped[str] = mapped_column(String(30))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    response_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)


class EnergyRecord(Base):
    __tablename__ = "energy_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    relay_id: Mapped[int] = mapped_column(ForeignKey("relays.id"))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("zones.id"), nullable=True)
    power_watts: Mapped[float] = mapped_column(Float)
    active_duration: Mapped[float] = mapped_column(Float)
    energy_kwh: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
