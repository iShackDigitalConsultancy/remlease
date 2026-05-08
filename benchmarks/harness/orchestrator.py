from benchmarks import _bootstrap  # noqa: F401
import os
import uuid
import time
import json
import asyncio
from typing import Optional
from unittest.mock import patch
from benchmarks.schemas.manifest import DocumentStatus, DocumentStageStats
from benchmarks.schemas.workspace_summary import WorkspaceSummary

from services.ingestion_service import ingest_document
from services.intelligence_service import extract_expiries
from services.intelligence_engine import generate_intelligence_report

class DummyPayload:
    def __init__(self, doc_id: str, force_refresh: bool = False):
        self.doc_id = doc_id
        self.force_refresh = force_refresh

def mock_get_embeddings(texts):
    """Return mock embeddings matching the dimension expected (e.g. 1536 for Voyage)."""
    return [[0.0] * 1536 for _ in texts]

def process_documents(input_dir: str, run_dir: str, db, manifest_builder, doc_limit: Optional[int], skip_embeddings: bool, llamaparse_config: dict):
    pdf_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(".pdf")])
    if doc_limit is not None:
        pdf_files = pdf_files[:doc_limit]
        
    docs_processed = 0
    docs_failed = 0
    workspace_id = str(uuid.uuid4())
    
    docs_dir = os.path.join(run_dir, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    
    for filename in pdf_files:
        doc_id = str(uuid.uuid4())
        doc_folder = os.path.join(docs_dir, doc_id)
        os.makedirs(doc_folder, exist_ok=True)
        
        file_path = os.path.join(input_dir, filename)
        size_bytes = os.path.getsize(file_path)
        with open(file_path, "rb") as f:
            pdf_bytes = f.read()
            
        doc_status = DocumentStatus(doc_id=doc_id, filename=filename, size_bytes=size_bytes, status="failed")
        
        try:
            # 1. Ingestion
            start_time = time.time()
            if skip_embeddings:
                with patch("services.vector_service.get_embeddings", side_effect=mock_get_embeddings):
                    ingest_document(
                        pdf_bytes=pdf_bytes,
                        doc_id=doc_id,
                        workspace_id=workspace_id,
                        db=db,
                        upload_dir=doc_folder,
                        llamaparse_config=llamaparse_config,
                        filename=filename,
                        firm_id_meta="benchmark"
                    )
            else:
                ingest_document(
                    pdf_bytes=pdf_bytes,
                    doc_id=doc_id,
                    workspace_id=workspace_id,
                    db=db,
                    upload_dir=doc_folder,
                    llamaparse_config=llamaparse_config,
                    filename=filename,
                    firm_id_meta="benchmark"
                )
            doc_status.stages.ingestion_seconds = time.time() - start_time
            
            # 2. Expiries
            start_time = time.time()
            # extract_expiries is async and returns a StreamingResponse
            class DummyUser:
                id = "benchmark"
                firm_id = "benchmark"
            
            payload = DummyPayload(doc_id=doc_id)
            payload.doc_ids = [doc_id]
            
            import services.intelligence_service
            services.intelligence_service.cache_dir = doc_folder
            asyncio.run(extract_expiries(payload, current_user=DummyUser(), db=db))
            doc_status.stages.expiries_seconds = time.time() - start_time
            
            # 3. Intelligence Report
            start_time = time.time()
            # generate_intelligence_report is async
            # Signature: async def generate_intelligence_report(workspace_id: str, doc_ids: list, filenames: list, full_text: str, db, doc_map: dict = None, cache_dir: str = None)
            md_path = os.path.join(doc_folder, f"{doc_id}.md")
            full_text = ""
            if os.path.exists(md_path):
                with open(md_path, "r") as f:
                    full_text = f.read()
                    
            asyncio.run(generate_intelligence_report(
                workspace_id=workspace_id,
                doc_ids=[doc_id],
                filenames=[filename],
                full_text=full_text,
                db=db,
                cache_dir=doc_folder
            ))
            doc_status.stages.intelligence_seconds = time.time() - start_time
            
            doc_status.status = "succeeded"
            docs_processed += 1
            
        except Exception as e:
            doc_status.status = "failed"
            doc_status.error = str(e)
            docs_failed += 1
            
        manifest_builder.add_document(doc_status)

    # Build workspace summary
    ws_summary = WorkspaceSummary(workspace_id=workspace_id, doc_count=docs_processed)
    with open(os.path.join(run_dir, "workspace_summary.json"), "w") as f:
        f.write(ws_summary.model_dump_json(indent=2))
        
    return {
        "docs_processed": docs_processed,
        "docs_failed": docs_failed,
        "workspace_id": workspace_id
    }
