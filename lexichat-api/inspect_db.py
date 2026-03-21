import sqlite3
import pandas as pd

try:
    conn = sqlite3.connect('/Users/wdbmacminipro/Desktop/rem-leases/lexichat-api/database.db')
    docs = pd.read_sql("SELECT * FROM workspace_documents LIMIT 5", conn)
    print("----- WORKSPACE_DOCUMENTS -----")
    print(docs)
    ws = pd.read_sql("SELECT * FROM workspaces LIMIT 5", conn)
    print("\n----- WORKSPACES -----")
    print(ws)
except Exception as e:
    print(e)
