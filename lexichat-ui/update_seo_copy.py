import os

filepath = "/Users/wdbmacminipro/Desktop/REM-Leases/lexichat-ui/src/App.jsx"
with open(filepath, "r", encoding="utf-8") as file:
    content = file.read()

replacements = {
    # Free Audit Hooks
    "Upload your first lease — it's free": "Get your Free AI Lease Audit",
    "Upload your first lease and see what RealEstateMeta finds in 30 seconds.": "Drop your first lease below to get your Free Audit. Discover risks and missing clauses in 30 seconds.",
    "No credit card. No setup. Just answers.": "No credit card. Free risk audit. Instant answers.",
    "No sign-up needed. Upload any residential or commercial lease and start asking questions immediately.": "Upload any residential or commercial lease for a Free Audit. Start extracting dates and risks immediately.",
    
    # Firm Tier Upsell
    "Enterprise Security": "Firm Tier & Agency White-Labeling",
    "POPIA-compliant architecture, end-to-end encryption, and zero data retention on third-party models. Your lease documents contain sensitive commercial and personal information — we treat them accordingly.": "Generate branded PDF risk-reports to send to your landlord clients. Pass the software cost onto landlords as an administration fee while keeping data strictly POPIA-compliant with enterprise encryption.",
    "\"End-to-end encryption at rest and in transit\",\"Zero data retention on external AI models\",\"POPIA-compliant data handling\",\"Full audit trail for every query\"": "\"Client-branded PDF Risk Reports\",\"Pass-through software billing\",\"POPIA-compliant and Encrypted\",\"Portfolio-wide firm administration\""
}

for old, new in replacements.items():
    if old in content:
        content = content.replace(old, new)
        print(f"Replaced: {old[:20]}...")
    else:
        print(f"Warning: Could not find '{old[:30]}...' in App.jsx")

with open(filepath, "w", encoding="utf-8") as file:
    file.write(content)

print("SEO Copy applied successfully.")
