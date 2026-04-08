import os
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("lekkerpilot")

from sentence_transformers import SentenceTransformer
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
vec = embedding_model.encode("28 Amendments to Pleadings and Documents (1) Any party desiring to amend a pleading or document").tolist()

res = index.query(
    vector=vec,
    top_k=20,
    include_metadata=True,
    filter={"jurisdiction": {"$eq": "za"}}
)
for r in res.get('matches', []):
    text = r['metadata']['text']
    if '28' in text and 'amend' in text.lower():
        print(f"--- MATCH (Score: {r['score']:.2f}) ---")
        print(text)
        print("\n")
