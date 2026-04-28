import os
import uuid
import time
import requests
from fastapi import HTTPException, BackgroundTasks, UploadFile
from sqlalchemy.orm import Session
from typing import Optional

from dependencies import UPLOAD_DIR, index
import models
from utils.chunking import smart_chunk
from services import intelligence_service
from services import vector_service

def process_document_background(doc_id: str, file_path_saved: str, filename: str, workspace_id: str, firm_id_meta: str):
    import time
    
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
            print(f"Invalid or corrupted PDF file during fallback extraction. {str(e)}")
            return
            
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
            return
            
    if not chunks_with_meta:
        print("Could not extract any text from the document.")
        return
        
    # Embed and store in Pinecone
    vectors_to_upsert = []
    texts = [c["text"] for c in chunks_with_meta]
    try:
        embeddings = vector_service.get_embeddings(texts)
        for idx, c_meta in enumerate(chunks_with_meta):
            vectors_to_upsert.append({
                "id": f"{doc_id}_{idx}",
                "values": embeddings[idx],
                "metadata": {
                    "doc_id": doc_id,
                    "filename": filename,
                    "page": c_meta["page"],
                    "text": c_meta["text"],
                    "is_global": False,
                    "jurisdiction": "none",
                    "firm_id": firm_id_meta
                }
            })
    except Exception as e:
        print(f"Embedding error: {e}")
        return
            
    if vectors_to_upsert:
        index.upsert(vectors=vectors_to_upsert)
        
    # Auto-generate structured document brief securely in the BACKGROUND to drastically cut upload latency
    sample_text = " ".join([c["text"] for c in chunks_with_meta[:15]])
    intelligence_service.analyze_document_brief_background(doc_id, filename, sample_text)


async def upload_pdf(workspace_id: str, background_tasks: BackgroundTasks, file: UploadFile, current_user: Optional[models.User], x_session_id: Optional[str], db: Session):
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

    # 1. Create DB record immediately
    db_doc = models.WorkspaceDocument(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        pinecone_doc_id=doc_id,
        filename=file.filename
    )
    db.add(db_doc)
    db.commit()

    # 2. Run background task
    background_tasks.add_task(
        process_document_background,
        doc_id=doc_id,
        file_path_saved=file_path_saved,
        filename=file.filename,
        workspace_id=workspace_id,
        firm_id_meta=firm_id_meta
    )

    # 3. Return immediately
    return {
        "message": "Upload started",
        "doc_id": doc_id,
        "filename": file.filename,
        "brief": None,
        "processing": True
    }
