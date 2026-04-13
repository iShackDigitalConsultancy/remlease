FROM python:3.11-slim

# Install system dependencies required for PDF parsing and OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the API directory into the container
COPY lexichat-api/ /app/lexichat-api/

# Copy the SQLite DB if it exists (Railway might use an external DB instead, but we copy everything just in case)
COPY rem-leases.db /app/rem-leases.db

# Install python dependencies
RUN pip install --no-cache-dir -r /app/lexichat-api/requirements.txt

# Change to the working directory where main.py resides
WORKDIR /app/lexichat-api

# The PORT environment variable is automatically provided by Railway
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
