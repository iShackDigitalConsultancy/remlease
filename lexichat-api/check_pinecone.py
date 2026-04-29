import os
from pinecone import Pinecone

pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
index = pc.Index("lekkerpilot")

stats = index.describe_index_stats()
print(f"Total vector count: {stats.total_vector_count}")
print(f"Dimensions: {stats.dimension}")
print(f"Namespaces: {stats.namespaces}")
