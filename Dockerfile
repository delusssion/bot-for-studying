FROM python:3.11-slim

# poppler-utils: required by pdf2image for PDF → image conversion
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create log directory so the volume mount works smoothly
RUN mkdir -p logs

CMD ["python", "-m", "bot.main"]
