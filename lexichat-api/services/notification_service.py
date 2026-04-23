import json
import os
import datetime
from sqlalchemy.orm import Session
from fastapi import HTTPException
import httpx
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

def send_brevo_email(recipient_email: str, recipient_name: str, subject: str, html_content: str):
    api_key = os.environ.get("BREVO_API_KEY")
    sender_email = os.environ.get("BREVO_SENDER_EMAIL")
    
    if not api_key or not sender_email:
        print("Missing Brevo credentials in environment.")
        return False
        
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "sender": {"name": "REM Leases Alerts", "email": sender_email},
        "to": [{"email": recipient_email, "name": recipient_name}],
        "subject": subject,
        "htmlContent": html_content
    }
    
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Failed to send Brevo email to {recipient_email}: {e}")
        return False

def build_expiry_email(expiry_data, days_remaining, workspace_name, document_context):
    if days_remaining <= 30:
        bg_color = "#fee2e2"
        text_color = "#991b1b"
    elif days_remaining <= 90:
        bg_color = "#ffedd5"
        text_color = "#9a3412"
    else:
        bg_color = "#fef9c3"
        text_color = "#854d0e"
        
    if days_remaining <= 0:
        banner_text = "URGENT: Lease has expired"
        bg_color = "#fee2e2"
        text_color = "#991b1b"
    else:
        banner_text = f"Action Required: {days_remaining} days until lease expiry"
        
    location = document_context.get("location", "Unknown Location")
    parties = document_context.get("parties", [])
    parties_html = "".join([f"<li><strong>{p.get('role', 'Party')}:</strong> {p.get('name', 'Unknown')}</li>" for p in parties])
    if not parties_html:
        parties_html = "<li>No parties listed.</li>"
        
    commencement = expiry_data.get("commencement_date", "Not specified")
    renewal = expiry_data.get("renewal_deadline", "Not specified")
    expiry = expiry_data.get("expiry_date", "Not specified")
    
    clause_text = expiry_data.get('clause_text', '') or expiry_data.get('clause_reference', 'No clause text provided.')
    action_req = expiry_data.get('action_required', 'Review lease terms immediately.')
    
    html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; color: #333;">
        <h2 style="color: #1e40af; border-bottom: 2px solid #1e40af; padding-bottom: 10px;">REM Leases — Lease Renewal Alert</h2>
        
        <div style="background-color: {bg_color}; color: {text_color}; padding: 15px; border-radius: 6px; font-weight: bold; margin-bottom: 20px; text-align: center;">
            {banner_text}
        </div>
        
        <div style="margin-bottom: 20px;">
            <h3 style="color: #1f2937; margin-bottom: 5px;">Property Details</h3>
            <p style="margin: 0;"><strong>Location:</strong> {location}</p>
            <p style="margin: 5px 0 0 0;"><strong>Workspace:</strong> {workspace_name}</p>
        </div>
        
        <div style="margin-bottom: 20px;">
            <h3 style="color: #1f2937; margin-bottom: 5px;">Parties Involved</h3>
            <ul style="margin: 0; padding-left: 20px;">
                {parties_html}
            </ul>
        </div>
        
        <div style="margin-bottom: 20px;">
            <h3 style="color: #1f2937; margin-bottom: 5px;">Key Dates</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr>
                    <td style="padding: 8px; border: 1px solid #e5e7eb;"><strong>Commencement Date</strong></td>
                    <td style="padding: 8px; border: 1px solid #e5e7eb;">{commencement}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #e5e7eb; background-color: #ffedd5;"><strong>Renewal Deadline</strong></td>
                    <td style="padding: 8px; border: 1px solid #e5e7eb; background-color: #ffedd5;">{renewal}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; border: 1px solid #e5e7eb; background-color: #fee2e2;"><strong>Expiry Date</strong></td>
                    <td style="padding: 8px; border: 1px solid #e5e7eb; background-color: #fee2e2;">{expiry}</td>
                </tr>
            </table>
        </div>
        
        <div style="margin-bottom: 20px;">
            <h3 style="color: #1f2937; margin-bottom: 5px;">Governing Clause</h3>
            <blockquote style="border-left: 4px solid #9ca3af; margin: 0; padding-left: 15px; font-style: italic; color: #4b5563;">
                {clause_text}
            </blockquote>
        </div>
        
        <div style="margin-bottom: 30px;">
            <h3 style="color: #1f2937; margin-bottom: 5px;">Action Required</h3>
            <p style="margin: 0;"><strong>{action_req}</strong></p>
        </div>
        
        <div style="text-align: center; margin-bottom: 30px;">
            <a href="https://rem-leases.vercel.app" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Open REM Leases Platform</a>
        </div>
        
        <div style="font-size: 12px; color: #6b7280; border-top: 1px solid #e5e7eb; padding-top: 15px; text-align: center;">
            <p style="margin: 0;">This is an automated alert from REM Leases.</p>
            <p style="margin: 5px 0 0 0;">Manage your notification settings at <a href="https://rem-leases.vercel.app" style="color: #2563eb;">rem-leases.vercel.app</a></p>
        </div>
    </div>
    """
    return html

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
        document_context = data.get("document_context", {})
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
            
            doc = db.query(models.WorkspaceDocument).filter(
                models.WorkspaceDocument.workspace_id == workspace.id,
                models.WorkspaceDocument.filename == exp.get("document", "")
            ).first()
            if doc:
                doc_id = doc.id
            
            trigger_threshold = None
            if days_remaining <= 0:
                trigger_threshold = 0
            else:
                for threshold in thresholds:
                    if (threshold - 7) < days_remaining <= threshold:
                        trigger_threshold = threshold
                        break
                        
            if trigger_threshold is not None:
                log_entry = db.query(models.NotificationLog).filter(
                    models.NotificationLog.doc_id == doc_id,
                    models.NotificationLog.threshold_days == trigger_threshold
                ).first()
                
                if not log_entry:
                    html_body = build_expiry_email(exp, days_remaining, workspace.name, document_context)
                    
                    if days_remaining <= 0:
                        subject = f"URGENT: Lease has expired — {workspace.name}"
                    else:
                        subject = f"Action Required: Lease expiring in {days_remaining} days — {workspace.name}"
                        
                    recipients = []
                    if config.landlord_email: recipients.append(("Landlord", config.landlord_email))
                    if config.franchisee_email: recipients.append(("Franchisee", config.franchisee_email))
                    if config.franchisor_email: recipients.append(("Franchisor", config.franchisor_email))
                    
                    sent_count = 0
                    for r_name, r_email in recipients:
                        success = send_brevo_email(r_email, r_name, subject, html_body)
                        if success:
                            sent_count += 1
                            
                    new_log = models.NotificationLog(
                        doc_id=doc_id,
                        threshold_days=trigger_threshold,
                        recipient_email=f"L:{config.landlord_email},F:{config.franchisee_email},FR:{config.franchisor_email}"
                    )
                    db.add(new_log)
                    
                    if sent_count > 0:
                        notified += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
    
    db.commit()
    return {"checked": checked, "notified": notified, "skipped": skipped}
