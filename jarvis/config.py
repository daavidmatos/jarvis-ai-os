from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./jarvis.db"
    redis_url: str = "redis://localhost:6379/0"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6"
    primary_provider: str = "openai"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"
    google_api_key: str | None = None
    google_model: str = "gemini-3.8-flash"
    tavily_api_key: str | None = None
    serper_api_key: str | None = None
    default_provider: str = "auto"
    autonomous_routing: bool = True
    allow_external_ai: bool = True
    allow_local_fallback: bool = False
    max_agent_steps: int = 5
    max_task_retries: int = 2
    max_plan_tasks: int = 8
    workspace_dir: str = "./workspace"
    enable_autonomy: bool = False
    allow_medium_risk_tools: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    @property
    def workspace_path(self) -> Path:
        p = Path(self.workspace_dir).resolve(); p.mkdir(parents=True, exist_ok=True); return p
settings = Settings()
