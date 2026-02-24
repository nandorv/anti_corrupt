from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Paths ──────────────────────────────────────────────────
    data_dir: Path = Path("data")
    output_dir: Path = Path("output")

    # ── AI / LLM ───────────────────────────────────────────────
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    default_llm_model: str = "claude-sonnet-4-20250514"
    max_tokens_per_summary: int = 1000

    # ── News Sources ───────────────────────────────────────────
    newsapi_key: str = ""

    # ── Publishing ─────────────────────────────────────────────
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    twitter_bearer_token: str = ""

    # ── App ────────────────────────────────────────────────────
    log_level: str = "INFO"

    @property
    def root_dir(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def prompts_dir(self) -> Path:
        return Path(__file__).parent / "prompts"

    @property
    def drafts_dir(self) -> Path:
        return self.output_dir / "drafts"

    @property
    def approved_dir(self) -> Path:
        return self.output_dir / "approved"

    @property
    def images_dir(self) -> Path:
        return self.output_dir / "images"

    @property
    def published_dir(self) -> Path:
        return self.output_dir / "published"

    def ensure_output_dirs(self) -> None:
        """Create output directories if they don't exist."""
        for d in [self.drafts_dir, self.approved_dir, self.images_dir, self.published_dir]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
