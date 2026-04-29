import sys
from sqlalchemy import create_engine, text

pg_url = "postgresql+pg8000://postgres:PJJWrSwFNcKLJjfSInaiyTRqTbppMYbZ@nozomi.proxy.rlwy.net:13715/railway"
engine = create_engine(pg_url)

def check_orphans():
    try:
        with engine.connect() as conn:
            orphans_ws_docs = conn.execute(text(
                "SELECT count(*) FROM workspace_documents WHERE workspace_id NOT IN (SELECT id FROM workspaces)"
            )).scalar()
            
            orphans_ws = conn.execute(text(
                "SELECT count(*) FROM workspaces WHERE firm_id IS NOT NULL AND firm_id NOT IN (SELECT id FROM firms)"
            )).scalar()
            
            orphans_users = conn.execute(text(
                "SELECT count(*) FROM users WHERE firm_id IS NOT NULL AND firm_id NOT IN (SELECT id FROM firms)"
            )).scalar()
            
            print(f"Orphaned Workspace Documents: {orphans_ws_docs}")
            print(f"Orphaned Workspaces (invalid firm): {orphans_ws}")
            print(f"Orphaned Users (invalid firm): {orphans_users}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    check_orphans()
