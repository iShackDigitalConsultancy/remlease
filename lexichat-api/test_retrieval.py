import os
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

load_dotenv()
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("rem-leases")

print("Checking index stats:")
print(index.describe_index_stats())

embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

query = "Rule 28 Amendments to Pleadings Timeframes"
query_vec = embedding_model.encode(query).tolist()

print("\nExecuting query...")
response = index.query(
    vector=query_vec,
    top_k=5, 
    include_metadata=True,
    filter={
        "is_global": {"$eq": True},
        "jurisdiction": {"$eq": "za"}
    }
)

matches = response.get('matches', [])
print(f"Found {len(matches)} matches.")

for match in matches:
    print(f"[{match['score']}] {match['metadata']['filename']} - Page {match['metadata'].get('page', '?')}")
    print(f"{match['metadata']['text'][:200]}...")
    print("---")
