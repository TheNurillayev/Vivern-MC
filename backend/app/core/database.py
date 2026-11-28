from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from backend.app.core.config import settings

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    settings.resolved_database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {}
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
import logging

logger = logging.getLogger("vivern-db")

async def init_db():
    # Import all models to ensure they are registered with Base.metadata
    import backend.app.models  # noqa
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Dynamic auto-migration for ALL tables and columns
        for table_name, table in Base.metadata.tables.items():
            try:
                res = await conn.execute(text(f"PRAGMA table_info({table_name})"))
                existing_cols = {row[1] for row in res.fetchall()}
                if not existing_cols:
                    continue
                for col in table.columns:
                    if col.name not in existing_cols:
                        col_type_str = str(col.type.compile(engine.dialect))
                        default_clause = ""
                        if col.default is not None and hasattr(col.default, 'arg'):
                            arg = col.default.arg
                            if isinstance(arg, bool):
                                default_clause = f" DEFAULT {1 if arg else 0}"
                            elif isinstance(arg, (int, float)):
                                default_clause = f" DEFAULT {arg}"
                            elif isinstance(arg, str):
                                default_clause = f" DEFAULT '{arg}'"
                        elif col.nullable:
                            default_clause = " DEFAULT NULL"

                        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {col.name} {col_type_str}{default_clause}"
                        try:
                            await conn.execute(text(alter_sql))
                            logger.info(f"Auto-migrated column: {table_name}.{col.name} ({col_type_str})")
                        except Exception as col_err:
                            logger.warning(f"Could not add column {table_name}.{col.name}: {col_err}")
            except Exception as tbl_err:
                logger.warning(f"Error checking table {table_name}: {tbl_err}")

        # Explicitly ensure users.updated_at exists
        try:
            await conn.execute(text("ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"))
        except Exception:
            pass

        # Backfill existing coin purchases into total_paid_som & coin_transactions
        try:
            pricing_map = {10: 5000, 30: 14000, 50: 22000, 100: 40000}
            users_with_coins = await conn.execute(text("SELECT id, coins, total_paid_som FROM users WHERE coins > 0"))
            for uid, c_val, p_val in users_with_coins.fetchall():
                if not p_val or p_val == 0:
                    est_som = pricing_map.get(c_val, c_val * 500)
                    await conn.execute(text(f"UPDATE users SET total_paid_som = {est_som} WHERE id = {uid}"))
                    tx_check = await conn.execute(text(f"SELECT COUNT(*) FROM coin_transactions WHERE user_id = {uid}"))
                    if tx_check.scalar() == 0:
                        import uuid, datetime
                        tx_id = str(uuid.uuid4())
                        now_str = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                        desc = f"To'lov cheki orqali ({c_val} Tanga)"
                        await conn.execute(text(
                            f"INSERT INTO coin_transactions (id, user_id, type, coins, amount_som, description, status, created_at) "
                            f"VALUES ('{tx_id}', {uid}, 'purchase', {c_val}, {est_som}, '{desc}', 'completed', '{now_str}')"
                        ))
        except Exception:
            pass

        # Unstick any pending orders that were waiting in payment_required
        try:
            await conn.execute(text("UPDATE orders SET status = 'queued' WHERE status = 'payment_required'"))
        except Exception:
            pass
    await seed_default_library_assets()

async def seed_default_library_assets():
    import shutil
    from backend.app.models.library_asset import LibraryAsset
    from backend.app.services.audio.validator import validate_audio_file
    from sqlalchemy import select, delete

    lib_dir = settings.storage_path / "library"
    lib_dir.mkdir(parents=True, exist_ok=True)

    # Sync bundled source tracks into storage_path/library if missing
    candidate_sources = [
        settings.BASE_DIR / "MC - Source",
        settings.BASE_DIR / "default_assets" / "library",
        settings.BASE_DIR / "storage" / "library",
    ]
    source_map = {
        "Kilaviatura (starter).m4a": "number_call_v11_0f3022e4.m4a",
        "Kiss the Rain.mp3": "starter_v11_ba3471ac.mp3",
        "Wishes Music.mp3": "wishes_v1_ef68ec30.mp3",
        "Wishes 2.mp3": "wishes_v2_wishes2.mp3",
        "Aşk Mühürü.mp3": "starter_v2_ask_muhuru.mp3",
    }
    for c_dir in candidate_sources:
        if c_dir.exists():
            for src_name, target_name in source_map.items():
                s_file = c_dir / src_name
                d_file = lib_dir / target_name
                if s_file.exists() and not d_file.exists():
                    try:
                        shutil.copy2(s_file, d_file)
                    except Exception:
                        pass

    # Ensure call_ending track exists
    ce_src = lib_dir / "starter_v11_ba3471ac.mp3"
    ce_dst = lib_dir / "call_ending_v11_f4ab917e.mp3"
    if ce_src.exists() and not ce_dst.exists():
        try:
            shutil.copy2(ce_src, ce_dst)
        except Exception:
            pass

    # Register/Update studio library tracks in DB
    defaults = [
        ("number_call", "Raqam terish va Qo'ng'iroq (15s)", "number_call_v11_0f3022e4.m4a", True, 11),
        ("starter", "Kiss the Rain (Asosiy fon)", "starter_v11_ba3471ac.mp3", True, 11),
        ("starter", "Aşk Mühürü (Romantik fon)", "starter_v2_ask_muhuru.mp3", False, 10),
        ("wishes", "Wishes 1 (Klassik tilaklar musiqasi)", "wishes_v1_ef68ec30.mp3", True, 11),
        ("wishes", "Wishes 2 (Hissiyotli ohang)", "wishes_v2_wishes2.mp3", False, 10),
        ("call_ending", "Kiss the Rain Outro", "call_ending_v11_f4ab917e.mp3", True, 11),
    ]

    async with AsyncSessionLocal() as session:
        # Remove dummy wav tracks (duration <= 3.0s or .wav)
        await session.execute(
            delete(LibraryAsset).where(
                (LibraryAsset.filename.like("%.wav")) | 
                (LibraryAsset.duration_seconds <= 3.1)
            )
        )
        await session.commit()

        for category, title, filename, is_active, version in defaults:
            file_path = lib_dir / filename
            if not file_path.exists():
                continue
            try:
                meta = validate_audio_file(str(file_path))
                dur = meta.get("duration_seconds", 60.0)
                fmt = meta.get("format", "mp3")
                size = meta.get("file_size_bytes", file_path.stat().st_size)
            except Exception:
                dur, fmt, size = 60.0, "mp3", file_path.stat().st_size

            res_ex = await session.execute(
                select(LibraryAsset).where(LibraryAsset.filename == filename)
            )
            existing = res_ex.scalar_one_or_none()
            if existing:
                existing.title = title
                existing.storage_path = str(file_path)
                existing.duration_seconds = dur
                existing.is_active = is_active
                existing.version = version
            else:
                asset = LibraryAsset(
                    category=category,
                    title=title,
                    filename=filename,
                    storage_path=str(file_path),
                    duration_seconds=dur,
                    format=fmt,
                    file_size_bytes=size,
                    is_active=is_active,
                    version=version,
                    uploaded_by="8449563084"
                )
                session.add(asset)
        await session.commit()
