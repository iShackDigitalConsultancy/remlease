from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
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
