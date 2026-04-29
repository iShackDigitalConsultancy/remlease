with open("old_main.py", "r") as f:
    lines = f.readlines()

def get_lines(start, end):
    return "".join(lines[start-1:end])

funcs = [
    get_lines(119, 159),   # analyze_document_brief
    get_lines(348, 354),   # analyze_document_brief_background
    get_lines(356, 378),   # get_document_brief
    get_lines(543, 632),   # document_audit (wait, look at lines. 543 is class AuditRequest. Let's just do 547 to 632)
    get_lines(547, 632),   # audit
    get_lines(637, 731),   # extract_timeline
    get_lines(736, 821),   # extract_expiries
    get_lines(826, 916),   # gap_analysis
    get_lines(918, 1045),  # portfolio_overview
    get_lines(1052, 1166), # document_compare
    get_lines(1175, 1336)  # chat_with_pdf
]

# Let's adjust to be safe and visually correct based on my earlier view_file outputs.
# I had a view empty line offset. Let me just use the actual code matching instead of magic lines to be 100% robust!
import re

with open("old_main.py", "r") as f:
    text = f.read()

def extract_func(name):
    # Match the function signature and EVERYTHING until the next `@app.` or `class ` or `if __name__` or `def ` at indentation level 0.
    match = re.search(r'(async def |def )' + name + r'\(.*?\)[\s\S]*?(?=\n(?:@app\.|class |def |async def |if __name__|$))', text)
    if not match: return ""
    return match.group(0)

names = [
    "analyze_document_brief",
    "analyze_document_brief_background",
    "get_document_brief",
    "document_audit",
    "extract_timeline",
    "extract_expiries",
    "gap_analysis",
    "portfolio_overview",
    "document_compare",
    "chat_with_pdf"
]

header = """import os
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

"""

with open("services/intelligence_service.py", "w") as f:
    f.write(header)
    for name in names:
        func = extract_func(name)
        func = func.replace('payload: AuditRequest, ', 'payload, ')
        func = func.replace('payload: TimelineExtractionRequest, ', 'payload, ')
        func = func.replace('payload: ExpiryExtractionRequest, ', 'payload, ')
        func = func.replace('payload: GapAnalysisRequest, ', 'payload, ')
        func = func.replace('payload: CompareRequest, ', 'payload, ')
        func = func.replace('request: ChatRequest, ', 'request, ')
        f.write(func + "\n\n")

print("Fixed intelligence_service.py")
