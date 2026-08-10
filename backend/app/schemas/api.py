from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Point(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ZoneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    coordinates: list[Point] = Field(min_length=3)
    zone_type: Literal["rectangle", "polygon"] = "polygon"
    colour: str = "#22d3ee"
    enabled: bool = True
    relay_ids: list[int] = []
    auto_control_enabled: bool = True

    @field_validator("colour")
    @classmethod
    def valid_colour(cls, value: str) -> str:
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("colour must be a #RRGGBB value")
        int(value[1:], 16)
        return value


class ZoneUpdate(ZoneCreate):
    pass


class ZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    coordinates: list[Point]
    zone_type: str
    colour: str
    enabled: bool
    relay_ids: list[int] = []
    auto_control_enabled: bool = True


class CameraSelect(BaseModel):
    index: int = Field(ge=0, le=20)
    width: int = Field(default=1280)
    height: int = Field(default=720)

    @field_validator("width")
    @classmethod
    def width_supported(cls, value: int) -> int:
        if value not in (640, 1280):
            raise ValueError("width must be 640 or 1280")
        return value

    @field_validator("height")
    @classmethod
    def height_supported(cls, value: int) -> int:
        if value not in (480, 720):
            raise ValueError("height must be 480 or 720")
        return value


class DetectionSettings(BaseModel):
    confidence: float = Field(ge=0.1, le=0.95)
    inference_interval_ms: int = Field(ge=20, le=2000)


class ManualOverride(BaseModel):
    state: bool
    # When omitted, ON yields to vacancy after the deactivation delay and
    # OFF yields to occupancy after the activation delay.
    duration_seconds: float | None = Field(default=None, ge=0, le=86400)


class RelayTest(BaseModel):
    relay_id: int = Field(ge=1)
    duration_seconds: float = Field(default=1, ge=0.1, le=10)


class SystemSettingsUpdate(BaseModel):
    mode: Literal["automatic", "manual", "hybrid"] | None = None
    activation_delay_seconds: float | None = Field(default=None, ge=0, le=120)
    deactivation_delay_seconds: float | None = Field(default=None, ge=0, le=600)
    energy_tariff_per_kwh: float | None = Field(default=None, ge=0)
    esp32_base_url: str | None = None
