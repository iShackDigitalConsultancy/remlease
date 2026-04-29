import os
import argparse
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
load_dotenv()
import models

print("WARNING: This script permanently deletes orphaned WorkspaceDocument records from PostgreSQL. Only run with explicit architect approval.\n")

pg_url = os.environ.get("DATABASE_URL")
if not pg_url:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

engine = create_engine(pg_url)
SessionLocal = sessionmaker(bind=engine)
db = SessionLocal()

API_URL = "https://rem-leases-production.up.railway.app/api/admin/migrate-voyage"
ADMIN_KEY = os.environ.get("MIGRATION_ADMIN_KEY")

def main():
    parser = argparse.ArgumentParser(description="Cleanup orphaned WorkspaceDocuments in Postgres")
    parser.add_argument("--dry-run", action="store_true", help="List orphaned records without deleting")
    args = parser.parse_args()

    # We must hit the live API to determine physical Volume state since we are running locally
    resp = requests.post(
        API_URL, 
        headers={"X-Admin-Key": ADMIN_KEY},
        json={"dry_run": True}
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to fetch live volume state: {resp.text}")
        
    missing_uuids = resp.json().get("missing", [])
    
    docs = db.query(models.WorkspaceDocument).filter(models.WorkspaceDocument.id.in_(missing_uuids)).all()

    if args.dry_run:
        print(f"DRY RUN: Found {len(docs)} orphaned documents.")
        for o in docs:
            print(f"Orphaned record: {o.id} ({o.filename})")
    else:
        print(f"Executing full cleanup of {len(docs)} orphaned documents...")
        count = 0
        for o in docs:
            print(f"Deleted orphaned record: {o.id} ({o.filename})")
            db.delete(o)
            count += 1
        db.commit()
        print(f"Cleaned {count} orphaned records")

if __name__ == "__main__":
    main()
