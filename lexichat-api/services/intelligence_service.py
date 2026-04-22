import os
import json
import re
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from dependencies import UPLOAD_DIR, groq_client, index, vo
import models
from sqlalchemy.orm import Session
from fastapi import Depends, Header
from typing import List, Optional
from services.map_reduce import run_feature_gated_pipeline
from auth import get_current_user_optional
from database import get_db

def get_embedding(text: str):
    return vo.embed([text], model="voyage-law-2").embeddings[0]

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


def analyze_document_brief_background(doc_id: str, filename: str, sample_text: str):
    try:
        brief = analyze_document_brief(doc_id, filename, sample_text)
        with open(os.path.join(UPLOAD_DIR, f"{doc_id}_brief.json"), "w") as f:
            json.dump(brief, f)
    except Exception as e:
        print(f"Background brief extraction failed: {e}")


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
        
    file_path = os.path.join(UPLOAD_DIR, f"{doc_id}_brief.json")
    if not os.path.exists(file_path):
        return {"brief": None}
        
    with open(file_path, "r") as f:
        brief = json.load(f)
    return {"brief": brief}


async def document_audit(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
    file_path = os.path.join(UPLOAD_DIR, f"{payload.doc_id}.md")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Underlying document markdown file not found")
        
    try:
        with open(file_path, "r") as f:
            full_text = f.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read local document: {str(e)}")

    map_task = f"Extract all policy clauses, compliance obligations, and risk provisions from this section."
    reduce_task = f"""Produce a structured audit report flagging all compliance risks and policy gaps against this strictly provided policy:

async def extract_timeline(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.md")
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

async def extract_expiries(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.md")
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

async def gap_analysis(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.md")
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
        file_path = os.path.join(UPLOAD_DIR, f"{doc.pinecone_doc_id}.md")
        if not os.path.exists(file_path):
            file_path = os.path.join(UPLOAD_DIR, f"{doc.id}.md")
            
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

async def document_compare(payload, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            
        file_path = os.path.join(UPLOAD_DIR, f"{doc_id}.md")
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

async def chat_with_pdf(request, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
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
            query_text = request.query
            candidates = [r.get('metadata', {}).get('text', '') for r in matches]
            reranked = vo.rerank(query_text, candidates, model="rerank-2", top_k=12)
            top_matches = [matches[r.index] for r in reranked.results]

            # Force-anchor Page 1 definition contexts to bypass violent vector filtering failures
            page_one_anchors = []
            for doc_id in request.doc_ids:
                try:
                    md_path = os.path.join(UPLOAD_DIR, f"{doc_id}.md")
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


