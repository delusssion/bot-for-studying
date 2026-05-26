FROM python:3.11-slim

# poppler-utils: pdf2image; nodejs+pptxgenjs: PPTX generation; libreoffice: PPTX→PDF for visual QA
RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils nodejs npm libreoffice \
    && npm install -g pptxgenjs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create log directory so the volume mount works smoothly
RUN mkdir -p logs

CMD ["python", "-m", "bot.main"]
