from fpdf import FPDF
import os

acts = {
    "CompaniesAct.pdf": {
        "title": "Companies Act, 71 of 2008",
        "body": "The Companies Act 71 of 2008 regulates the incorporation, registration, internal organization, and management of companies in South Africa. Key provisions include the roles of directors, fiduciary duties, memorandums of incorporation (MOI), and business rescue proceedings for financially distressed corporate entities."
    },
    "NationalCreditAct.pdf": {
        "title": "National Credit Act, 34 of 2005",
        "body": "The National Credit Act (NCA) of South Africa regulates the consumer credit market. Crucially, Section 129 requires a credit provider to send a written notice to the consumer drawing their attention to default before commencing any legal proceedings or issuing a summons."
    },
    "LabourRelationsAct.pdf": {
        "title": "Labour Relations Act, 66 of 1995",
        "body": "The Labour Relations Act (LRA) regulates the organizational rights of trade unions and promotes collective bargaining in South Africa. It dictates clear procedural fairness requirements for dismissing employees, known as the Code of Good Practice on Dismissal, and creates the CCMA for alternate dispute resolution."
    },
    "BasicConditionsOfEmploymentAct.pdf": {
        "title": "Basic Conditions of Employment Act, 75 of 1997",
        "body": "The BCEA ensures fair labor practices in South Africa by establishing baseline working conditions. It mandates maximum statutory working hours, minimum leave requirements (annual, sick, maternity), and regulations around severance pay upon retrenchment."
    },
    "UniformRulesOfCourt.pdf": {
        "title": "Uniform Rules of Court (High Court)",
        "body": "The Uniform Rules of Court govern the civil procedure in the High Courts of South Africa. For instance, Rule 6(5)(b) stipulates that a respondent must serve a notice to oppose within 5 court days of receiving a motion, and Rule 14 governs proceedings by and against partnerships and firms."
    }
}

os.makedirs("knowledge_base/za", exist_ok=True)

for filename, content in acts.items():
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=15)
    pdf.cell(200, 10, txt=content["title"], ln=1, align='C')
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 10, txt=content["body"])
    pdf.output(f"knowledge_base/za/{filename}")
    print(f"Generated {filename}")
