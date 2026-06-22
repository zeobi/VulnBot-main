from contextlib import contextmanager
from functools import wraps
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeMeta, Session, declarative_base, sessionmaker

from config.config import Configs


def _build_db_url_and_options():
    db_type = getattr(Configs.db_config, "type", "sqlite").lower()

    if db_type == "sqlite":
        sqlite_path = Path(Configs.db_config.sqlite.get("path") or Configs.PENTEST_ROOT / "data/vulnbot.sqlite3")
        if not sqlite_path.is_absolute():
            sqlite_path = Configs.PENTEST_ROOT / sqlite_path
        sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{sqlite_path.as_posix()}", {"connect_args": {"check_same_thread": False}}

    if db_type == "mysql":
        mysql = Configs.db_config.mysql
        db_url = (
            f"mysql+pymysql://{mysql['user']}:{mysql['password']}"
            f"@{mysql['host']}:{mysql['port']}/{mysql['database']}"
        )
        return db_url, {}

    raise ValueError(f"Unsupported database type: {db_type}")


db_url, engine_options = _build_db_url_and_options()

engine = create_engine(db_url, **engine_options)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base: DeclarativeMeta = declarative_base()

@contextmanager
def session_scope() -> Session:
    """上下文管理器用于自动获取 Session, 避免错误"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def with_session(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        with session_scope() as session:
            try:
                result = f(session, *args, **kwargs)
                session.commit()
                return result
            except:
                session.rollback()
                raise

    return wrapper


def create_tables():
    # Import models before metadata creation so SQLAlchemy registers every table.
    import db.models.conversation_model  # noqa: F401
    import db.models.benchmark_model  # noqa: F401
    import db.models.message_model  # noqa: F401
    import db.models.plan_model  # noqa: F401
    import db.models.session_model  # noqa: F401
    import db.models.task_model  # noqa: F401
    import rag.kb.models.kb_document_model  # noqa: F401
    import rag.kb.models.knowledge_file_model  # noqa: F401

    Base.metadata.create_all(bind=engine)
