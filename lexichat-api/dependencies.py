import os
import voyageai
from pinecone import Pinecone, ServerlessSpec
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize API Clients
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
vo = voyageai.Client(api_key=os.environ.get("VOYAGE_API_KEY"))

# Pinecone Index initialization globally via Serverless AWS mapping
index_name = "lekkerpilot"
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=1024,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
index = pc.Index(index_name)

# UPLOAD_DIR mapping
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Centralized Dependency exports
from database import get_db
from auth import get_current_user, get_current_user_optional

from config.model_versions import PRODUCTION_PINECONE_NAMESPACE

class NamespaceViolation(Exception):
    """Raised when a Pinecone namespace does not match the expected environment boundaries."""
    pass

def safe_upsert(index, vectors, namespace):
    if namespace is None or not isinstance(namespace, str):
        raise NamespaceViolation("Namespace must be a non-empty string.")
        
    if namespace == PRODUCTION_PINECONE_NAMESPACE:
        pass # OK for Production
    elif namespace.startswith("benchmark-"):
        pass # OK for Benchmark
    else:
        raise NamespaceViolation(f"NamespaceViolation: Expected production namespace '{PRODUCTION_PINECONE_NAMESPACE}' or prefix 'benchmark-', got '{namespace}'")
    
    index.upsert(vectors=vectors, namespace=namespace)

def safe_query(index, vector, top_k, include_metadata, query_filter, namespace):
    if namespace is None or not isinstance(namespace, str):
        raise NamespaceViolation("Namespace must be a non-empty string.")
        
    if namespace == PRODUCTION_PINECONE_NAMESPACE:
        pass # OK for Production
    elif namespace.startswith("benchmark-"):
        pass # OK for Benchmark
    else:
        raise NamespaceViolation(f"NamespaceViolation: Expected production namespace '{PRODUCTION_PINECONE_NAMESPACE}' or prefix 'benchmark-', got '{namespace}'")
    
    return index.query(vector=vector, top_k=top_k, include_metadata=include_metadata, filter=query_filter, namespace=namespace)

