FROM python:3.11-slim

# libreoffice-core alone cannot load any document ("source file could not
# be loaded") — the Writer component is required for DOCX->PDF conversion.
# libemail-outlook-message-perl provides msgconvert, used to read uploaded
# .msg (Outlook) hiring-approval emails. It only Recommends (not Depends
# on) libemail-address-perl, which --no-install-recommends then skips —
# msgconvert fails at runtime ("Can't locate Email/Address.pm") without
# it, so it must be listed explicitly.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    fonts-liberation \
    libemail-outlook-message-perl \
    libemail-address-perl \
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
