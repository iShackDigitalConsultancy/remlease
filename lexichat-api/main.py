from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, status, Header, BackgroundTasks, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.orm import Session
import models
from database import engine, get_db
from auth import get_current_user, get_current_user_optional, create_access_token, get_password_hash, verify_password
from services.map_reduce import run_feature_gated_pipeline

from dependencies import pc, groq_client, vo, index, UPLOAD_DIR
from utils.chunking import smart_chunk, CLAUSE_PATTERN
from utils.exporters import export_markdown_to_docx
from services import intelligence_service

models.Base.metadata.create_all(bind=engine)

from pinecone import Pinecone, ServerlessSpec
from groq import Groq
import uuid
import os
import io
import json
import docx
import requests
import time
import re
import voyageai

app = FastAPI(title="REM-Leases API")

frontend_url = os.environ.get("FRONTEND_URL")

# Always allow both apex and www subdomain, plus any FRONTEND_URL from env
origins = list(filter(None, [
    frontend_url,
    "https://rem-leases.ai",
    "https://www.rem-leases.ai",
    "http://localhost:5173",
    "http://localhost:3000",
]))

# Enable CORS for React frontend (Local / Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://rem-leases.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Cloud Clients

def get_embedding(text: str):
    return vo.embed([text], model="voyage-law-2").embeddings[0]

def get_embeddings(texts: List[str]):
    all_embeddings = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i+50]
        result = vo.embed(batch, model="voyage-law-2")
        all_embeddings.extend(result.embeddings)
        if i + 50 < len(texts):
            time.sleep(2)
    return all_embeddings

# ── Smart legal chunking ──────────────────────────────────────────────────────

# ── Auto document brief ───────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    firm_name: Optional[str] = None
    is_firm_admin: bool = False

@app.post("/api/auth/signup")
def signup(user: UserCreate, x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    firm_id = None
    if user.is_firm_admin and user.firm_name:
        firm_id = str(uuid.uuid4())
        new_firm = models.Firm(id=firm_id, name=user.firm_name)
        db.add(new_firm)
        db.commit()
    elif user.firm_name:
        firm = db.query(models.Firm).filter(models.Firm.name == user.firm_name).first()
        if not firm:
            raise HTTPException(status_code=400, detail="Firm not found")
        firm_id = firm.id
    else:
        # Create a personal firm
        firm_id = str(uuid.uuid4())
        new_firm = models.Firm(id=firm_id, name=f"{user.full_name}'s Personal Workspace")
        db.add(new_firm)
        db.commit()

    user_id = str(uuid.uuid4())
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        id=user_id,
        email=user.email,
        hashed_password=hashed_password,
        full_name=user.full_name,
        role="admin" if user.is_firm_admin else "member",
        firm_id=firm_id
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # SECURE SESSION MIGRATION
    # If the user originated from an anonymous test session, immediately transition all their documents and workspaces to their newly secured Firm Account.
    if x_session_id and firm_id:
        orphan_workspaces = db.query(models.Workspace).filter(models.Workspace.session_id == x_session_id).all()
        for w in orphan_workspaces:
            w.firm_id = firm_id
            w.session_id = None
        if orphan_workspaces:
            db.commit()

    return {"message": "User created successfully"}

@app.post("/api/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user.id})
    return {"access_token": access_token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "full_name": user.full_name, "firm_id": user.firm_id, "role": user.role}}

@app.get("/api/workspaces")
def get_workspaces(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        workspaces = db.query(models.Workspace).filter(models.Workspace.firm_id == current_user.firm_id).all()
    else:
        if not x_session_id:
            return []
        workspaces = db.query(models.Workspace).filter(models.Workspace.session_id == x_session_id).all()
        
    result = []
    for w in workspaces:
        docs = db.query(models.WorkspaceDocument).filter(models.WorkspaceDocument.workspace_id == w.id).all()
        result.append({
            "id": w.id,
            "name": w.name,
            "documents": [{"id": d.pinecone_doc_id, "name": d.filename} for d in docs]
        })
    return result

@app.post("/api/workspaces")
def create_workspace(name: str = Form(...), current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    ws_id = str(uuid.uuid4())
    if current_user:
        new_ws = models.Workspace(id=ws_id, name=name, firm_id=current_user.firm_id)
    else:
        if not x_session_id:
            raise HTTPException(status_code=400, detail="Missing X-Session-Id header")
        new_ws = models.Workspace(id=ws_id, name=name, session_id=x_session_id)
    db.add(new_ws)
    db.commit()
    return {"id": ws_id, "name": name, "documents": []}

class WorkspaceRenameRequest(BaseModel):
    name: str

@app.put("/api/workspaces/{ws_id}")
def rename_workspace(ws_id: str, request: WorkspaceRenameRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.firm_id == current_user.firm_id).first()
    else:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.session_id == x_session_id).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    workspace.name = request.name
    db.commit()
    return {"id": workspace.id, "name": workspace.name}

@app.delete("/api/workspaces/{ws_id}")
def delete_workspace(ws_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.firm_id == current_user.firm_id).first()
    else:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.session_id == x_session_id).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    db.delete(workspace)
    db.commit()
    return {"message": "Deleted"}

class DocumentRenameRequest(BaseModel):
    name: str

@app.put("/api/documents/{doc_id}")
def rename_document(doc_id: str, request: DocumentRenameRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
            models.Workspace.firm_id == current_user.firm_id
        ).first()
    else:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
            models.Workspace.session_id == x_session_id
        ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    doc.filename = request.name
    db.commit()
    return {"message": "Renamed", "name": doc.filename}

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    # Find the document record and verify ownership
    if current_user:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
            models.Workspace.firm_id == current_user.firm_id
        ).first()
    else:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == doc_id) | (models.WorkspaceDocument.id == doc_id),
            models.Workspace.session_id == x_session_id
        ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Remove all Pinecone vectors for this document
    try:
        index.delete(filter={"doc_id": {"$eq": doc_id}})
    except Exception as e:
        print(f"Pinecone delete warning (non-fatal): {e}")

    # Remove the uploaded file from disk
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
    if os.path.exists(file_path):
        os.remove(file_path)

    # Remove the DB record
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}

# Background tasks proxy
def analyze_document_brief_background(doc_id: str, filename: str, sample_text: str):
    intelligence_service.analyze_document_brief_background(doc_id, filename, sample_text)

@app.get("/api/documents/{doc_id}/brief")
def get_document_brief(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return intelligence_service.get_document_brief(doc_id, current_user, x_session_id, db)

@app.post("/api/upload/{workspace_id}")
async def upload_pdf(workspace_id: str, background_tasks: BackgroundTasks, file: UploadFile = File(...), current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    firm_id_meta = "none"
    if current_user:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == workspace_id, models.Workspace.firm_id == current_user.firm_id).first()
        firm_id_meta = current_user.firm_id or "none"
    else:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == workspace_id, models.Workspace.session_id == x_session_id).first()
        
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    # Generate unique document ID
    doc_id = str(uuid.uuid4())
    
    file.file.seek(0)
    pdf_bytes = file.file.read()
    
    # Save PDF to disk for viewing in React
    
    file_path_saved = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
    with open(file_path_saved, "wb") as f:
        f.write(pdf_bytes)
    
    llama_api_key = os.environ.get("LLAMA_CLOUD_API_KEY")
    chunks_with_meta = []
    full_markdown = ""
    
    if not llama_api_key:
        print("WARNING: LLAMA_CLOUD_API_KEY is missing. Falling back to native PyMuPDF and Tesseract OCR.")
        import fitz
        try:
            doc = fitz.open(file_path_saved)
            for i, page in enumerate(doc):
                text = page.get_text()
                
                # If PyMuPDF couldn't find text, it's likely a scanned image
                if len(text.strip()) < 50:
                    try:
                        import pytesseract
                        import pdf2image
                        # Convert just this page to image to save memory (pages are 1-indexed in pdf2image)
                        images = pdf2image.convert_from_path(file_path_saved, first_page=i+1, last_page=i+1)
                        if images:
                            text = pytesseract.image_to_string(images[0])
                    except Exception as ocr_e:
                        print(f"Fallback OCR failed on page {i+1}: {ocr_e}")

                page_num = i + 1
                full_markdown += f"\n<!-- PAGE {page_num} START -->\n{text}\n"
                if text.strip():
                    for chunk in smart_chunk(text, page_num):
                        chunks_with_meta.append(chunk)
            
            with open(os.path.join(UPLOAD_DIR, f"{doc_id}.md"), "w") as f:
                f.write(full_markdown)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF file during fallback extraction. {str(e)}")
            
    else:
        try:
            headers = {
                "Authorization": f"Bearer {llama_api_key}",
                "Accept": "application/json"
            }
            
            # 1. Upload to LlamaParse Headless Pipeline
            with open(file_path_saved, "rb") as f:
                files = {"file": f}
                data = {"premium_mode": "false", "result_type": "markdown"}
                upload_resp = requests.post("https://api.cloud.llamaindex.ai/api/parsing/upload", headers=headers, files=files, data=data)
                upload_resp.raise_for_status()
                
            job_id = upload_resp.json().get("id")
            if not job_id:
                raise Exception("Failed to retrieve LlamaParse Job ID")
                
            # 2. Poll the Headless Pipeline until successful extraction
            max_retries = 60
            for _ in range(max_retries):
                status_resp = requests.get(f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}", headers=headers)
                status_resp.raise_for_status()
                status = status_resp.json().get("status")
                if status == "SUCCESS":
                    break
                elif status == "ERROR":
                    raise Exception("LlamaParse cloud processing failed with an upstream error")
                time.sleep(2)
            else:
                raise Exception("Document parsing timed out after 2 minutes")

            # 3. Pull the granular JSON array detailing perfectly structured markdown page-by-page
            result_resp = requests.get(f"https://api.cloud.llamaindex.ai/api/parsing/job/{job_id}/result/json", headers=headers)
            result_resp.raise_for_status()
            
            json_result = result_resp.json()
            pages = json_result.get("pages", [])
            
            for page_data in pages:
                page_num = page_data.get("page", 1)
                text = page_data.get("md", page_data.get("text", ""))
                full_markdown += f"\n<!-- PAGE {page_num} START -->\n{text}\n"
                
                if text.strip():
                    for chunk in smart_chunk(text, page_num):
                        chunks_with_meta.append(chunk)
                        
            # Cache the pristine LlamaParse markdown so downstream endpoints (Audit, Compare) can load it instantly
            with open(os.path.join(UPLOAD_DIR, f"{doc_id}.md"), "w") as f:
                f.write(full_markdown)

        except Exception as e:
            print(f"LlamaParse parsing completely failed: {e}")
            raise HTTPException(status_code=400, detail=f"LlamaParse document ingestion failed: {str(e)}")
            
    if not chunks_with_meta:
        raise HTTPException(status_code=400, detail="Could not extract any text from the document.")
        
    # Embed and store in Pinecone
    vectors_to_upsert = []
    if chunks_with_meta:
        texts = [c["text"] for c in chunks_with_meta]
        try:
            embeddings = get_embeddings(texts)
            for idx, c_meta in enumerate(chunks_with_meta):
                vectors_to_upsert.append({
                    "id": f"{doc_id}_{idx}",
                    "values": embeddings[idx],
                    "metadata": {
                        "doc_id": doc_id,
                        "filename": file.filename,
                        "page": c_meta["page"],
                        "text": c_meta["text"],
                        "is_global": False,
                        "jurisdiction": "none",
                        "firm_id": firm_id_meta
                    }
                })
        except Exception as e:
            print(f"Embedding error: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to generate and map document vector embeddings. Internal Error: {str(e)}")
            
    if vectors_to_upsert:
        index.upsert(vectors=vectors_to_upsert)
        
    db_doc = models.WorkspaceDocument(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        pinecone_doc_id=doc_id,
        filename=file.filename
    )
    db.add(db_doc)
    db.commit()

    # Auto-generate structured document brief securely in the BACKGROUND to drastically cut upload latency
    sample_text = " ".join([c["text"] for c in chunks_with_meta[:15]])
    background_tasks.add_task(analyze_document_brief_background, doc_id, file.filename, sample_text)

    return {"message": "Success", "doc_id": doc_id, "chunks_processed": len(vectors_to_upsert), "filename": file.filename, "brief": None}

class AuditRequest(BaseModel):
    doc_id: str
    policy: str

@app.post("/api/audit")
async def document_audit(payload: AuditRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.document_audit(payload, current_user, x_session_id, db)

class TimelineExtractionRequest(BaseModel):
    doc_ids: List[str]

@app.post("/api/extract-timeline")
async def extract_timeline(payload: TimelineExtractionRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.extract_timeline(payload, current_user, x_session_id, db)

class ExpiryExtractionRequest(BaseModel):
    doc_ids: List[str]

@app.post("/api/extract-expiries")
async def extract_expiries(payload: ExpiryExtractionRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.extract_expiries(payload, current_user, x_session_id, db)

class GapAnalysisRequest(BaseModel):
    doc_ids: List[str]

@app.post("/api/gap-analysis")
async def gap_analysis(payload: GapAnalysisRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.gap_analysis(payload, current_user, x_session_id, db)

@app.get("/api/portfolio-overview")
async def portfolio_overview(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.portfolio_overview(current_user, x_session_id, db)


class CompareRequest(BaseModel):
    doc_id_a: str
    doc_id_b: str

@app.post("/api/compare")
async def document_compare(payload: CompareRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.document_compare(payload, current_user, x_session_id, db)

class ChatRequest(BaseModel):
    doc_ids: List[str]
    query: str
    is_timeline: bool = False
    jurisdictions: List[str] = []
    is_firm_search: bool = False

@app.post("/api/chat")
async def chat_with_pdf(request: ChatRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.chat_with_pdf(request, current_user, x_session_id, db)

@app.get("/api/document/{doc_id}")
async def get_document(doc_id: str):
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.pdf")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Document not found, it may have been deleted.")

class ExportDocxRequest(BaseModel):
    text: str

@app.post("/api/export_docx")
async def export_to_docx(request: ExportDocxRequest):
    try:
        buffer = export_markdown_to_docx(request.text)
        headers = {
            'Content-Disposition': 'attachment; filename="Lekkerpilot_Draft.docx"'
        }
        return Response(content=buffer.getvalue(), 
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate DOCX export: {str(e)}")

class MigrationAdminRequest(BaseModel):
    dry_run: bool

@app.post("/api/admin/migrate-voyage")
def migrate_voyage_admin(
    request: MigrationAdminRequest, 
    request_headers: Request, 
    db: Session = Depends(get_db)
):
    import json
    import time
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
        import voyageai
        from pinecone import Pinecone, ServerlessSpec
        
        yield json.dumps({"status": "starting", "message": "Deleting index..."}) + "\n"
        pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
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
        
        index = pc.Index("lekkerpilot")
                
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
                    index.upsert(vectors=vectors_to_upsert)
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

class ResetPineconeRequest(BaseModel):
    pass

@app.post("/api/admin/reset-pinecone")
def reset_pinecone_admin(
    request_headers: Request
):
    admin_key = os.environ.get("MIGRATION_ADMIN_KEY")
    req_key = request_headers.headers.get("x-admin-key")
    
    if admin_key:
        admin_key = admin_key.strip()
    if req_key:
        req_key = req_key.strip()
        
    if not admin_key or req_key != admin_key:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
