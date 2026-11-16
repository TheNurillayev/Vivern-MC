import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.database import init_db
from backend.app.core.config import settings
from backend.app.api.health import router as health_router
from backend.app.api.auth import router as auth_router
from backend.app.api.admin import router as admin_router
from backend.app.api.orders import router as orders_router
from backend.app.api.payments import router as payments_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("vivern")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Vivern MC backend...")
    await init_db()
    # Ensure storage paths
    settings.storage_path
    logger.info("Database and storage initialized successfully.")
    yield
    logger.info("Shutting down Vivern MC backend...")

app = FastAPI(
    title="Vivern MC API",
    description="Automated Birthday Audio Production Service API",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(orders_router)
app.include_router(payments_router)

# Mount static files and web frontend
web_dir = Path(__file__).resolve().parent.parent.parent / "web"
web_static_dir = web_dir / "static"
if web_static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(web_static_dir)), name="static")

# Mount web root (for index.html, admin.html)
if web_dir.exists():
    app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
