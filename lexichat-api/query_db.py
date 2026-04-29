import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ['DATABASE_URL'] = 'postgresql+pg8000://postgres:MpxsytEYlyQXxgDDplPsyqYPUFptTOrA@nozomi.proxy.rlwy.net:13715/railway'
import sys
sys.path.append(os.path.dirname(__file__))

import models
from database import Base

engine = create_engine(os.environ['DATABASE_URL'])
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

user = db.query(models.User).filter_by(email='jack@bootlegger.co.za').first()
if user:
    import auth
    token = auth.create_access_token({"sub": user.email, "role": user.role, "firm_id": str(user.firm_id)})
    print("TOKEN_START", token, "TOKEN_END")
    
    docs = db.query(models.WorkspaceDocument).filter(models.WorkspaceDocument.filename.like('%Bootlegger%')).all()
    for d in docs:
        print(f"DOC_ID: {d.id} | NAME: {d.filename}")
else:
    print("USER NOT FOUND")
