import os
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))

try:
    pc.delete_index("rem-leases")
    print("Successfully deleted 'rem-leases' index.")
except Exception as e:
    print(f"Error deleting index: {e}")
