import re

with open("main.py", "r") as f:
    text = f.read()

# Add import services.data_service at the top
text = text.replace("from services import intelligence_service\n", "from services import intelligence_service\nfrom services import data_service\n")

# Replace signup
stub_signup = """@app.post("/api/auth/signup")
def signup(user: UserCreate, x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.signup(user, x_session_id, db)
"""
text = re.sub(r'@app\.post\("/api/auth/signup"\)\ndef signup\(.*?return \{"message": "User created successfully"\}\n', stub_signup, text, flags=re.DOTALL)

# Replace login
stub_login = """@app.post("/api/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    return data_service.login(form_data, db)
"""
text = re.sub(r'@app\.post\("/api/auth/login"\)\ndef login\(.*?return \{"access_token": access_token, "token_type": "bearer", "user": \{"id": user\.id, "email": user\.email, "full_name": user\.full_name, "firm_id": user\.firm_id, "role": user\.role\}\}\n', stub_login, text, flags=re.DOTALL)

# Replace get_workspaces
stub_get_workspaces = """@app.get("/api/workspaces")
def get_workspaces(current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.get_workspaces(current_user, x_session_id, db)
"""
text = re.sub(r'@app\.get\("/api/workspaces"\)\ndef get_workspaces\(.*?return result\n', stub_get_workspaces, text, flags=re.DOTALL)

# Replace create_workspace
stub_create_workspace = """@app.post("/api/workspaces")
def create_workspace(name: str = Form(...), current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.create_workspace(name, current_user, x_session_id, db)
"""
text = re.sub(r'@app\.post\("/api/workspaces"\)\ndef create_workspace\(.*?return \{"id": ws_id, "name": name, "documents": \[\]\}\n', stub_create_workspace, text, flags=re.DOTALL)

# Replace rename_workspace
stub_rename_workspace = """@app.put("/api/workspaces/{ws_id}")
def rename_workspace(ws_id: str, request: WorkspaceRenameRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.rename_workspace(ws_id, request, current_user, x_session_id, db)
"""
text = re.sub(r'@app\.put\("/api/workspaces/\{ws_id\}"\)\ndef rename_workspace\(.*?return \{"id": workspace\.id, "name": workspace\.name\}\n', stub_rename_workspace, text, flags=re.DOTALL)

# Replace delete_workspace
stub_delete_workspace = """@app.delete("/api/workspaces/{ws_id}")
def delete_workspace(ws_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.delete_workspace(ws_id, current_user, x_session_id, db)
"""
text = re.sub(r'@app\.delete\("/api/workspaces/\{ws_id\}"\)\ndef delete_workspace\(.*?return \{"message": "Deleted"\}\n', stub_delete_workspace, text, flags=re.DOTALL)

# Replace rename_document
stub_rename_document = """@app.put("/api/documents/{doc_id}")
def rename_document(doc_id: str, request: DocumentRenameRequest, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.rename_document(doc_id, request, current_user, x_session_id, db)
"""
text = re.sub(r'@app\.put\("/api/documents/\{doc_id\}"\)\ndef rename_document\(.*?return \{"message": "Renamed", "name": doc\.filename\}\n', stub_rename_document, text, flags=re.DOTALL)

# Replace delete_document
stub_delete_document = """@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: str, current_user: Optional[models.User] = Depends(get_current_user_optional), x_session_id: Optional[str] = Header(None), db: Session = Depends(get_db)):
    return data_service.delete_document(doc_id, current_user, x_session_id, db)
"""
text = re.sub(r'@app\.delete\("/api/documents/\{doc_id\}"\)\ndef delete_document\(.*?return \{"message": "Document deleted"\}\n', stub_delete_document, text, flags=re.DOTALL)

# Replace get_document
stub_get_document = """@app.get("/api/document/{doc_id}")
async def get_document(doc_id: str):
    return await data_service.get_document(doc_id)
"""
text = re.sub(r'@app\.get\("/api/document/\{doc_id\}"\)\nasync def get_document\(doc_id: str\):.*?raise HTTPException\(status_code=404, detail="Document not found, it may have been deleted\."\)\n', stub_get_document, text, flags=re.DOTALL)

with open("main.py", "w") as f:
    f.write(text)

print("Updated main.py")
