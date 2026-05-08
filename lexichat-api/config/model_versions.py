# Groq Extraction Model
GROQ_EXTRACTION_MODEL = "llama-3.3-70b-versatile"
# Deprecation watch: Groq announces deprecations on the /docs/deprecations page. 
# Subscribe to the Groq Discord #announcements channel. When a deprecation is announced, 
# open a ticket to evaluate the replacement and re-baseline all golden runs.

# Voyage Embedding Model
VOYAGE_EMBEDDING_MODEL = "voyage-law-2"
VOYAGE_EMBEDDING_DIM = 1024
# Deprecation watch: Voyage announces deprecations via email and at https://docs.voyageai.com/. 
# When a deprecation is announced, the embedding model AND the Pinecone index dimensions must be migrated together.

# LlamaParse Configuration
LLAMAPARSE_RESULT_TYPE = "markdown"
LLAMAPARSE_DEFAULT_MODE = "false"  # basic mode

# Pinecone
PRODUCTION_PINECONE_NAMESPACE = ""  
# Verified: The codebase currently calls `index.upsert` in `ingestion_service.py` and `admin_service.py` 
# WITHOUT a namespace argument. The official Pinecone SDK handles an absent namespace by defaulting to `""`. 
# Therefore, `""` is the true production namespace.
