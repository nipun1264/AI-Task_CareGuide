from contextlib import asynccontextmanager
from pathlib import Path
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Support both package execution (``uvicorn app.main:app``) and PyCharm's
# "Run current file" action (``python app/main.py``).
if __package__ in {None, ""}:
    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(project_root) / 'document_intelligence.local.db'}")
    os.environ.setdefault("STORAGE_PATH", str(Path(project_root) / "storage" / "uploads"))
    from app.api import router
    from app.database import Base, engine
else:
    from .api import router
    from .database import Base, engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Document Intelligence API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)
