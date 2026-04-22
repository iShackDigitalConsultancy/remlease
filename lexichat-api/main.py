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
from services import data_service

models.Base.metadata.create_all(bind=engine)

from pinecone import Pinecone, ServerlessSpec
from groq import Groq
import uuid
import os
import io
import json
import requests
import time
import re

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
    return data_service.signup(user, x_session_id, db)

@app.post("/api/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return data_service.login(form_data, db)

@app.get("/api/workspaces")
def get_workspaces(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.get_workspaces(current_user, x_session_id, db)

@app.post("/api/workspaces")
def create_workspace(name: str = Form(...), current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.create_workspace(name, current_user, x_session_id, db)

class WorkspaceRenameRequest(BaseModel):
    name: str

@app.put("/api/workspaces/{ws_id}")
def rename_workspace(ws_id: str, request: WorkspaceRenameRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.rename_workspace(ws_id, request, current_user, x_session_id, db)

@app.delete("/api/workspaces/{ws_id}")
def delete_workspace(ws_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.delete_workspace(ws_id, current_user, x_session_id, db)

class DocumentRenameRequest(BaseModel):
    name: str

@app.put("/api/documents/{doc_id}")
def rename_document(doc_id: str, request: DocumentRenameRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.rename_document(doc_id, request, current_user, x_session_id, db)

@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.delete_document(doc_id, current_user, x_session_id, db)

# Background tasks proxy
def analyze_document_brief_background(doc_id: str, filename: str, sample_text: str):
    intelligence_service.analyze_document_brief_background(doc_id, filename, sample_text)

@app.get("/api/documents/{doc_id}/brief")
def get_document_brief(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return intelligence_service.get_document_brief(doc_id, current_user, x_session_id, db)

@app.post("/api/upload/{workspace_id}")
async def upload_pdf(workspace_id: str, background_tasks: BackgroundTasks, file: UploadFile = File(...), current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    from services import ingestion_service
    return await ingestion_service.upload_pdf(workspace_id, background_tasks, file, current_user, x_session_id, db)

class AuditRequest(BaseModel):
    doc_id: str
    policy: str
    force_refresh: bool = False

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
    force_refresh: bool = False

@app.post("/api/extract-expiries")
async def extract_expiries(payload: ExpiryExtractionRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.extract_expiries(payload, current_user, x_session_id, db)

class GapAnalysisRequest(BaseModel):
    doc_ids: List[str]
    force_refresh: bool = False

@app.post("/api/gap-analysis")
async def gap_analysis(payload: GapAnalysisRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.gap_analysis(payload, current_user, x_session_id, db)

@app.get("/api/portfolio-overview")
async def portfolio_overview(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await intelligence_service.portfolio_overview(current_user, x_session_id, db)


class CompareRequest(BaseModel):
    doc_id_a: str
    doc_id_b: str
    force_refresh: bool = False

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
async def get_document(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return await data_service.get_document(doc_id, current_user, x_session_id, db)

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
    from services import admin_service
    return admin_service.migrate_voyage_admin(request, request_headers, db)

class ResetPineconeRequest(BaseModel):
    pass

@app.post("/api/admin/reset-pinecone")
def reset_pinecone_admin(
    request_headers: Request
):
    from services import admin_service
    return admin_service.reset_pinecone_admin(request_headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
