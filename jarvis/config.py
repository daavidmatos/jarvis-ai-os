from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./jarvis.db"
    redis_url: str = "redis://localhost:6379/0"

    public_base_url: str = "http://localhost:8000"

    jarvis_access_password: str | None = None
    jarvis_session_secret: str | None = None
    jarvis_session_days: int = 30
    jarvis_login_max_attempts: int = 8
    jarvis_login_window_seconds: int = 900

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-sol"
    openai_image_model: str = "gpt-image-2"
    primary_provider: str = "openai"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    google_api_key: str | None = None
    # Temporary free core: use the stronger Flash model for judgment/tool routing.
    # Audio transcription remains on Flash-Lite below to keep short voice turns cheap/fast.
    google_model: str = "gemini-3.6-flash"

    google_tts_model: str = "gemini-3.1-flash-tts-preview"
    google_tts_voice: str = "Gacrux"
    google_stt_model: str = "gemini-3.5-flash-lite"
    voice_max_audio_bytes: int = 8_000_000

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_token_path: str = "~/.config/jarvis/google_oauth.json"
    google_monitor_state_path: str = "~/.config/jarvis/google_monitor.json"
    gmail_pubsub_topic: str | None = None
    google_pubsub_webhook_secret: str | None = None
    enable_google_monitoring: bool = True
    google_monitor_interval_seconds: int = 3600

    google_maps_api_key: str | None = None
    places_default_radius_m: int = 5000
    places_max_candidates: int = 5

    google_ads_developer_token: str | None = None
    google_ads_customer_id: str | None = None
    google_ads_login_customer_id: str | None = None
    google_ads_api_version: str = "v25"

    meta_graph_version: str = "v24.0"
    meta_access_token: str | None = None
    meta_instagram_user_id: str | None = None
    meta_app_secret: str | None = None
    meta_webhook_verify_token: str | None = None

    fuel_api_base_url: str | None = None
    fuel_api_token: str | None = None
    fuel_webhook_secret: str | None = None

    trello_api_key: str | None = None
    trello_token: str | None = None

    desktop_bridge_token: str | None = None
    desktop_frame_max_bytes: int = 3_000_000
    desktop_frame_retention: int = 2

    tavily_api_key: str | None = None
    serper_api_key: str | None = None

    # Real browser execution layer. Browserless Free can be used for testing.
    # The agent is only allowed to PREPARE commerce flows by default; final purchases
    # and bookings remain user-confirmed in the external service.
    browserless_api_token: str | None = None
    browserless_base_url: str = "https://production-sfo.browserless.io"
    browserless_ifood_profile: str | None = None
    browserless_default_timeout_ms: int = 90000
    browserless_max_steps: int = 24

    secrets_path: str = "~/.config/jarvis/secrets.json"

    autonomous_routing: bool = True
    allow_external_ai: bool = True
    allow_local_fallback: bool = False
    finalize_with_primary: bool = True
    max_agent_steps: int = 5
    max_task_retries: int = 2
    max_plan_tasks: int = 8

    workspace_dir: str = "./workspace"
    enable_autonomy: bool = True
    allow_medium_risk_tools: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def workspace_path(self) -> Path:
        p = Path(self.workspace_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def secrets_file(self) -> Path:
        return Path(self.secrets_path).expanduser().resolve()


settings = Settings()
