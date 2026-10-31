"""PyCharm entry point for running the API outside Docker."""
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent

# The editor run configuration uses an independent SQLite file, so it works
# even when Docker is stopped or its database credentials differ.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'document_intelligence.local.db'}")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("STORAGE_PATH", str(PROJECT_ROOT / "storage" / "uploads"))

from app.main import app  # noqa: E402


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8001")))
