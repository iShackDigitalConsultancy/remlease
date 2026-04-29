example_filename = "contract.pdf"
reduce_task = f"""Produce a chronological expiry schedule with calculated deadlines across the full document.
Find the Expiry Date, Renewal Notice Deadline, and relevant Notification Clause for each document.
Output ONLY valid JSON matching this exact structure:
{{
  "expiries": [
    {{
      "document": "{example_filename}",
      "commencement_date": "YYYY-MM-DD",
      "expiry_date": "YYYY-MM-DD",
      "renewal_deadline": "YYYY-MM-DD",
      "clause": "Text of the clause governing renewal/termination",
      "action_required": "Short description of what must happen"
    }}
  ]
}}
If a date is vague or missing, make your best guess for the date format "YYYY-MM-DD". Perform strict date arithmetic if the contract specifies a start date and term duration. Return ONLY the JSON object."""
print("PROMPT:")
print(reduce_task)
