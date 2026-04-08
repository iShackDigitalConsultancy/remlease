import os
import sys
import uuid
import json
from dotenv import load_dotenv
from pinecone import Pinecone
from sentence_transformers import SentenceTransformer
from pypdf import PdfReader

load_dotenv()

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
if not PINECONE_API_KEY:
    print("Error: PINECONE_API_KEY environment variable not set.")
    sys.exit(1)

pc = Pinecone(api_key=PINECONE_API_KEY)
index_name = "lekkerpilot"
if index_name not in pc.list_indexes().names():
    from pinecone import ServerlessSpec
    print(f"Index {index_name} not found. Creating it...")
    pc.create_index(
        name=index_name,
        dimension=384,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1")
    )
index = pc.Index(index_name)
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

def ingest_knowledge_base(pdf_path: str, jurisdiction: str, doc_name: str):
    print(f"Ingesting knowledge base document: {pdf_path}")
    print(f"Jurisdiction: {jurisdiction}, Document Name: {doc_name}")
    
    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)
        
    doc_id = str(uuid.uuid4())
    vectors_to_upsert = []

    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        if not text:
            text = ""
        
        # Simple chunking
        words = text.split()
        chunk_size = 200
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            chunk_text = " ".join(chunk_words)
            if not chunk_text.strip():
                continue
                
            chunk_id = f"{doc_id}-p{page_num}-{i}"
            embedding = embedding_model.encode(chunk_text).tolist()
            
            metadata = {
                "doc_id": doc_id,
                "filename": doc_name,
                "page": page_num + 1,
                "text": chunk_text,
                "is_global": True,
                "jurisdiction": jurisdiction
            }
            vectors_to_upsert.append({
                "id": chunk_id,
                "values": embedding,
                "metadata": metadata
            })

    # Batch upsert to Pinecone
    batch_size = 100
    for i in range(0, len(vectors_to_upsert), batch_size):
        batch = vectors_to_upsert[i:i + batch_size]
        index.upsert(vectors=batch)
        print(f"Upserted batch {i//batch_size + 1}/{(len(vectors_to_upsert) + batch_size - 1)//batch_size}")
        
    print(f"Successfully ingested {len(vectors_to_upsert)} chunks for {doc_name} into jurisdiction '{jurisdiction}'.")

if __name__ == "__main__":
    docs_to_ingest = [
        {"path": "./knowledge_base/za/SAConstitution-web-eng.pdf", "name": "Constitution of the Republic of South Africa, 1996"},
        {"path": "./knowledge_base/za/CompaniesAct.pdf", "name": "Companies Act, 71 of 2008"},
        {"path": "./knowledge_base/za/NationalCreditAct.pdf", "name": "National Credit Act, 34 of 2005"},
        {"path": "./knowledge_base/za/LabourRelationsAct.pdf", "name": "Labour Relations Act, 66 of 1995"},
        {"path": "./knowledge_base/za/BasicConditionsOfEmploymentAct.pdf", "name": "Basic Conditions of Employment Act, 75 of 1997"},
        {"path": "./knowledge_base/za/UniformRulesOfCourt.pdf", "name": "Uniform Rules of Court (High Court)"},
    ]
    for d in docs_to_ingest:
        ingest_knowledge_base(d["path"], "za", d["name"])

