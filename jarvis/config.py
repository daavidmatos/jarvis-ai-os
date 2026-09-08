from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./jarvis.db"
    redis_url: str = "redis://localhost:6379/0"

    # Public server address. Required for OAuth callbacks and push webhooks.
    public_base_url: str = "http://localhost:8000"

    # OpenAI is the mandatory primary cognition layer.
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6"
    openai_image_model: str = "gpt-image-2"
    primary_provider: str = "openai"

    # Optional specialist providers. The router may delegate automatically.
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    google_api_key: str | None = None
    google_model: str = "gemini-3.8-flash"

    # Google Workspace OAuth. This is separate from the Gemini API key above.
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_token_path: str = "~/.config/jarvis/google_oauth.json"
    google_monitor_state_path: str = "~/.config/jarvis/google_monitor.json"
    gmail_pubsub_topic: str | None = None
    google_pubsub_webhook_secret: str | None = None

    # Google Ads uses the same OAuth identity plus a developer token/customer IDs.
    google_ads_developer_token: str | None = None
    google_ads_customer_id: str | None = None
    google_ads_login_customer_id: str | None = None
    google_ads_api_version: str = "v25"

    # Meta / Instagram Graph API.
    meta_graph_version: str = "v24.0"
    meta_access_token: str | None = None
    meta_instagram_user_id: str | None = None
    meta_app_secret: str | None = None
    meta_webhook_verify_token: str | None = None

    # Optional Fuel business API contract. The Lovable app can expose these endpoints later.
    fuel_api_base_url: str | None = None
    fuel_api_token: str | None = None
    fuel_webhook_secret: str | None = None

    # Optional dedicated search providers. OpenAI hosted web search remains available.
    tavily_api_key: str | None = None
    serper_api_key: str | None = None

    # One-time local credential store. Environment variables still override stored keys.
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
