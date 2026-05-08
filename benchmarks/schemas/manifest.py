from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime

class DocumentStageStats(BaseModel):
    ingestion_seconds: Optional[float] = None
    expiries_seconds: Optional[float] = None
    intelligence_seconds: Optional[float] = None

class DocumentStatus(BaseModel):
    doc_id: str
    filename: str
    size_bytes: int
    status: str = Field(pattern="^(succeeded|failed)$")
    error: Optional[str] = None
    stages: DocumentStageStats = Field(default_factory=DocumentStageStats)

class PineconeTracking(BaseModel):
    namespace: str
    cleanup_attempted: bool = False
    cleanup_succeeded: bool = False
    cleanup_error: Optional[str] = None

class ConfigTracking(BaseModel):
    llamaparse_config: dict
    groq_extraction_model: str
    voyage_embedding_model: str

class SecretsFingerprint(BaseModel):
    GROQ_API_KEY: Optional[str] = None
    LLAMA_CLOUD_API_KEY: Optional[str] = None
    VOYAGE_API_KEY: Optional[str] = None

class BenchmarkManifest(BaseModel):
    schema_version: str = "0.1.0"
    run_id: str
    run_tag: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    wall_clock_seconds: Optional[float] = None
    git_commit: str
    input_dir: str
    output_dir: str
    doc_limit: Optional[int] = None
    skip_embeddings: bool
    dry_run: bool
    config: ConfigTracking
    secrets_fingerprint: SecretsFingerprint
    pinecone: PineconeTracking
    documents: List[DocumentStatus] = Field(default_factory=list)
