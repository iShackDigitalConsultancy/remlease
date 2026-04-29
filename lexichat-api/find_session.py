import os
import models
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

pg_url = os.environ.get("DATABASE_URL")
if not pg_url:
    raise RuntimeError("DATABASE_URL missing")

engine = create_engine(pg_url)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

doc = db.query(models.WorkspaceDocument).filter(models.WorkspaceDocument.pinecone_doc_id == "0ae5e1d0-15e8-47b0-9003-66760929a8e1").first()
if doc:
    print(f"Workspace ID: {doc.workspace_id}")
    ws = db.query(models.Workspace).filter(models.Workspace.id == doc.workspace_id).first()
    if ws:
        print(f"Session ID: {ws.session_id}")
