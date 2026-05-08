"""
Generate test fixtures for the REM-Leases pipeline.
Usage: python scripts/generate_test_fixtures.py
"""
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

def generate_smoke_test_pdf():
    os.makedirs("tests/fixtures", exist_ok=True)
    c = canvas.Canvas("tests/fixtures/smoke_test.pdf", pagesize=letter)
    c.drawString(100, 750, "Lease Agreement - Smoke Test")
    c.drawString(100, 730, "This is a simple test document.")
    c.drawString(100, 710, "Commencement Date: 2025-01-01")
    c.drawString(100, 690, "Expiry Date: 2030-01-01")
    c.save()
    print("Generated tests/fixtures/smoke_test.pdf")

if __name__ == "__main__":
    generate_smoke_test_pdf()
