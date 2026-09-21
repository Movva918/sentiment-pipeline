FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download and bake FinBERT model into the image
COPY download_model.py .
RUN python download_model.py && rm download_model.py

# Copy application code
COPY main.py .

# Cloud Run uses port 8080
EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
