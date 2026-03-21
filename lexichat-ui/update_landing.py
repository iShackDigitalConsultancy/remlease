import os
import re

filepath = "/Users/wdbmacminipro/Desktop/REM-Leases/lexichat-ui/src/App.jsx"
with open(filepath, "r", encoding="utf-8") as file:
    content = file.read()

replacements = {
    # 1. Landing Page (Hero Section)
    "LEKKER FAST. DEAD ACCURATE. ENTERPRISE LOCKED DOWN.": "LEKKER FAST. DEAD ACCURATE. PORTFOLIO READY.",
    "Your documents have answers.<br />Stop digging. Start asking.": "Your leases have answers.<br />Stop digging through filing cabinets. Start asking.",
    "REM-Leases reads contracts, briefs and pleadings the way you wish your junior could — in seconds, not hours.": "lease.realestatemeta.ai reads your entire lease portfolio the way you wish your property manager could — in seconds, not days. Upload any lease. Ask any question. Get answers with clause references you can verify.",
    "Upload your first document — it's free": "Upload your first lease — it's free",
    "No credit card. No setup. Just answers.": "No credit card. No setup. Just answers.",
    
    # Drop Zone Text
    "No sign-up needed. Upload any brief, contract, or pleading and start asking questions immediately.": "No sign-up needed. Upload any residential or commercial lease and start asking questions immediately.",
    "Trusted by litigation, conveyancing and corporate counsel teams who bill by the hour — and hate wasting them.": "Trusted by landlords, asset managers and property professionals who manage portfolios — not paperwork.",
    
    # Features Page header string
    "Three things REM-Leases does<br />that change how you work.": "Three things that change how you manage your leases.",
    "Purpose-built for legal. Not repurposed from somewhere else.": "Purpose-built for property. Not repurposed from a legal tool.",
    
    # Feature 1
    "Instant document analysis": "Instant Lease Analysis",
    "Drop a 200-page contract. Get answers in 30 seconds.": "Drop a 200-page lease. Get answers in 30 seconds.",
    "Upload any brief, lease, SPA, or set of pleadings. REM-Leases extracts every clause, obligation, deadline and red flag — then lets you interrogate the document like it's on the stand.": "Upload any residential lease, commercial lease, or addendum. RealEstateMeta extracts every clause, obligation, escalation formula, critical date and red flag — then lets you interrogate the document like you wrote it yourself.",
    "\"Clause extraction and categorisation\",\"Obligation and deadline mapping\",\"Risk and anomaly flagging\",\"Natural language Q&A across the full document\"": "\"Clause extraction and categorisation\",\"Escalation and renewal date mapping\",\"Obligation and liability flagging\",\"Natural language Q&A across the full document\"",
    
    # Feature 2
    "Precedent discovery": "Portfolio Intelligence",
    "Precedent at your fingertips, not buried in a filing cabinet.": "See your entire lease book at a glance. Not one lease at a time.",
    "Surface relevant case law and comparable clauses across your entire document library. What used to take a candidate attorney three days now takes three clicks.": "Surface patterns, risks and opportunities across your entire portfolio. Which tenants have below-market escalations? Which leases expire in Q1? Where are your maintenance obligations heaviest? What used to take a week of spreadsheet work now takes three clicks.",
    "\"Cross-reference clauses against your document library\",\"Surface comparable terms from prior matters\",\"Pattern detection across contract portfolios\",\"Citation and source linking for every result\"": "\"Cross-reference clauses across your full portfolio\",\"Surface expiring leases and upcoming renewal windows\",\"Compare escalation terms across tenants\",\"Flag inconsistencies and non-standard clauses\"",
    
    # Feature 3
    "Enterprise security": "Enterprise Security",
    "Your client's secrets stay secret. Full stop.": "Your tenant data stays yours. Full stop.",
    "Bank-grade encryption, SOC 2 compliance-ready architecture, and zero data retention on third-party models. Your client's privileged information stays exactly that — privileged.": "POPIA-compliant architecture, end-to-end encryption, and zero data retention on third-party models. Your lease documents contain sensitive commercial and personal information — we treat them accordingly.",
    "\"End-to-end encryption at rest and in transit\",\"Zero data retention on external AI models\",\"SOC 2 compliance-ready architecture\",\"Full audit trail for every query\"": "\"End-to-end encryption at rest and in transit\",\"Zero data retention on external AI models\",\"POPIA-compliant data handling\",\"Full audit trail for every query\"",
    
    # Steps
    "Drag in any contract, brief, pleading or legal document. PDF, Word, scanned — REM-Leases handles it.": "Drag in any lease — residential, commercial, sectional title, or addendum. PDF, Word, scanned — RealEstateMeta handles it.",
    "Ask any question in plain English. \"What are the termination clauses?\" \"When do the warranties expire?\" \"Flag every obligation on the buyer.\"": "Ask any question in plain English. \"What are the escalation terms?\" \"When does this lease renew?\" \"What are my maintenance obligations?\" \"Flag every clause that favours the tenant.\"",
    "Get precise, sourced answers with page references. Export, share with your team, or keep interrogating. The document is yours to command.": "Get precise, sourced answers with clause references. Export, share with your team, or keep interrogating. Your lease portfolio is yours to command.",
    
    # Final CTA
    "Your next brief is waiting.<br />Stop reading. Start asking.": "Your next lease review is waiting.<br />Stop reading. Start asking.",
    "Upload your first document and see what REM-Leases finds in 30 seconds.": "Upload your first lease and see what RealEstateMeta finds in 30 seconds.",
    
    # Footer
    "© {new Date().getFullYear()} REM-Leases — Lekker fast. Dead accurate. Enterprise locked down.": "© {new Date().getFullYear()} RealEstateMeta — Lekker fast. Dead accurate. Portfolio ready.",
}

# The FAQ array block
old_faq_block = """  const faqs = [
    { q: "Is my client data safe?", a: "Yes. REM-Leases uses enterprise-grade encryption, and we never retain your data on third-party model infrastructure. Your documents are processed and purged. We're building towards SOC 2 certification because we believe legal AI without bulletproof security isn't legal AI — it's a liability." },
    { q: "Does it actually understand legal documents, or is this just ChatGPT with a skin?", a: "REM-Leases is purpose-built for legal document analysis. It understands clause structures, contractual hierarchies, and legal terminology. It doesn't hallucinate citations — every answer is grounded in the document you uploaded, with page references you can verify." },
    { q: "Will this replace my junior associates?", a: "No. It'll make them ten times more useful. REM-Leases handles the reading and extraction so your team can focus on analysis, strategy and the work that actually requires a legal mind." },
    { q: "What document types does it support?", a: "Contracts, briefs, pleadings, leases, SPAs, MOIs, shareholder agreements, NDAs, regulatory filings — if it's a legal document, REM-Leases can read it. PDF, Word and scanned documents are all supported." },
    { q: "How long does analysis actually take?", a: "A typical 100-page contract is fully analysed in under 30 seconds. Longer documents take proportionally longer, but we're talking minutes, not hours." },
  ];"""

new_faq_block = """  const faqs = [
    { q: "Is my lease data safe?", a: "Yes. RealEstateMeta uses enterprise-grade encryption, and we never retain your data on third-party model infrastructure. Your documents are processed and purged. Our architecture is POPIA-compliant because we believe property AI without bulletproof security isn't property AI — it's a liability." },
    { q: "Does it actually understand leases, or is this just ChatGPT with a skin?", a: "RealEstateMeta is purpose-built for lease document analysis. It understands clause structures, escalation formulas, renewal mechanisms, and South African property terminology. It doesn't hallucinate — every answer is grounded in the document you uploaded, with clause references you can verify." },
    { q: "Will this replace my property manager?", a: "No. It'll make them ten times more useful. RealEstateMeta handles the reading and extraction so your team can focus on negotiation, tenant relations, and the strategic decisions that actually grow your portfolio." },
    { q: "What lease types does it support?", a: "Commercial leases, residential leases, sectional title leases, industrial leases, ground leases, addendums, side letters, lease amendments — if it's a lease document, RealEstateMeta can read it. PDF, Word and scanned documents are all supported." },
    { q: "How long does analysis actually take?", a: "A typical 50-page lease is fully analysed in under 30 seconds. Longer or more complex documents take proportionally longer, but we're talking minutes, not the hours or days you're used to." },
    { q: "Can I analyse my whole portfolio at once?", a: "Yes. Upload your entire lease book and interrogate it as a single dataset. Ask portfolio-wide questions like \\\"Which leases expire in the next 12 months?\\\" or \\\"Show me all tenants with escalation rates below 7%.\\\"" },
    { q: "Is it compliant with South African legislation?", a: "Our platform is built with POPIA compliance at its core. We process data within secure, encrypted environments and retain nothing after your session. We can also help you identify clauses in your leases that may need updating for Rental Housing Act or Consumer Protection Act compliance." },
  ];"""

for old, new in replacements.items():
    content = content.replace(old, new)

if old_faq_block in content:
    content = content.replace(old_faq_block, new_faq_block)
else:
    print("Warning: old_faq_block not found exactly.")
    # attempt regex fallback
    content = re.sub(r"const faqs = \[.*?\];", new_faq_block, content, flags=re.DOTALL)

# Problem Section
problem_old = "You already know the problem."
problem_new = "The property management problem."
content = content.replace(problem_old, problem_new)

p1_old1 = "Your team spends hours reading documents that should take minutes."
p1_new1 = "Manual lease extraction is slow and error-prone."
content = content.replace(p1_old1, p1_new1)

p1_old2 = "A 200-page SPA lands on your desk at 4pm. You need the key obligations, deadlines and red flags by tomorrow morning. Right now, that means a late night or an anxious junior."
p1_new2 = "Reading through every lease to find termination rights, maintenance obligations, or escalation formulas takes hours per document. Multiply that across a portfolio and it becomes impossible."
content = content.replace(p1_old2, p1_new2)

p2_old1 = "Finding the right precedent is slow, manual and unreliable."
p2_new1 = "You have no portfolio-wide visibility."
content = content.replace(p2_old1, p2_new1)

p2_old2 = "You know there's a comparable clause somewhere in last year's matters. You just can't find it without digging through folders, emails and half-remembered file names."
p2_new2 = "Which leases have favourable escalation clauses? Which tenants have first right of refusal? Nobody knows without manual digging through hundreds of pages."
content = content.replace(p2_old2, p2_new2)

p3_old1 = "Generic AI tools aren't built for legal work."
p3_new1 = "Compliance risk and costly legal reviews."
content = content.replace(p3_old1, p3_new1)

p3_old2 = "ChatGPT hallucinates citations. General-purpose tools don't understand clause structures, legal hierarchies or privilege. You need something purpose-built."
p3_new2 = "Non-compliance with POPIA and the Rental Housing Act carries heavy fines. Sending every lease to an attorney at R2,500/hour for routine clauses is wasteful."
content = content.replace(p3_old2, p3_new2)

with open(filepath, "w", encoding="utf-8") as file:
    file.write(content)

print("Landing page copy updated successfully.")
