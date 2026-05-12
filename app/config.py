from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./ai_tracker.db"

    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    github_token: str = ""
    x_bearer_token: str = ""

    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.moonshot.ai/v1"
    kimi_model: str = "kimi-k2.6"

    retention_days: int = 180

    relevance_keywords: str = (
        "llm,large language model,gpt,claude,gemini,deep learning,"
        "transformer,agentic,ai agent,rag,fine-tuning,diffusion,multimodal"
    )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def keywords_list(self) -> list[str]:
        return [k.strip().lower() for k in self.relevance_keywords.split(",") if k.strip()]


settings = Settings()
