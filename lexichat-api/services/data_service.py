import os
import uuid
import json
import glob
from fastapi import HTTPException, Depends, Header, status, Form
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from dependencies import UPLOAD_DIR, index
import models
from sqlalchemy.orm import Session
from typing import List, Optional
from auth import get_current_user_optional, get_password_hash, create_access_token, verify_password
from database import get_db

def signup(user, x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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


def rename_workspace(ws_id: str, request, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.firm_id == current_user.firm_id).first()
    else:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.session_id == x_session_id).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    workspace.name = request.name
    db.commit()
    return {"id": workspace.id, "name": workspace.name}


def delete_workspace(ws_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if current_user:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.firm_id == current_user.firm_id).first()
    else:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == ws_id, models.Workspace.session_id == x_session_id).first()
    
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
        
    docs = db.query(models.WorkspaceDocument).filter(models.WorkspaceDocument.workspace_id == workspace.id).all()
    for doc in docs:
        try:
            index.delete(ids=[doc.pinecone_doc_id], namespace="")
        except Exception:
            pass
            
        for ext in [".md", ".pdf", "_brief.json"]:
            file_path = os.path.join(UPLOAD_DIR, f"{doc.pinecone_doc_id}{ext}")
            if os.path.exists(file_path):
                os.remove(file_path)
                
        for cache_file in glob.glob(os.path.join(UPLOAD_DIR, f"{doc.workspace_id}_*.json")):
            if os.path.exists(cache_file):
                os.remove(cache_file)
                
        db.query(models.NotificationLog).filter(models.NotificationLog.doc_id == doc.id).delete(synchronize_session=False)
        db.delete(doc)
        
    db.query(models.NotificationConfig).filter(models.NotificationConfig.workspace_id == workspace.id).delete(synchronize_session=False)
    db.flush()
    db.delete(workspace)
    db.commit()
    return {"message": "Workspace deleted successfully"}


def rename_document(doc_id: str, request, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
        index.delete(ids=[doc.pinecone_doc_id], namespace="")
    except Exception as e:
        print(f"Pinecone delete warning (non-fatal): {e}")

    # Remove the uploaded files from disk
    for ext in [".md", ".pdf", "_brief.json"]:
        file_path = os.path.join(UPLOAD_DIR, f"{doc.pinecone_doc_id}{ext}")
        if os.path.exists(file_path):
            os.remove(file_path)
            
    for cache_file in glob.glob(os.path.join(UPLOAD_DIR, f"{doc.workspace_id}_*.json")):
        if os.path.exists(cache_file):
            os.remove(cache_file)

    # Remove associated notification logs to prevent foreign key errors
    db.query(models.NotificationLog).filter(models.NotificationLog.doc_id == doc.id).delete(synchronize_session=False)

    # Remove the DB record
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted"}

# Background tasks proxy

async def get_document(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    if not current_user and not x_session_id:
        raise HTTPException(status_code=403, detail="Access denied")

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

    file_path = os.path.join(UPLOAD_DIR, f"{doc.pinecone_doc_id}.pdf")
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/pdf")
    raise HTTPException(status_code=404, detail="Document not found, it may have been deleted.")


