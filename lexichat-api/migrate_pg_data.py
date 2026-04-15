import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User, Firm, Workspace, WorkspaceDocument, AnonymousSession

sqlite_url = "sqlite:///./rem-leases.db"
pg_url = "postgresql+pg8000://postgres:PJJWrSwFNcKLJjfSInaiyTRqTbppMYbZ@nozomi.proxy.rlwy.net:13715/railway"

sqlite_engine = create_engine(sqlite_url)
pg_engine = create_engine(pg_url)

# 1. Create tables in Postgres natively
print("Creating tables in PostgreSQL...")
Base.metadata.create_all(bind=pg_engine)

SqliteSession = sessionmaker(bind=sqlite_engine)
PgSession = sessionmaker(bind=pg_engine)

source = SqliteSession()
target = PgSession()

print("Extracting data from SQLite and pushing to Postgres...")

def migrate_model(model_class):
    rows = source.query(model_class).all()
    if not rows:
        return
    for row in rows:
        # Create a dictionary of the native python object, ignoring SQLAlchemy state
        data = {c.name: getattr(row, c.name) for c in model_class.__table__.columns}
        new_row = model_class(**data)
        target.add(new_row)
    try:
        target.commit()
    except Exception as e:
        print(f"Error migrating {model_class.__tablename__}: {e}")
        target.rollback()
    print(f"Successfully Migrated {len(rows)} records into table '{model_class.__tablename__}'")

# Execute strictly sequentially avoiding Foreign Key Constraint faults
try:
    migrate_model(Firm)
    migrate_model(User)
    migrate_model(AnonymousSession)
    migrate_model(Workspace)
    migrate_model(WorkspaceDocument)
    print("Migration Fully Completed!")
except Exception as e:
    print(f"Unexpected Fatal Error during migration: {e}")

source.close()
target.close()
