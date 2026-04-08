import os
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer

load_dotenv()
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("lekkerpilot")
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

query = "can you amend your plea one day before trial?"
query_vec = embedding_model.encode(query).tolist()

response = index.query(
    vector=query_vec,
    top_k=25, 
    include_metadata=True,
    filter={
        "is_global": {"$eq": True},
        "jurisdiction": {"$eq": "za"}
    }
)

matches = response.get('matches', [])
print(f"Found {len(matches)} matches.")

for i, match in enumerate(matches):
    print(f"[{i+1}] Score: {match['score']:.3f} | File: {match['metadata']['filename']} | Page {match['metadata'].get('page', '?')}")
    print(f"{match['metadata']['text'][:150]}...\n")
