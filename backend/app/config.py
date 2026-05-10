from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        env_path = parent / ".env"
        if env_path.exists():
            return env_path
    raise FileNotFoundError(".env file not found")

ENV_FILE = find_env_file(Path(__file__).resolve())

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str

    # LangSmith
    langsmith_api_key: str = ""
    langsmith_project: str = "rag-mvp-stage1"
    langsmith_tracing: str = "false"

    # Server
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    # Storage
    chroma_persist_dir: str = "./data/chroma"
    sqlite_path: str = "./data/app.db"
    upload_dir: str = "./data/uploads"

    # Models
    gen_model: str = "gpt-4o-mini"
    embed_model: str = "text-embedding-3-small"

    # Retrieval
    semantic_top_k: int = 10

    # Chunking
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64

    # Limits
    max_file_size_mb: int = 50
    max_pdf_pages: int = 500
    max_documents: int = 20
    chat_history_turns: int = 6


settings = Settings()
