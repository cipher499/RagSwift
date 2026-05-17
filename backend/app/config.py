from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def find_env_file(start: Path) -> Path:
    for parent in [start] + list(start.parents):
        env_path = parent / ".env"
        if env_path.exists():
            return env_path
    raise FileNotFoundError(".env file not found")

ENV_FILE = find_env_file(Path(__file__).resolve())

_REPO_ROOT = Path(__file__).resolve().parents[2]  # backend/app/config.py → repo root

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
    chroma_persist_dir: str = str(_REPO_ROOT / "data/chroma")
    sqlite_path: str = str(_REPO_ROOT / "data/app.db")
    upload_dir: str = str(_REPO_ROOT / "data/uploads")

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
    max_pdf_pages: int = 1200
    max_documents: int = 20
    chat_history_turns: int = 6

    @model_validator(mode="after")
    def _resolve_storage_paths(self) -> "Settings":
        """Resolve relative storage paths against the .env file's directory.

        This makes CHROMA_PERSIST_DIR=./data/chroma in .env always resolve to
        an absolute path rooted at the repo root, regardless of which directory
        the process is launched from.
        """
        base = ENV_FILE.parent
        for field in ("chroma_persist_dir", "sqlite_path", "upload_dir"):
            val = Path(getattr(self, field))
            if not val.is_absolute():
                setattr(self, field, str(base / val))
        return self


settings = Settings()
