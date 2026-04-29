import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import WorkspaceDocument

pg_url = "postgresql+pg8000://postgres:PJJWrSwFNcKLJjfSInaiyTRqTbppMYbZ@nozomi.proxy.rlwy.net:13715/railway"
engine = create_engine(pg_url)
Session = sessionmaker(bind=engine)
session = Session()

docs = session.query(WorkspaceDocument).all()
total = len(docs)
found = 0

print(f"Checking {total} documents in PostgreSQL...")

for doc in docs:
    # Try local uploads first, fallback to /app/uploads if testing locally
    local_path = f"./uploads/{doc.id}.md"
    app_path = f"/app/uploads/{doc.id}.md"
    
    if os.path.exists(local_path) or os.path.exists(app_path):
        found += 1
    else:
        print(f"MISSING: {doc.id}")

print(f"Readable documents: {found}/{total}")
session.close()
