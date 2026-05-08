import os
import json
import hashlib
from typing import Optional
from benchmarks.schemas.manifest import BenchmarkManifest, SecretsFingerprint, ConfigTracking, PineconeTracking

def hash_secret(secret_val: Optional[str]) -> Optional[str]:
    if not secret_val:
        return None
    return hashlib.sha256(secret_val.encode('utf-8')).hexdigest()[:8]

class ManifestBuilder:
    def __init__(self, run_id: str, run_tag: str, started_at, git_commit: str, input_dir: str, output_dir: str, doc_limit: Optional[int], skip_embeddings: bool, dry_run: bool):
        from config.model_versions import GROQ_MODEL, VOYAGE_MODEL
        
        secrets = SecretsFingerprint(
            GROQ_API_KEY=hash_secret(os.environ.get("GROQ_API_KEY")),
            LLAMA_CLOUD_API_KEY=hash_secret(os.environ.get("LLAMA_CLOUD_API_KEY")),
            VOYAGE_API_KEY=hash_secret(os.environ.get("VOYAGE_API_KEY"))
        )
        
        config = ConfigTracking(
            llamaparse_config={"premium_mode": "false", "result_type": "markdown"},
            groq_extraction_model=GROQ_MODEL,
            voyage_embedding_model=VOYAGE_MODEL
        )
        
        pinecone_tracker = PineconeTracking(
            namespace=f"benchmark-{run_id}"
        )
        
        self.manifest = BenchmarkManifest(
            run_id=run_id,
            run_tag=run_tag,
            started_at=started_at,
            git_commit=git_commit,
            input_dir=input_dir,
            output_dir=output_dir,
            doc_limit=doc_limit,
            skip_embeddings=skip_embeddings,
            dry_run=dry_run,
            config=config,
            secrets_fingerprint=secrets,
            pinecone=pinecone_tracker
        )
        self.output_path = os.path.join(output_dir, "manifest.json")

    def add_document(self, doc_status):
        self.manifest.documents.append(doc_status)

    def update_pinecone_cleanup(self, attempted: bool, succeeded: bool, error: Optional[str]):
        self.manifest.pinecone.cleanup_attempted = attempted
        self.manifest.pinecone.cleanup_succeeded = succeeded
        self.manifest.pinecone.cleanup_error = error

    def finish(self, completed_at, wall_clock_seconds: float):
        self.manifest.completed_at = completed_at
        self.manifest.wall_clock_seconds = wall_clock_seconds
        self.flush()
        
    def flush(self):
        with open(self.output_path, "w") as f:
            # Pydantic v2 .model_dump_json()
            f.write(self.manifest.model_dump_json(indent=2))
