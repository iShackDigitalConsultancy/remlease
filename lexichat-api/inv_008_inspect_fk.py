import sys
from sqlalchemy import create_engine, text

pg_url = "postgresql+pg8000://postgres:PJJWrSwFNcKLJjfSInaiyTRqTbppMYbZ@nozomi.proxy.rlwy.net:13715/railway"
engine = create_engine(pg_url)

def inspect_db_fks():
    print("--- CONNECTING TO POSTGRESQL ---")
    try:
        with engine.connect() as conn:
            query = """
            SELECT
                tc.table_name, 
                kcu.column_name, 
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name 
            FROM 
                information_schema.table_constraints AS tc 
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY';
            """
            result = conn.execute(text(query)).fetchall()
            print("FOREIGN KEYS:")
            for r in result:
                print(f"{r[0]}.{r[1]} -> {r[2]}.{r[3]}")
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    inspect_db_fks()
