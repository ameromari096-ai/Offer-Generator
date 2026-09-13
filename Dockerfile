FROM python:3.11-slim

# libreoffice-core alone cannot load any document ("source file could not
# be loaded") — the Writer component is required for DOCX->PDF conversion.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY offer_agent/ offer_agent/
COPY templates/ templates/
COPY webapp/ webapp/

RUN mkdir -p data/storage

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "webapp.app:app"]
