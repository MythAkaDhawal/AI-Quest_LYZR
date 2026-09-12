import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    LYZR_API_KEY: str = os.getenv("LYZR_API_KEY", "")
    GROQ_MODEL_ID: str = os.getenv("GROQ_MODEL_ID", "openai/gpt-oss-20b")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
