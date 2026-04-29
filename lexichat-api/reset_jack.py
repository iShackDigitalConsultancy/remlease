from sqlalchemy.orm import Session
from database import SessionLocal
import models
from auth import get_password_hash

def reset():
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "jack@bootlegger.co.za").first()
    if user:
        user.hashed_password = get_password_hash("123456789")
        db.commit()
        print("Password reset to 123456789")
    else:
        print("User not found")
    db.close()

reset()
