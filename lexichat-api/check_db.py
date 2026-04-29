import os
import models
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

pg_url = os.environ.get("DATABASE_URL", "postgresql+pg8000://postgres:MpxsytEYlyQXxgDDplPsyqYPUFptTOrA@nozomi.proxy.rlwy.net:13715/railway")

engine = create_engine(pg_url)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

docs = db.query(models.WorkspaceDocument).all()
print(f"Total rows in WorkspaceDocument: {len(docs)}")
for d in docs:
    if str(d.id) == "0ae5e1d0-15e8-47b0-9003-66760929a8e1":
        print("FOUND newly uploaded document in DB!")
