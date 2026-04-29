example_filename = "contract.pdf"
old_full_text = "some text"
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
print("LEGACY OP PROMPT:")
print(prompt)
