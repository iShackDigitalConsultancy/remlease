from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, status, Header, BackgroundTasks
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

models.Base.metadata.create_all(bind=engine)

from pinecone import Pinecone, ServerlessSpec
from groq import Groq
from sentence_transformers import SentenceTransformer
import uuid
import os
import io
import json
import docx
import requests
import time
import re
from sentence_transformers import SentenceTransformer, CrossEncoder

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
pc = Pinecone(api_key=os.environ.get("PINECONE_API_KEY"))
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

index_name = "lekkerpilot"
if index_name not in pc.list_indexes().names():
    pc.create_index(
        name=index_name,
        dimension=384,  # all-MiniLM-L6-v2 output dimension
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
index = pc.Index(index_name)

# Initialize local embedding model for insanely fast, free vectorization
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def get_embedding(text: str):
    return embedding_model.encode(text).tolist()

def get_embeddings(texts: List[str]):
    # Drastically reduce batch_size to prevent OOM killed on Railway's 512MB RAM limit
    return embedding_model.encode(texts, batch_size=4, show_progress_bar=False).tolist()

# Cross-encoder reranker — re-scores Pinecone hits for precision
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

# ── Smart legal chunking ──────────────────────────────────────────────────────
CLAUSE_PATTERN = re.compile(
    r'(?:^|\n)(?='
    r'\d+\.\d+|'          # 12.1  / 1.2.3
    r'\d+\.|'             # 1.
    r'\([a-zA-Z]\)|'      # (a)
    r'WHEREAS|'           # WHEREAS
    r'NOW,?\s+THEREFORE|' # NOW THEREFORE
    r'SCHEDULE|'          # SCHEDULE
    r'ANNEXURE|'
    r'[A-Z]{4,}\s*:)'     # ALL CAPS HEADING:
)

def smart_chunk(text: str, page_num: int, max_chars: int = 900, overlap: int = 150):
    """Split text on legal clause boundaries with character-length cap."""
    raw_splits = CLAUSE_PATTERN.split(text)
    splits = [s.strip() for s in raw_splits if s and s.strip()]
    if not splits:
        splits = [text]

    chunks = []
    buffer = ""
    for split in splits:
        if len(buffer) + len(split) <= max_chars:
            buffer += ("\n" if buffer else "") + split
        else:
            if buffer:
                chunks.append({"text": buffer, "page": page_num})
            # Start new buffer with overlap from previous
            buffer = buffer[-overlap:] + "\n" + split if buffer else split
    if buffer:
        chunks.append({"text": buffer, "page": page_num})
    return chunks

# ── Auto document brief ───────────────────────────────────────────────────────
def analyze_document_brief(doc_id: str, filename: str, sample_text: str) -> dict:
    """Run a structured Groq extraction and return a JSON brief."""
    prompt = (
        "You are a senior South African legal analyst. Analyse the following document extract, "
        "which may contain dirty OCR from a signed/scanned lease or contract. "
        "Read carefully through any garbled text to find the core entities.\n\n"
        "Respond with ONLY valid JSON — no markdown fences, no commentary.\n"
        "Return exactly this structure:\n"
        '{\n'
        '  "doc_type": "short document type e.g. Commercial Lease, Sale of Shares, NDA",\n'
        '  "parties": ["Party A Name", "Party B Name"],\n'
        '  "obligations": ["Key obligation 1", "Key obligation 2"],\n'
        '  "financial_terms": ["Rent/Payment amounts", "Deposits", "Escalations if any"],\n'
        '  "key_dates": [{"label": "Commencement/Effective Date", "value": "1 March 2024"}],\n'
        '  "execution_status": "Briefly state if signatures appear present or if it looks like an unsigned draft",\n'
        '  "summary": "Two-sentence plain English summary of the document."\n'
        '}\n\n'
        f"DOCUMENT: {filename}\n\nEXTRACT:\n{sample_text[:8000]}"
    )
    try:
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.1,
            max_tokens=800
        )
        raw = resp.choices[0].message.content.strip()
        # Strip accidental markdown fences
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)
    except Exception as e:
        print(f"Brief generation failed: {e}")
        return {
            "doc_type": "Legal Document", 
            "parties": [], 
            "obligations": [], 
            "financial_terms": [], 
            "key_dates": [], 
            "execution_status": "Unknown", 
            "summary": ""
        }

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
    file_path = f"./uploads/{doc_id}.pdf"
    if os.path.exists(file_path):
        os.remove(file_path)

    # Remove the DB record
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}

def analyze_document_brief_background(doc_id: str, filename: str, sample_text: str):
    try:
        brief = analyze_document_brief(doc_id, filename, sample_text)
        with open(f"./uploads/{doc_id}_brief.json", "w") as f:
            json.dump(brief, f)
    except Exception as e:
        print(f"Background brief extraction failed: {e}")

@app.get("/api/documents/{doc_id}/brief")
def get_document_brief(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
        raise HTTPException(status_code=403, detail="Access denied")
        
    file_path = f"./uploads/{doc_id}_brief.json"
    if not os.path.exists(file_path):
        return {"brief": None}
        
    with open(file_path, "r") as f:
        brief = json.load(f)
    return {"brief": brief}

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
    os.makedirs("./uploads", exist_ok=True)
    file_path_saved = f"./uploads/{doc_id}.pdf"
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
            
            with open(f"./uploads/{doc_id}.md", "w") as f:
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
            with open(f"./uploads/{doc_id}.md", "w") as f:
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
    # 1. Verify access to the document
    if current_user:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == payload.doc_id) | (models.WorkspaceDocument.id == payload.doc_id),
            models.Workspace.firm_id == current_user.firm_id
        ).first()
    else:
        doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            (models.WorkspaceDocument.pinecone_doc_id == payload.doc_id) | (models.WorkspaceDocument.id == payload.doc_id),
            models.Workspace.session_id == x_session_id
        ).first()
        
    if not doc:
        raise HTTPException(status_code=403, detail="Access denied for document audit")
        
    # 2. Extract Document Text directly from local cached markdown
    file_path = f"./uploads/{payload.doc_id}.md"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Underlying document markdown file not found")
        
    try:
        with open(file_path, "r") as f:
            full_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read local document: {str(e)}")

    map_task = f"Extract all policy clauses, compliance obligations, and risk provisions from this section."
    reduce_task = f"""Produce a structured audit report flagging all compliance risks and policy gaps against this strictly provided policy:
{payload.policy}

Deduplicate identical violations found across different sections.
Output ONLY valid JSON matching this exact array structure:
[
  {{
    "check": "Rule 1 from the policy",
    "status": "PASS", 
    "explanation": "Brief explanation of why it passed, quoting the text if possible."
  }},
  {{
    "check": "Rule 2 from the policy",
    "status": "FAIL", 
    "explanation": "Explanation of why it failed or is missing."
  }}
]
Use "PASS", "FAIL", or "REVIEW" for the status. Output nothing but the JSON array."""

    def legacy_op():
        doc_text = str(full_text)[:18000]
        prompt = f"""You are a senior legal auditor reviewing a document against a strict Compliance Policy.
    
POLICY TO CHECK THE DOCUMENT AGAINST:
{payload.policy}

DOCUMENT TEXT:
{doc_text}

INSTRUCTIONS:
Evaluate the document strictly against the policy above. 
Output ONLY valid JSON matching this exact array structure:
[
  {{
    "check": "Rule 1 from the policy",
    "status": "PASS", 
    "explanation": "Brief explanation of why it passed, quoting the text if possible."
  }},
  {{
    "check": "Rule 2 from the policy",
    "status": "FAIL", 
    "explanation": "Explanation of why it failed or is missing."
  }}
]

Use "PASS", "FAIL", or "REVIEW" for the status. Output nothing but the JSON array."""
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=2000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return {"audit": json.loads(raw)}

    return StreamingResponse(run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op), media_type="text/event-stream")

class TimelineExtractionRequest(BaseModel):
    doc_ids: List[str]

@app.post("/api/extract-timeline")
async def extract_timeline(payload: TimelineExtractionRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="No documents selected")
        
    full_text: str = ""
    for doc_id in payload.doc_ids:
        # Verify access
        if current_user is not None:
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
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        file_path = f"./uploads/{doc_id}.md"
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    doc_text = f.read()
                full_text += f"\n--- DOCUMENT START: {doc.filename} ---\n{doc_text}\n"
            except Exception as e:
                print(f"Failed to read {file_path}: {e}")
                
    if not full_text:
        raise HTTPException(status_code=404, detail="No text could be extracted from selected documents.")

    map_task = "Extract all dated events, milestones, and party obligations from this section."
    reduce_task = """Produce a chronological timeline of all events across the full document.
JSON SCHEMA REQUIREMENT:
{
  "characters": [
    {
      "name": "Jane Doe",
      "role": "Plaintiff",
      "description": "Former employee of the company..."
    }
  ],
  "timeline": [
    {
      "date": "2023-01-15",
      "event": "Employment Contract Signed",
      "source": "contract.pdf"
    }
  ]
}
If a date is vague, express it as roughly as possible inside the date field. Make sure the timeline array chronologically ordered from oldest to newest. Return ONLY the raw JSON object."""

    def legacy_op():
        old_full_text = str(full_text)[:18000]
        prompt = f"""You are a senior legal analyst creating a comprehensive chronologically-ordered Master Timeline and Cast of Characters from the provided documents.

DOCUMENTS TEXT:
{old_full_text}

INSTRUCTIONS:
1. Identify all key people, organizations, or entities mentioned (Cast of Characters).
2. Extract all events with implied or explicit dates into a unified Master Timeline.
3. Output ONLY valid JSON matching this exact structure:
{{
  "characters": [
    {{
      "name": "Jane Doe",
      "role": "Plaintiff",
      "description": "Former employee of the company..."
    }}
  ],
  "timeline": [
    {{
      "date": "2023-01-15",
      "event": "Employment Contract Signed",
      "source": "contract.pdf"
    }}
  ]
}}

If a date is vague (e.g. "Early 2023"), express it as roughly as possible inside the date field. Make sure the timeline array chronologically ordered from oldest to newest. Return ONLY the raw JSON object."""
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=3000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    return StreamingResponse(run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op), media_type="text/event-stream")

class ExpiryExtractionRequest(BaseModel):
    doc_ids: List[str]

@app.post("/api/extract-expiries")
async def extract_expiries(payload: ExpiryExtractionRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not payload.doc_ids:
        raise HTTPException(status_code=400, detail="No documents selected")
        
    full_text: str = ""
    for doc_id in payload.doc_ids:
        if current_user is not None:
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
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        file_path = f"./uploads/{doc_id}.md"
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    doc_text = f.read()
                full_text += f"\n--- DOCUMENT START: {doc.filename} ---\n{doc_text}\n"
            except Exception as e:
                print(f"Failed to read {file_path}: {e}")
                
    if not full_text:
        raise HTTPException(status_code=404, detail="No text could be extracted from selected documents.")

    map_task = "Extract all dates, terms, deadlines, and renewal notice periods from this section."
    reduce_task = """Produce a chronological expiry schedule with calculated deadlines across the full document.
Find the Expiry Date, Renewal Notice Deadline, and relevant Notification Clause for each document.
Output ONLY valid JSON matching this exact structure:
{
  "expiries": [
    {
      "document": "contract_name.pdf",
      "commencement_date": "YYYY-MM-DD",
      "expiry_date": "YYYY-MM-DD",
      "renewal_deadline": "YYYY-MM-DD",
      "clause": "Text of the clause governing renewal/termination",
      "action_required": "Short description of what must happen"
    }
  ]
}
If a date is vague or missing, make your best guess for the date format "YYYY-MM-DD". Perform strict date arithmetic if the contract specifies a start date and term duration. Return ONLY the JSON object."""

    def legacy_op():
        old_full_text = str(full_text)[:18000]
        prompt = f"""You are a senior legal analyst extracting crucial dates from multiple contracts to trigger calendar/SmartBuilding events.

DOCUMENTS TEXT:
{old_full_text}

INSTRUCTIONS:
Find the Expiry Date, Renewal Notice Deadline, and relevant Notification Clause for each document.
Output ONLY valid JSON matching this exact structure:
{{
  "expiries": [
    {{
      "document": "contract_name.pdf",
      "commencement_date": "YYYY-MM-DD" (Extract the explicit start or signature date, or null if absolutely missing),
      "expiry_date": "YYYY-MM-DD" (EXTREMELY IMPORTANT: If missing, you MUST CALCULATE it by finding 'Commencement Date' or 'Signature Date' and adding 'Duration'/'Term'. E.g. start=2023-01-01 + duration 5 years = 2028-01-01),
      "renewal_deadline": "YYYY-MM-DD" (Calculate from expiry date minus notice period if applicable),
      "clause": "Text of the clause governing renewal/termination",
      "action_required": "Short description of what must happen"
    }}
  ]
}}

If a date is vague or missing, make your best guess for the date format "YYYY-MM-DD". Perform strict date arithmetic if the contract specifies a start date and term duration. Return ONLY the JSON object."""
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=2000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    return StreamingResponse(run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op), media_type="text/event-stream")

class GapAnalysisRequest(BaseModel):
    doc_ids: List[str]

@app.post("/api/gap-analysis")
async def gap_analysis(payload: GapAnalysisRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if len(payload.doc_ids) < 2:
        raise HTTPException(status_code=400, detail="At least two documents required to run a gap analysis.")
        
    full_text: str = ""
    for doc_id in payload.doc_ids:
        if current_user is not None:
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
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        file_path = f"./uploads/{doc_id}.md"
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    doc_text = f.read()
                full_text += f"\n--- DOCUMENT START: {doc.filename} ---\n{doc_text}\n"
            except Exception as e:
                print(f"Failed to read {file_path}: {e}")
                
    if not full_text:
        raise HTTPException(status_code=404, detail="No text could be extracted from selected documents.")

    map_task = "Extract all obligations, restrictions, and operational requirements from this section."
    reduce_task = """Cross-reference franchise obligations against lease provisions and list every misalignment found. Flag uncertain matches explicitly.
Output exactly this JSON structure:
{
  "detected_lease": "FileName (or null)",
  "detected_franchise": "FileName (or null)",
  "lease_key_terms": { "term": "...", "expiry": "...", "permitted_use": "..." },
  "franchise_key_terms": { "term": "...", "expiry": "...", "permitted_use": "..." },
  "gaps": [
    {
      "category": "Term Alignment | Permitted Use | Signage/Aesthetics | Contingencies / Exit",
      "franchise_requirement": "What does the franchise demand?",
      "lease_provision": "What does the lease actually say?",
      "status": "RISK" or "MATCH" or "WARNING"
    }
  ]
}
If only one document type is uploaded, map whatever you can and put 'null' for the missing one. Return ONLY valid JSON."""

    def legacy_op():
        old_full_text = str(full_text)[:24000]
        prompt = f"""You are a master commercial real estate and franchise attorney.
The user has uploaded multiple documents. Your job is to automatically detect which is the Franchise Agreement and which is the Lease Agreement. Then, cross-reference them to find gaps, conflicts, and risks. 
Provide key terms and a critical mismatch report.

DOCUMENTS TEXT:
{old_full_text}

INSTRUCTIONS:
Output exactly this JSON structure:
{{
  "detected_lease": "FileName (or null)",
  "detected_franchise": "FileName (or null)",
  "lease_key_terms": {{ "term": "...", "expiry": "...", "permitted_use": "..." }},
  "franchise_key_terms": {{ "term": "...", "expiry": "...", "permitted_use": "..." }},
  "gaps": [
    {{
      "category": "Term Alignment | Permitted Use | Signage/Aesthetics | Contingencies / Exit",
      "franchise_requirement": "What does the franchise demand?",
      "lease_provision": "What does the lease actually say?",
      "status": "RISK" or "MATCH" or "WARNING"
    }}
  ]
}}

If only one document type is uploaded, map whatever you can and put 'null' for the missing one.
Return ONLY valid JSON."""
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=3000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    return StreamingResponse(run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op), media_type="text/event-stream")

@app.get("/api/portfolio-overview")
async def portfolio_overview(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        docs = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            models.Workspace.firm_id == current_user.firm_id
        ).all()
    elif x_session_id:
        docs = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
            models.Workspace.session_id == x_session_id
        ).all()
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
        
    if not docs:
        return {"data": []}
        
    full_text = ""
    # Process up to 10 documents, taking 6000 characters each to avoid heavy context limits.
    for doc in docs[:10]:
        file_path = f"./uploads/{doc.pinecone_doc_id}.md"
        if not os.path.exists(file_path):
            file_path = f"./uploads/{doc.id}.md"
            
        if os.path.exists(file_path):
            try:
                with open(file_path, "r") as f:
                    doc_text = f.read()
                full_text += f"\n--- DOCUMENT START: {doc.filename} ---\n{doc_text}\n"
            except Exception as e:
                pass
                
    if not full_text:
        return {"data": []}

    map_task = "Extract key financial terms, parties, and material obligations from this section."
    reduce_task = """Produce a portfolio dashboard of key terms across all documents. Flag documents where extraction confidence was low.
Output exactly this JSON structure as an array of objects:
[
  {
    "filename": "Exact Name of the Document",
    "doc_type": "Lease" OR "Franchise Agreement" OR "Unknown",
    "expiry_date": "YYYY-MM-DD",
    "renewal_deadline": "YYYY-MM-DD",
    "key_terms": "1-sentence summary of the most important term or permitted use",
    "flags": "Any major risks, unusual clauses or Management Alerts"
  }
]
Ensure the JSON is perfectly valid and is just the array. Ensure you include EVERY specific document listed in the text."""

    async def generate_response():
        use_map_reduce = os.environ.get("USE_MAP_REDUCE", "False").lower() in ("true", "1", "yes")
        
        if use_map_reduce:
            from services.map_reduce import run_map_reduce_stream
            final = None
            async for chunk in run_map_reduce_stream(full_text, map_task, reduce_task):
                if '"status": "complete"' in chunk:
                    try:
                        obj = json.loads(chunk[6:])
                        final = obj.get("data", [])
                    except:
                        final = []
                else:
                    yield chunk
                    
            if final is not None:
                for item in final:
                    matched_doc = next((d for d in docs if d.filename == item.get("filename")), None)
                    if matched_doc:
                        item["workspace_id"] = getattr(matched_doc, "workspace_id", None)
                        item["doc_id"] = getattr(matched_doc, "id", None)
                yield f"data: {json.dumps({'status': 'complete', 'data': final})}\n\n"
        else:
            yield f"data: {json.dumps({'status': 'processing', 'message': 'Analysing document (Legacy Mode)...'})}\n\n"
            
            # Legacy logic
            legacy_text = ""
            for doc in docs[:10]:
                fp = f"./uploads/{doc.pinecone_doc_id}.md"
                if not os.path.exists(fp):
                    fp = f"./uploads/{doc.id}.md"
                if os.path.exists(fp):
                    with open(fp, "r") as f:
                        t = f.read()
                    legacy_text += f"\n--- DOCUMENT START: {doc.filename} ---\n{str(t)[:6000]}\n"
                    
            prompt = f"""You are an expert commercial leasing manager. Review the following portfolio of lease and franchise agreements.
For each document provided, extract the critical terms for a global management dashboard.

DOCUMENTS TEXT:
{legacy_text}

INSTRUCTIONS:
Output exactly this JSON structure as an array of objects:
[
  {{
    "filename": "Exact Name of the Document",
    "doc_type": "Lease" OR "Franchise Agreement" OR "Unknown",
    "expiry_date": "YYYY-MM-DD" (EXTREMELY IMPORTANT: If the expiry date is not explicitly stated, you MUST CALCULATE it by finding the 'Commencement Date' or 'Signature Date' and adding the 'Duration' or 'Term'. For example, if commencement is 1 July 2023 and duration is 5 years, calculate and output 2028-06-30.),
    "renewal_deadline": "YYYY-MM-DD" (Calculate based on the expiry date if it requires N months notice, or null if not found.),
    "key_terms": "1-sentence summary of the most important term or permitted use",
    "flags": "Any major risks, unusual clauses or Management Alerts"
  }}
]
Ensure the JSON is perfectly valid and is just the array. Do not output anything else.
Ensure you include EVERY specific document listed in the text."""
            try:
                resp = groq_client.chat.completions.create(
                    model='llama-3.3-70b-versatile',
                    messages=[{'role': 'user', 'content': prompt}],
                    temperature=0.0,
                    max_tokens=4000
                )
                raw = resp.choices[0].message.content.strip()
                raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
                result = json.loads(raw)
                
                for item in result:
                    matched_doc = next((d for d in docs if d.filename == item.get("filename")), None)
                    if matched_doc:
                        item["workspace_id"] = getattr(matched_doc, "workspace_id", None)
                        item["doc_id"] = getattr(matched_doc, "id", None)
                        
                yield f"data: {json.dumps({'status': 'complete', 'data': result})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Failed to analyse portfolio'})}\n\n"

    return StreamingResponse(generate_response(), media_type="text/event-stream")


class CompareRequest(BaseModel):
    doc_id_a: str
    doc_id_b: str

@app.post("/api/compare")
async def document_compare(payload: CompareRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if payload.doc_id_a == payload.doc_id_b:
        raise HTTPException(status_code=400, detail="Must select two different documents to compare")
        
    doc_texts = {}
    
    for doc_id in [payload.doc_id_a, payload.doc_id_b]:
        if current_user:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                models.WorkspaceDocument.pinecone_doc_id == doc_id,
                models.Workspace.firm_id == current_user.firm_id
            ).first()
        else:
            doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                models.WorkspaceDocument.pinecone_doc_id == doc_id,
                models.Workspace.session_id == x_session_id
            ).first()
            
        if not doc:
            raise HTTPException(status_code=403, detail=f"Access denied for document {doc_id}")
            
        file_path = f"./uploads/{doc_id}.md"
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Source markdown for {doc.filename} not found.")
            
        try:
            with open(file_path, "r") as f:
                doc_text = f.read()
            doc_texts[doc_id] = str(doc_text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to extract text from {doc.filename}: {str(e)}")

    full_text = f"--- DOCUMENT A START: {payload.doc_id_a} ---\n{doc_texts[payload.doc_id_a]}\n--- DOCUMENT B START: {payload.doc_id_b} ---\n{doc_texts[payload.doc_id_b]}"

    map_task = "Extract all material terms, obligations, and risk clauses from this section. Retain context of which document this belongs to (Document A or Document B)."
    reduce_task = """Produce a forensic redline diff of ADDED, MODIFIED, and DELETED provisions between the two documents. Flag any sections where comparison was limited by content quality.
JSON SCHEMA REQUIREMENT:
{
  "risk_summary": "A 2-3 sentence executive summary explaining how the risk profile has shifted from Document A to Document B.",
  "changes": [
    {
      "type": "ADDED",
      "original_text": null,
      "new_text": "Exact text added to Document B",
      "impact": "High/Med/Low impact: Short explanation of legal implication."
    },
    {
      "type": "DELETED",
      "original_text": "Exact text removed from Document A",
      "new_text": null,
      "impact": "High/Med/Low impact: Short explanation of legal implication."
    },
    {
      "type": "MODIFIED",
      "original_text": "Exact original clause in Document A",
      "new_text": "Exact new clause in Document B",
      "impact": "High/Med/Low impact: Short explanation of how the modification shifts obligation."
    }
  ]
}
Return ONLY the raw JSON object."""

    def legacy_op():
        doc_a_old = str(doc_texts[payload.doc_id_a])[:9000]
        doc_b_old = str(doc_texts[payload.doc_id_b])[:9000]
        prompt = f"""You are a master legal analyst conducting a forensic "redline" comparison between an original document and a modified draft. 
    
DOCUMENT A (Original / Base Document):
{doc_a_old}

DOCUMENT B (Modified / Counter-party Draft):
{doc_b_old}

INSTRUCTIONS:
Carefully compare the documents. Output a structured forensic difference report in valid JSON.
Ignore cosmetic or stylistic wording changes (like whitespace or font). Focus strictly on substantive legal/obligational changes.

JSON SCHEMA REQUIREMENT:
{{
  "risk_summary": "A 2-3 sentence executive summary explaining how the risk profile has shifted from Document A to Document B.",
  "changes": [
    {{
      "type": "ADDED",
      "original_text": null,
      "new_text": "Exact text added to Document B",
      "impact": "High/Med/Low impact: Short explanation of legal implication."
    }},
    {{
      "type": "DELETED",
      "original_text": "Exact text removed from Document A",
      "new_text": null,
      "impact": "High/Med/Low impact: Short explanation of legal implication."
    }},
    {{
      "type": "MODIFIED",
      "original_text": "Exact original clause in Document A",
      "new_text": "Exact new clause in Document B",
      "impact": "High/Med/Low impact: Short explanation of how the modification shifts obligation."
    }}
  ]
}}

Return ONLY the raw JSON object. Do not wrap in markdown code blocks."""
        resp = groq_client.chat.completions.create(
            model='llama-3.3-70b-versatile',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.0,
            max_tokens=4000
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r'^```[a-z]*\n?', '', raw).rstrip('`').strip()
        return json.loads(raw)

    return StreamingResponse(run_feature_gated_pipeline(full_text, map_task, reduce_task, legacy_op), media_type="text/event-stream")

class ChatRequest(BaseModel):
    doc_ids: List[str]
    query: str
    is_timeline: bool = False
    jurisdictions: List[str] = []
    is_firm_search: bool = False

@app.post("/api/chat")
async def chat_with_pdf(request: ChatRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    try:
        # Enforce freemium limit for anonymous users
        if not current_user:
            if not x_session_id:
                raise HTTPException(status_code=401, detail="Authentication or Session ID required")
                
            # Freemium cap: 3 queries for anonymous users, then prompt to register
            anon_session = db.query(models.AnonymousSession).filter(models.AnonymousSession.id == x_session_id).first()
            if not anon_session:
                anon_session = models.AnonymousSession(id=x_session_id, query_count=0)
                db.add(anon_session)
                db.commit()
            if anon_session.query_count >= 3:
                raise HTTPException(status_code=402, detail="limit_reached")
            anon_session.query_count += 1
            db.commit()


        # Verify access
        for doc_id in request.doc_ids:
            if current_user:
                doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                    models.WorkspaceDocument.pinecone_doc_id == doc_id,
                    models.Workspace.firm_id == current_user.firm_id
                ).first()
            else:
                doc = db.query(models.WorkspaceDocument).join(models.Workspace).filter(
                    models.WorkspaceDocument.pinecone_doc_id == doc_id,
                    models.Workspace.session_id == x_session_id
                ).first()
                
            if not doc:
                raise HTTPException(status_code=403, detail="Access denied for one or more documents")

        if not request.doc_ids and not request.jurisdictions and not request.is_firm_search:
            return {"answer": "Please upload a document or select a Knowledge Base to get started.", "context_used": 0}
        if request.is_timeline:
            # Override query to specifically hunt for dates and timeline events
            query_vec = get_embedding("dates, deadlines, chronological sequence of events, important milestones, timeline")
            chunks_per_doc = 15 # Cap slightly lower to prevent RAM OOM
        else:
            query_vec = get_embedding(request.query)
            # Rollback context window: max 12 chunks per file to strictly prevent Cross-Encoder PyTorch SIGKILL on 512MB RAM
            chunks_per_doc = max(4, 12 // len(request.doc_ids)) if request.doc_ids else 6
        
        # Search Pinecone for top matches from EACH selected document individually to ensure diverse cross-document context
        matches = []
        
        if request.is_firm_search:
            if not current_user or not current_user.firm_id:
                raise HTTPException(status_code=403, detail="Firm Precedent Search requires a registered firm account.")
            firm_response = index.query(
                vector=query_vec,
                top_k=20,
                include_metadata=True,
                filter={"firm_id": {"$eq": current_user.firm_id}}
            )
            matches.extend(firm_response.get('matches', []))
        else:
            for doc_id in request.doc_ids:
                query_response = index.query(
                    vector=query_vec,
                    top_k=chunks_per_doc,
                    include_metadata=True,
                    filter={"doc_id": {"$eq": doc_id}}
                )
                matches.extend(query_response.get('matches', []))
            
            # Regional Knowledge Base Sweeps (The Law)
            for jur in request.jurisdictions:
                jur_response = index.query(
                    vector=query_vec,
                    top_k=20, 
                    include_metadata=True,
                    filter={
                        "is_global": {"$eq": True},
                        "jurisdiction": {"$eq": jur}
                    }
                )
                matches.extend(jur_response.get('matches', []))
        
        if not matches:
            context = "No relevant context found in the document."
        else:
            # ── Rerank with cross-encoder for precision ───────────────────────
            query_text = request.query
            pairs = [(query_text, r.get('metadata', {}).get('text', '')) for r in matches]
            scores = reranker.predict(pairs)
            ranked = sorted(zip(scores, matches), key=lambda x: x[0], reverse=True)
            top_matches = [m for _, m in ranked[:12]]  # Keep best 12 chunks only (High-precision cutoff)

            # Force-anchor Page 1 definition contexts to bypass violent vector filtering failures
            page_one_anchors = []
            for doc_id in request.doc_ids:
                try:
                    md_path = f"./uploads/{doc_id}.md"
                    if os.path.exists(md_path):
                        with open(md_path, "r") as f:
                            p1_text = f.read(1500) # Load the absolutely critical opening definitions
                            if p1_text.strip():
                                # We lack the original filename trivially here, but the LLM knows it's the primary doc
                                page_one_anchors.append(f"[Critical Page 1 Definitions / Header]\n{p1_text}")
                except Exception:
                    pass
                    
            context_pieces = page_one_anchors.copy()
            
            for r in top_matches:
                m = r.get('metadata', {})
                piece = f"[{m.get('filename')}, Page {m.get('page')}]\n{m.get('text')}"
                context_pieces.append(piece)
            context = "\n\n---\n\n".join(context_pieces)
            
            # Safety cap to prevent Groq 6000 TPM rate limit crash
            if len(context) > 18000:
                context = context[:18000] + "\n...[Context Truncated for System Limits]"
                
        if request.is_timeline:
            system_prompt = (
                "You are an expert legal assistant. Your task is to extract every single date, deadline, "
                "or chronological event mentioned in the provided document context and construct a comprehensive Timeline.\n\n"
                "Format the output strictly as a Markdown Chronological Timeline. For example:\n"
                "**May 4th, 2024:** The defendant signed the initial contract. [contract.pdf, Page 2]\n\n"
                "Order the events from oldest to most recent. If no dates are found, state that no chronological events could be extracted. "
                "You MUST cite the source filename and page number for every event.\n\n"
                f"DOCUMENT CONTEXT:\n{context}"
            )
        else:
            system_prompt = (
                "You are a brilliant, highly analytical legal and real estate assistant (Real Estate Meta / REM). "
                "You are strictly prohibited from hallucinating or guessing outside the provided document context. "
                "You must answer questions based SOLELY on the provided documents; however, you ARE permitted to make direct logical deductions from the text. "
                "If the answer cannot be found or logically deduced from the provided context, you MUST state: 'I cannot answer this based on the provided documents.' "
                "You MUST explicitly cite the exact source of your answers at the end of each relevant claim, using the exact format: [Filename, Page X]. "
                "For example: 'The tenant signed the lease on May 4th [contract.pdf, Page 2].'\n\n"
                "CRITICAL INSTRUCTION: The user is a professional reviewing corporate documents, Shareholder Agreements, and Commercial Real Estate Leases. You must expertly analyze clauses, identities, liabilities, and terms. You MUST answer these questions fully and accurately based on the context.\n\n"
                "Be precise, objective, and maintain a professional tone. Do not provide prescriptive legal advice.\n\n"
                f"DOCUMENT CONTEXT:\n{context}"
            )
        
        def generate():
            response = groq_client.chat.completions.create(
                model='llama-3.3-70b-versatile', # Massive 70B reasoning engine, 30,000 TPM limit
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': request.query}
                ],
                stream=True
            )
            for chunk in response:
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
                    
        return StreamingResponse(generate(), media_type="text/event-stream")
        
        return StreamingResponse(generate(), media_type="text/event-stream")
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/document/{doc_id}")
async def get_document(doc_id: str):
    file_path = f"./uploads/{doc_id}.pdf"
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Document not found, it may have been deleted.")

class ExportDocxRequest(BaseModel):
    text: str

@app.post("/api/export_docx")
async def export_to_docx(request: ExportDocxRequest):
    try:
        doc = docx.Document()
        doc.add_heading('Lekkerpilot AI Draft', 0)
        
        # Super basic markdown text parsing for the Word Document
        for line in request.text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('# '):
                doc.add_heading(line[2:], level=1)
            elif line.startswith('## '):
                doc.add_heading(line[3:], level=2)
            elif line.startswith('### '):
                doc.add_heading(line[4:], level=3)
            elif line.startswith('- ') or line.startswith('* '):
                doc.add_paragraph(line[2:], style='List Bullet')
            else:
                doc.add_paragraph(line)
                
        # Save to buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        headers = {
            'Content-Disposition': 'attachment; filename="Lekkerpilot_Draft.docx"'
        }
        return Response(content=buffer.getvalue(), 
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
