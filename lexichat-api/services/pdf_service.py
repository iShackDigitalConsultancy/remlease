from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, 
    Table, TableStyle, HRFlowable, 
    PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from io import BytesIO
from datetime import datetime

def safe(val):
    if val is None: return "-"
    if isinstance(val, dict): 
        return str(val)
    return str(val)

def _add_branding(canvas, doc):
    canvas.saveState()
    canvas.setFont('Helvetica-Bold', 10)
    canvas.setFillColorHex('#1a56db')
    canvas.drawString(cm, A4[1] - cm, "REM Leases")
    canvas.setFont('Helvetica', 10)
    canvas.setFillColorHex('#666666')
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    canvas.drawRightString(A4[0] - cm, A4[1] - cm, date_str)
    
    # Footer
    page_num = canvas.getPageNumber()
    canvas.drawCentredString(A4[0]/2, cm, str(page_num))
    canvas.restoreState()

def build_expiries_pdf(report_data, workspace_name, document_names) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=cm, leftMargin=cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#1a56db'), alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=12, alignment=TA_CENTER)
    
    story = []
    story.append(Paragraph("Global Expiry & Renewal Intelligence", title_style))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(workspace_name if workspace_name else "Portfolio", subtitle_style))
    story.append(Spacer(1, 1*cm))
    
    expiries = report_data.get("expiries", []) if isinstance(report_data, dict) else (report_data if isinstance(report_data, list) else [])
        
    for item in expiries:
        doc_name = item.get("document", "Unknown Document")
        story.append(Paragraph(f"<b>{doc_name}</b>", styles['Heading2']))
        story.append(Spacer(1, 0.2*cm))
        
        data = [
            ["Commencement", "Expiry Date", "Renewal Deadline"],
            [item.get("commencement", "-"), item.get("expiry_date", "-"), item.get("renewal_deadline", "-")]
        ]
        t = Table(data, colWidths=[5*cm, 5*cm, 5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a56db')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('GRID', (0,0), (-1,-1), 1, colors.lightgrey),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.5*cm))
        
        action_req = item.get("action_required", "-")
        story.append(Paragraph(f"<b>Action Required:</b> {action_req}", ParagraphStyle('Action', parent=styles['Normal'], backColor=colors.navajowhite, borderColor=colors.orange, borderWidth=1, borderPadding=5)))
        story.append(Spacer(1, 0.3*cm))
        
        clause = item.get("clause", "")
        if clause:
            story.append(Paragraph(f"<i>Governing Clause: {clause}</i>", styles['Normal']))
        story.append(Spacer(1, 1*cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        story.append(Spacer(1, 0.5*cm))
        
    doc.build(story, onFirstPage=_add_branding, onLaterPages=_add_branding)
    buffer.seek(0)
    return buffer

def build_fundamental_terms_pdf(report_data, workspace_name, document_names) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=cm, leftMargin=cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#1a56db'), alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=12, alignment=TA_CENTER)
    normal = styles['Normal']
    
    story = []
    story.append(Paragraph("Fundamental Terms", title_style))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(workspace_name if workspace_name else "Portfolio", subtitle_style))
    story.append(Spacer(1, 1*cm))
    
    ft = report_data.get("fundamental_terms", report_data if isinstance(report_data, dict) else {})
    
    # A) Parties table
    story.append(Paragraph("<b>Parties</b>", styles['Heading2']))
    lessor = ft.get("lessor", {})
    lessee = ft.get("lessee", {})
    parties_data = [
        ["Lessor", "Lessee"],
        [f"Name: {safe(lessor.get('name'))}", f"Name: {safe(lessee.get('name'))}"],
        [f"Registration: {safe(lessor.get('registration'))}", f"Registration: {safe(lessee.get('registration'))}"],
        [f"Representative: {safe(lessor.get('representative'))}", f"Representative: {safe(lessee.get('representative'))}"],
        [f"Domicilium: {safe(lessor.get('domicilium'))}", f"Domicilium: {safe(lessee.get('domicilium'))}"]
    ]
    t = Table(parties_data, colWidths=[9*cm, 9*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6)
    ]))
    story.append(t)
    story.append(Spacer(1, 0.5*cm))
    
    # B) Premises & Key Dates table
    story.append(Paragraph("<b>Premises & Key Dates</b>", styles['Heading2']))
    premises = ft.get("premises", {})
    premises_data = [
        ["Premises Description", safe(premises.get("description"))],
        ["Address", safe(premises.get("address"))],
        ["ERF", safe(premises.get("erf"))],
        ["Commencement Date", safe(ft.get("commencement_date"))],
        ["Expiry Date", safe(ft.get("expiry_date"))],
        ["Lease Period", safe(ft.get("lease_period"))],
        ["Renewal Option", safe(ft.get("renewal_option"))],
        ["Escalation Rate", safe(ft.get("escalation_rate"))],
        ["Permitted Use", safe(ft.get("permitted_use"))]
    ]
    t2 = Table(premises_data, colWidths=[6*cm, 12*cm])
    t2.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1,4), (1,4), colors.red),  # Expiry date value
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6)
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.5*cm))
    
    # C) Rental Schedule table
    rental_sched = ft.get("rental_schedule", [])
    if rental_sched:
        story.append(Paragraph("<b>Rental Schedule</b>", styles['Heading2']))
        rs_data = [["Period", "Monthly Amount", "Notes"]]
        for rs in rental_sched:
            rs_data.append([safe(rs.get("period")), safe(rs.get("monthly_amount")), safe(rs.get("notes"))])
            
        t3 = Table(rs_data, colWidths=[6*cm, 5*cm, 7*cm])
        t3.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('PADDING', (0,0), (-1,-1), 6)
        ]))
        story.append(t3)
        story.append(Spacer(1, 0.5*cm))
        
    # D) Special Conditions
    special_conds = ft.get("special_conditions", [])
    if special_conds:
        story.append(Paragraph("<b>Special Conditions</b>", styles['Heading2']))
        for cond in special_conds:
            story.append(Paragraph(f"• {safe(cond)}", normal))
        story.append(Spacer(1, 0.5*cm))
        
    # E) Franchise Terms
    franchise = ft.get("franchise_terms", {})
    if franchise:
        story.append(Paragraph("<b>Franchise Terms</b>", styles['Heading2']))
        f_data = [
            ["Commencement", safe(franchise.get("commencement_date"))],
            ["Expiry", safe(franchise.get("expiry_date"))],
            ["Term", safe(franchise.get("term_length"))],
            ["Upfront Fee", safe(franchise.get("upfront_license_fee"))],
            ["Fees", safe(franchise.get("monthly_franchise_fee"))]
        ]
        t4 = Table(f_data, colWidths=[6*cm, 12*cm])
        t4.setStyle(TableStyle([
            ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('PADDING', (0,0), (-1,-1), 6)
        ]))
        story.append(t4)
        story.append(Spacer(1, 0.5*cm))
    
    doc.build(story, onFirstPage=_add_branding, onLaterPages=_add_branding)
    buffer.seek(0)
    return buffer

def build_audit_pdf(report_data, workspace_name, document_names) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=cm, leftMargin=cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#1a56db'), alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=12, alignment=TA_CENTER)
    
    story = []
    story.append(Paragraph("Document Audit Report", title_style))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(workspace_name if workspace_name else "Portfolio", subtitle_style))
    story.append(Spacer(1, 1*cm))
    
    audit_items = report_data.get("audit_items", report_data.get("items", []))
    
    if not audit_items:
        data_str = safe(report_data)
        if len(data_str) > 3000:
            data_str = data_str[:3000] + "..."
        story.append(Paragraph(data_str, styles['Normal']))
    else:
        for item in audit_items:
            status = item.get("status", "").upper()
            bg_color = colors.lightgrey
            if status == "RISK": bg_color = colors.pink
            elif status == "WARNING": bg_color = colors.navajowhite
            elif status == "PASS": bg_color = colors.lightgreen
            
            # Status Badge row
            t = Table([[(Paragraph(f"<b>STATUS: {status}</b>", styles['Normal']),)]], colWidths=[18*cm])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), bg_color),
                ('BOX', (0,0), (-1,-1), 1, colors.grey),
                ('PADDING', (0,0), (-1,-1), 6)
            ]))
            story.append(t)
            story.append(Spacer(1, 0.1*cm))
            
            # Finding
            story.append(Paragraph(f"<b>Finding:</b> {safe(item.get('finding'))}", styles['Normal']))
            story.append(Spacer(1, 0.1*cm))
            # Clause
            story.append(Paragraph(f"<b>Clause Reference:</b> {safe(item.get('clause_reference'))}", styles['Normal']))
            story.append(Spacer(1, 0.1*cm))
            # Recommendation
            story.append(Paragraph(f"<b>Recommendation:</b> {safe(item.get('recommendation'))}", styles['Normal']))
            story.append(Spacer(1, 0.8*cm))
    
    doc.build(story, onFirstPage=_add_branding, onLaterPages=_add_branding)
    buffer.seek(0)
    return buffer

def build_compare_pdf(report_data, workspace_name, document_names) -> BytesIO:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=cm, leftMargin=cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, textColor=colors.HexColor('#1a56db'), alignment=TA_CENTER)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontName='Helvetica', fontSize=12, alignment=TA_CENTER)
    
    story = []
    story.append(Paragraph("Document Comparison Report", title_style))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(workspace_name if workspace_name else "Portfolio", subtitle_style))
    story.append(Spacer(1, 1*cm))
    
    differences = report_data.get("differences", report_data.get("items", []))
    
    if not differences:
        data_str = safe(report_data)
        if len(data_str) > 3000:
            data_str = data_str[:3000] + "..."
        story.append(Paragraph(data_str, styles['Normal']))
    else:
        for diff in differences:
            category = diff.get("category", "Difference")
            story.append(Paragraph(f"<b>{category}</b>", styles['Heading2']))
            
            doc_a_val = safe(diff.get("document_a_value", diff.get("doc_a", "")))
            doc_b_val = safe(diff.get("document_b_value", diff.get("doc_b", "")))
            
            # Paragraph formatting for table cells so they wrap
            p_a = Paragraph(doc_a_val, styles['Normal'])
            p_b = Paragraph(doc_b_val, styles['Normal'])
            
            t = Table([
                ["Document A", "Document B"],
                [p_a, p_b]
            ], colWidths=[9*cm, 9*cm])
            
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('VALIGN', (0,0), (-1,-1), 'TOP'),
                ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
                ('PADDING', (0,0), (-1,-1), 6)
            ]))
            story.append(t)
            story.append(Spacer(1, 0.1*cm))
            
            status = diff.get("status")
            if status:
                story.append(Paragraph(f"<i>Status: {status}</i>", styles['Normal']))
                
            story.append(Spacer(1, 0.8*cm))
    
    doc.build(story, onFirstPage=_add_branding, onLaterPages=_add_branding)
    buffer.seek(0)
    return buffer

def generate_pdf(report_type: str, report_data: dict, workspace_name: str, document_names: list) -> BytesIO:
    if report_type == "expiries":
        return build_expiries_pdf(report_data, workspace_name, document_names)
    elif report_type == "fundamental_terms":
        return build_fundamental_terms_pdf(report_data, workspace_name, document_names)
    elif report_type == "audit":
        return build_audit_pdf(report_data, workspace_name, document_names)
    elif report_type == "compare":
        return build_compare_pdf(report_data, workspace_name, document_names)
    else:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        doc.build([Paragraph(f"Unknown report type: {report_type}", getSampleStyleSheet()['Normal'])])
        buffer.seek(0)
        return buffer
