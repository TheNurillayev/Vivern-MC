from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.app.core.config import settings

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

from sqlalchemy import text

async def init_db():
    # Import all models to ensure they are registered with Base.metadata
    import backend.app.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe column migrations for orders table
        for col, col_type in [("custom_wishes_start_seconds", "FLOAT"), ("custom_call_ending_seconds", "FLOAT")]:
            try:
                await conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col} {col_type}"))
            except Exception:
                pass
    await seed_default_library_assets()

async def seed_default_library_assets():
    from backend.app.models.library_asset import LibraryAsset
    from backend.app.services.audio.validator import validate_audio_file
    from sqlalchemy import select, func

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(LibraryAsset.id)))
        count = result.scalar_one()
        if count == 0:
            lib_dir = settings.storage_path / "library"
            defaults = [
                ("number_call", "Number & Call (starter).m4a", "number_call_v11_0f3022e4.m4a"),
                ("starter", "Kiss the Rain.mp3", "starter_v11_ba3471ac.mp3"),
                ("call_ending", "Kiss the Rain.mp3 (Ending)", "call_ending_v11_f4ab917e.mp3"),
                ("wishes", "Wishes Music.mp3", "wishes_v1_ef68ec30.mp3"),
            ]
            for category, title, filename in defaults:
                file_path = lib_dir / filename
                if file_path.exists():
                    try:
                        meta = validate_audio_file(str(file_path))
                        dur = meta.get("duration_seconds", 60.0)
                        fmt = meta.get("format", "mp3")
                        size = meta.get("file_size_bytes", file_path.stat().st_size)
                    except Exception:
                        dur, fmt, size = 60.0, "mp3", file_path.stat().st_size
                    asset = LibraryAsset(
                        category=category,
                        title=title,
                        filename=filename,
                        storage_path=str(file_path),
                        duration_seconds=dur,
                        format=fmt,
                        file_size_bytes=size,
                        is_active=True,
                        version=1,
                        uploaded_by="8449563084"
                    )
                    session.add(asset)
            await session.commit()
