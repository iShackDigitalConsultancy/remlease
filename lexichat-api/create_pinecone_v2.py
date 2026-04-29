import os
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))

# Step 1: Discover spec
old_index = pc.describe_index("lekkerpilot")
cloud = old_index.spec.serverless.cloud
region = old_index.spec.serverless.region

print(f"Discovered Spec: cloud={cloud}, region={region}")

print("Creating lekkerpilot-v2 index (1024 d, cosine)...")
try:
    pc.create_index(
        name="lekkerpilot-v2",
        dimension=1024,
        metric="cosine",
        spec=ServerlessSpec(
            cloud=cloud,
            region=region
        )
    )
    print("SUCCESS: lekkerpilot-v2 index created.")
except Exception as e:
    print(f"FAILED to create index: {e}")
