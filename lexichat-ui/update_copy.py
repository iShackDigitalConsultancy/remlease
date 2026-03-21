import os

replacements = {
    # Auth.jsx replacements
    "Sign in to your workspace": "Sign in to your Property Dashboard",
    "Create your account": "Create your Leasing Account",
    "Individual / Join Firm": "Independent Landlord / Join Agency",
    "Register New Firm": "Register Property Group",
    "Firm Name to Join (Optional)": "Agency Name to Join (Optional)",
    "Firm Name": "Property Group / Agency Name",
    "attorney@lawfirm.co.za": "leasing@propertygroup.co.za",
    "Smith & Associates Inc": "PropTech Rentals",
    "If your firm is registered, type its exact name to request access to shared workspaces.": "If your agency is registered, type its exact name to request access to shared portfolios.",
    
    # App.jsx replacements
    "I have loaded this Case Workspace for your firm": "I have loaded this Leasing Workspace for your portfolio",
    "Upload a case file, brief, or contract into this new Firm workspace": "Upload a lease agreement, tenant application, or property document into this new Portfolio workspace",
    "Firm Workspaces": "Property Portfolios",
    "New Firm Case": "New Property Portfolio",
    "Documents in:": "Lease Files in:",
    "1. The governing law must be South Africa.\\n2. The agreement must have a fixed term.\\n3. There should be a mutual indemnification clause.": "1. The lease must stipulate a clear expiration date.\\n2. The security deposit amount must be clearly stated.\\n3. Tenant maintenance obligations must be defined.",
    "Global Knowledge Base": "Property Law & Leasing Regulations",
    "Constitution of the Republic": "Rental Housing Act (50 of 1999)",
    "Uniform Rules of Court": "Consumer Protection Act (CPA)",
    "Companies Act (71 of 2008)": "Prevention of Illegal Eviction Act (PIE)",
    "Labour Relations & BCEA": "Property Practitioners Act",
    "Firm Knowledge Base": "Agency & Portfolio History",
    "Search Firm Precedents": "Search Portfolio History",
    "Search across all documents uploaded by your firm": "Search across all lease agreements and documents uploaded by your agency",
    "Select a Firm Workspace": "Select a Property Portfolio",
    "Choose an existing case from the sidebar or click <span className=\"font-bold text-brand-blue\">+</span> to start a new workspace securely for your team.": "Choose an existing portfolio from the sidebar or click <span className=\"font-bold text-brand-blue\">+</span> to start a new workspace securely for your team."
}

base_dir = "/Users/wdbmacminipro/Desktop/REM-Leases/lexichat-ui/src"
files_to_update = [
    os.path.join(base_dir, "pages", "Auth.jsx"),
    os.path.join(base_dir, "App.jsx")
]

for file_path in files_to_update:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
        
        orig_content = content
        for old_str, new_str in replacements.items():
            content = content.replace(old_str, new_str)
        
        if content != orig_content:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(content)
            print(f"Updated {file_path}")
        else:
            print(f"No changes needed for {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
