import uuid
from sqlalchemy.orm import Session
from database import engine, SessionLocal
import models
from auth import get_password_hash

# Ensure tables are created
models.Base.metadata.create_all(bind=engine)

def seed_users():
    db: Session = SessionLocal()
    
    users_to_create = [
        {"email": "superadmin@example.com", "full_name": "Super Admin User", "role": "Super Admin", "password": "123456789"},
        {"email": "portfolio@example.com", "full_name": "Portfolio Manager User", "role": "Portfolio Manager", "password": "123456789"},
    ]
    
    users_to_delete = [
        "scheme@example.com",
        "resident@example.com",
        "guard@example.com"
    ]
    
    try:
        # Delete unwanted users safely
        for email in users_to_delete:
            user = db.query(models.User).filter(models.User.email == email).first()
            if user:
                print(f"Deleting mistakenly added user {email}...")
                db.delete(user)
        
        # Create or update wanted users
        for u in users_to_create:
            existing_user = db.query(models.User).filter(models.User.email == u["email"]).first()
            if not existing_user:
                print(f"Creating user {u['email']} with role {u['role']}...")
                hashed = get_password_hash(u["password"])
                
                firm_id = str(uuid.uuid4())
                new_firm = models.Firm(id=firm_id, name=f"{u['role']} Firm")
                db.add(new_firm)
                
                new_user = models.User(
                    id=str(uuid.uuid4()),
                    email=u["email"],
                    full_name=u["full_name"],
                    hashed_password=hashed,
                    role=u["role"],
                    firm_id=firm_id
                )
                db.add(new_user)
            else:
                print(f"User {u['email']} already exists. Updating role...")
                existing_user.role = u['role']
                
        db.commit()
        print("Done seeding access control users!")
    except Exception as e:
        print(f"Error seeding users: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_users()
