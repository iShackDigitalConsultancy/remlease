import sys
from sqlalchemy import create_engine, text

pg_url = "postgresql+pg8000://postgres:PJJWrSwFNcKLJjfSInaiyTRqTbppMYbZ@nozomi.proxy.rlwy.net:13715/railway"
engine = create_engine(pg_url)

def inspect_db():
    print("--- CONNECTING TO POSTGRESQL ---")
    try:
        with engine.connect() as conn:
            # Get tables
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).fetchall()
            tables = [r[0] for r in result]
            print(f"Tables in production: {tables}")
            
            for table in tables:
                print(f"\n--- TABLE: {table} ---")
                
                # Get columns
                cols = conn.execute(text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{table}'")).fetchall()
                print("Columns:")
                for c in cols:
                    print(f"  - {c[0]} ({c[1]})")
                    
                # Get row count safely
                count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
                print(f"Row count: {count}")
                
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    inspect_db()
