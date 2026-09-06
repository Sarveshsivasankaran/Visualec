from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Visualec"
    app_env: str = "development"
    database_url: str = "sqlite:///./visualec.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    camera_index: int = 0
    camera_width: int = 1280
    camera_height: int = 720
    camera_fps: int = 24
    auto_start_camera: bool = True
    detection_model: str = "visualec-pico.espdl"
    detection_input_size: int = 288
    detection_confidence: float = 0.45
    inference_interval_ms: int = 20
    activation_delay_seconds: float = 1.0
    deactivation_delay_seconds: float = 10.0
    camera_loss_safety_timeout: float = 30.0
    camera_loss_action: str = "off"
    esp32_base_url: str = "http://visualec-esp32-s3.local"
    esp32_timeout_seconds: float = 3.0
    relay_retries: int = 2
    energy_tariff_per_kwh: float = 8.0
    edge_device_token: str = "change-this-edge-token"
    edge_expected_model_sha256: str = ""
    edge_input_width: int = 288
    edge_input_height: int = 160
    edge_high_motion_fps: float = 8.0
    edge_medium_motion_fps: float = 4.0
    edge_low_motion_fps: float = 1.0
    edge_mandatory_refresh_seconds: float = 1.0
    edge_inference_timeout_seconds: float = 1.0
    edge_occupancy_heartbeat_seconds: float = 0.5
    edge_motion_pixel_threshold: int = 20
    edge_motion_high_threshold: float = 0.06
    edge_motion_medium_threshold: float = 0.015

    @property
    def allowed_origins(self) -> list[str]:
        return [value.strip() for value in self.cors_origins.split(",") if value.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
