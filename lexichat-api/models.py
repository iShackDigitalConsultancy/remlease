from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
import uuid

from sqlalchemy.orm import relationship
from database import Base
import datetime

class Firm(Base):
    __tablename__ = "firms"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    subscription_tier = Column(String, default="free")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    users = relationship("User", back_populates="firm")
    workspaces = relationship("Workspace", back_populates="firm")

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String, default="member") # admin, member
    firm_id = Column(String, ForeignKey("firms.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    firm = relationship("Firm", back_populates="users")

class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    firm_id = Column(String, ForeignKey("firms.id"), nullable=True)
    session_id = Column(String, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    firm = relationship("Firm", back_populates="workspaces")
    documents = relationship("WorkspaceDocument", back_populates="workspace", cascade="all, delete-orphan")
    notification_config = relationship("NotificationConfig", uselist=False, back_populates="workspace", cascade="all, delete-orphan")

class AnonymousSession(Base):
    __tablename__ = "anonymous_sessions"

    id = Column(String, primary_key=True, index=True)
    query_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class WorkspaceDocument(Base):
    __tablename__ = "workspace_documents"

    id = Column(String, primary_key=True, index=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"))
    pinecone_doc_id = Column(String, index=True)
    filename = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    workspace = relationship("Workspace", back_populates="documents")

class NotificationConfig(Base):
    __tablename__ = "notification_configs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id = Column(String, ForeignKey("workspaces.id"), unique=True, nullable=False)
    is_enabled = Column(Boolean, default=True)
    thresholds_days = Column(String, default="180,90,30")
    landlord_email = Column(String, nullable=True)
    franchisee_email = Column(String, nullable=True)
    franchisor_email = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    workspace = relationship("Workspace", back_populates="notification_config")

class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_id = Column(String, ForeignKey("workspace_documents.id"))
    threshold_days = Column(Integer)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    recipient_email = Column(String)
    status = Column(String, default="success")
    
    document = relationship("WorkspaceDocument")
