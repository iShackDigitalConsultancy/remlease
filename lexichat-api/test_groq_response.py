import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

example_filename = "test_lease_document.pdf"
old_full_text = "This lease commences on 1 January 2024 for a duration of 5 years."
prompt = f"""You are a senior legal analyst extracting crucial dates from multiple contracts to trigger calendar/SmartBuilding events.

DOCUMENTS TEXT:
{old_full_text}

INSTRUCTIONS:
Find the Expiry Date, Renewal Notice Deadline, and relevant Notification Clause for each document.
Output ONLY valid JSON matching this exact structure:
{{
  "expiries": [
    {{
      "document": "{example_filename}",
      "commencement_date": "YYYY-MM-DD" (Extract the explicit start or signature date, or null if absolutely missing),
      "expiry_date": "YYYY-MM-DD" (EXTREMELY IMPORTANT: If missing, you MUST CALCULATE it by finding 'Commencement Date' or 'Signature Date' and adding 'Duration'/'Term'. E.g. start=2023-01-01 + duration 5 years = 2028-01-01),
      "renewal_deadline": "YYYY-MM-DD" (Calculate from expiry date minus notice period if applicable),
      "clause": "Text of the clause governing renewal/termination",
      "action_required": "Short description of what must happen"
    }}
  ]
}}

If a date is vague or missing, make your best guess for the date format "YYYY-MM-DD". Perform strict date arithmetic if the contract specifies a start date and term duration. Return ONLY the JSON object."""

resp = groq_client.chat.completions.create(
    model='llama-3.3-70b-versatile',
    messages=[{'role': 'user', 'content': prompt}],
    temperature=0.0,
    max_tokens=2000
)
print("RAW LLM OUTPUT:")
print(resp.choices[0].message.content)
