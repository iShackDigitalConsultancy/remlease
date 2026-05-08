from benchmarks import _bootstrap  # noqa: F401
import contextlib
from database import engine, Base, SessionLocal

@contextlib.contextmanager
def ephemeral_session():
    """
    Context manager that provisions the ephemeral SQLite schema 
    and yields a fresh SQLAlchemy session.
    Cleanly closes the session on exit.
    """
    # Create the schema identical to production in the in-memory engine
    Base.metadata.create_all(engine)
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
