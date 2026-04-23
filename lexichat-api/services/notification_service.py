import json
import os
import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
import models
from dependencies import UPLOAD_DIR

def get_notification_config(workspace_id: str, db: Session):
    config = db.query(models.NotificationConfig).filter(models.NotificationConfig.workspace_id == workspace_id).first()
    if config:
        return config
    return {
        "is_enabled": False,
        "thresholds_days": "180,90,30",
        "landlord_email": None,
        "franchisee_email": None,
        "franchisor_email": None
    }

def update_notification_config(workspace_id: str, payload, db: Session):
    config = db.query(models.NotificationConfig).filter(models.NotificationConfig.workspace_id == workspace_id).first()
    if not config:
        config = models.NotificationConfig(workspace_id=workspace_id)
        db.add(config)
    
    config.is_enabled = payload.is_enabled
    config.thresholds_days = payload.thresholds_days
    config.landlord_email = payload.landlord_email
    config.franchisee_email = payload.franchisee_email
    config.franchisor_email = payload.franchisor_email
    
    db.commit()
    db.refresh(config)
    return config

def trigger_expiry_alerts(db: Session):
    configs = db.query(models.NotificationConfig).filter(models.NotificationConfig.is_enabled == True).all()
    
    checked = 0
    notified = 0
    skipped = 0
    
    for config in configs:
        workspace = db.query(models.Workspace).filter(models.Workspace.id == config.workspace_id).first()
        if not workspace:
            continue
            
        cache_path = os.path.join(UPLOAD_DIR, f"{workspace.id}_extract_expiries.json")
        if not os.path.exists(cache_path):
            continue
            
        try:
            with open(cache_path, "r") as f:
                data = json.load(f)
        except Exception:
            continue
            
        expiries = data.get("expiries", [])
        thresholds = [int(t.strip()) for t in config.thresholds_days.split(",") if t.strip().isdigit()]
        
        for exp in expiries:
            checked += 1
            deadline_str = exp.get("expiry_date") or exp.get("renewal_deadline")
            if not deadline_str or deadline_str == "null":
                continue
                
            try:
                deadline_date = datetime.datetime.strptime(deadline_str, "%Y-%m-%d").date()
            except ValueError:
                continue
                
            days_remaining = (deadline_date - datetime.datetime.utcnow().date()).days
            doc_id = "unknown"
            
            # Find doc_id from filename (if possible) or just search by filename
            doc = db.query(models.WorkspaceDocument).filter(
                models.WorkspaceDocument.workspace_id == workspace.id,
                models.WorkspaceDocument.filename == exp.get("document")
            ).first()
            if doc:
                doc_id = doc.id
            
            for threshold in thresholds:
                if (threshold - 7) < days_remaining <= threshold:
                    # Check log
                    log_entry = db.query(models.NotificationLog).filter(
                        models.NotificationLog.doc_id == doc_id,
                        models.NotificationLog.threshold_days == threshold
                    ).first()
                    
                    if not log_entry:
                        print(f"Would send email to Landlord: {config.landlord_email}, Franchisee: {config.franchisee_email}, Franchisor: {config.franchisor_email}")
                        new_log = models.NotificationLog(
                            doc_id=doc_id,
                            threshold_days=threshold,
                            recipient_email=f"L:{config.landlord_email},F:{config.franchisee_email},FR:{config.franchisor_email}"
                        )
                        db.add(new_log)
                        notified += 1
                    else:
                        skipped += 1
    
    db.commit()
    return {"checked": checked, "notified": notified, "skipped": skipped}
