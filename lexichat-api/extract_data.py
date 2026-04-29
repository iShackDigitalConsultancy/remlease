import re

with open("main.py", "r") as f:
    text = f.read()

def extract_func(name):
    # Match the function signature and EVERYTHING until the next `@app.` or `class ` or `if __name__` or `def ` at indentation level 0.
    match = re.search(r'(async def |def )' + name + r'\(.*?\)[\s\S]*?(?=\n(?:@app\.|class |def |async def |if __name__|$))', text)
    if not match: return ""
    return match.group(0)

names = [
    "signup",
    "login",
    "get_workspaces",
    "create_workspace",
    "rename_workspace",
    "delete_workspace",
    "rename_document",
    "delete_document",
    "get_document"
]

header = """import os
import uuid
import json
from fastapi import HTTPException, Depends, Header, status
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from dependencies import UPLOAD_DIR, index
import models
from sqlalchemy.orm import Session
from typing import List, Optional
from auth import get_current_user_optional, get_password_hash, create_access_token, verify_password
from database import get_db

"""

with open("services/data_service.py", "w") as f:
    f.write(header)
    for name in names:
        func = extract_func(name)
        # Strip strongly typed Pydantic payloads so FastAPI parses them in main.py, and data_service just takes the object
        func = func.replace('user: UserCreate, ', 'user, ')
        func = func.replace('request: WorkspaceRenameRequest, ', 'request, ')
        func = func.replace('request: DocumentRenameRequest, ', 'request, ')
        f.write(func + "\n\n")

print("Created data_service.py")
