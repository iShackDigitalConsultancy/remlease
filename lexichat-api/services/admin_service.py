import os
import json
import time

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pinecone import ServerlessSpec

from dependencies import index, pc, UPLOAD_DIR, vo
import models
from utils.chunking import CLAUSE_PATTERN

def migrate_voyage_admin(request, request_headers, db):
    admin_key = os.environ.get("MIGRATION_ADMIN_KEY")
    req_key = request_headers.headers.get("X-Admin-Key")
    
    print(f"DEBUG_MIGRATE: admin_key_len={len(admin_key) if admin_key else 0}, req_key_len={len(req_key) if req_key else 0}")
    print(f"DEBUG_MIGRATE: admin_key={repr(admin_key)}")
    print(f"DEBUG_MIGRATE: req_key={repr(req_key)}")
    print(f"DEBUG_MIGRATE: All headers: {list(request_headers.headers.keys())}")
    
    if not admin_key or req_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    docs = db.query(models.WorkspaceDocument).all()
    readable = 0
    missing = []
    
    for doc in docs:
        path = os.path.join(UPLOAD_DIR, f"{doc.pinecone_doc_id}.md")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            readable += 1
        else:
            missing.append(doc.id)
            
    if request.dry_run:
        return {
            "mode": "dry_run",
            "total_documents": len(docs),
            "readable": readable,
            "missing": missing,
            "ready_to_migrate": len(missing) == 0
        }
    
    if missing:
        return {"error": "Missing documents", "missing": missing, "status": "failed"}

    def migration_stream():
        yield json.dumps({"status": "starting", "message": "Deleting index..."}) + "\n"
        try:
            pc.delete_index("lekkerpilot")
        except Exception as e:
            pass
            
        yield json.dumps({"status": "waiting", "message": "Sleeping 10s..."}) + "\n"
        time.sleep(10)
        
        yield json.dumps({"status": "creating", "message": "Creating index 1024d..."}) + "\n"
        pc.create_index(
            name="lekkerpilot", 
            dimension=1024, 
            metric="cosine", 
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        
        yield json.dumps({"status": "waiting", "message": "Sleeping 30s..."}) + "\n"
        time.sleep(30)
        
        # We need to recreate the index reference since we deleted and recreated it
        fresh_index = pc.Index("lekkerpilot")
                
        docs_migrated = 0
        vectors_upserted = 0
        failed_documents = []
        
        for doc in docs:
            path = os.path.join(UPLOAD_DIR, f"{doc.pinecone_doc_id}.md")
            try:
                with open(path, "r", encoding="utf-8") as f:
                    text_content = f.read()
                raw_splits = CLAUSE_PATTERN.split(text_content)
                splits = [s.strip() for s in raw_splits if s and s.strip()]
                if not splits:
                    splits = [text_content]
                
                chunks = []
                buffer = ""
                for split in splits:
                    if len(buffer) + len(split) <= 1500:
                        buffer += ("\n" if buffer else "") + split
                    else:
                        if buffer:
                            chunks.append(buffer)
                        buffer = split
                if buffer:
                    chunks.append(buffer)
                    
                batch_size = 50
                for i in range(0, len(chunks), batch_size):
                    batch = chunks[i:i+batch_size]
                    result = vo.embed(batch, model="voyage-law-2")
                    
                    vectors_to_upsert = []
                    for j, emb in enumerate(result.embeddings):
                        vectors_to_upsert.append({
                            "id": f"{doc.pinecone_doc_id}_chunk_{i+j}",
                            "values": emb,
                            "metadata": {
                                "firm_id": doc.workspace.firm_id if doc.workspace and doc.workspace.firm_id else "none",
                                "workspace_id": doc.workspace_id,
                                "doc_id": doc.id,
                                "text": batch[j]
                            }
                        })
                    fresh_index.upsert(vectors=vectors_to_upsert)
                    vectors_upserted += len(vectors_to_upsert)
                    
                    if i + batch_size < len(chunks):
                        time.sleep(2)
                        
                docs_migrated += 1
                yield json.dumps({"status": "progress", "message": f"Ingested doc {docs_migrated} of {len(docs)}: {doc.id}"}) + "\n"
                
            except Exception as e:
                failed_documents.append(doc.id)
                yield json.dumps({"status": "error", "message": f"Failed doc {doc.id}: {str(e)}"}) + "\n"
                
        yield json.dumps({
            "mode": "migration",
            "documents_migrated": docs_migrated,
            "vectors_upserted": vectors_upserted,
            "failed_documents": failed_documents,
            "status": "complete"
        }) + "\n"
        
    return StreamingResponse(migration_stream(), media_type="application/x-ndjson")


def reset_pinecone_admin(request_headers):
    admin_key = os.environ.get("MIGRATION_ADMIN_KEY")
    req_key = request_headers.headers.get("x-admin-key")
    
    if admin_key:
        admin_key = admin_key.strip()
    if req_key:
        req_key = req_key.strip()
        
    if not admin_key or req_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        index_name = "lekkerpilot"
        # 1. Delete the existing lekkerpilot index
        if index_name in pc.list_indexes().names():
            pc.delete_index(index_name)
        
        # 2. Wait 10 seconds
        time.sleep(10)
        
        # 3. Recreate it at 1024 dimensions, cosine metric
        pc.create_index(
            name=index_name,
            dimension=1024,
            metric="cosine",
            spec=ServerlessSpec(
                cloud="aws",
                region="us-east-1"
            )
        )
        
        # 4. Wait 30 seconds for readiness
        time.sleep(30)
        
        # 5. Return status
        return {"status": "complete", "message": "Index reset to 1024d"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
