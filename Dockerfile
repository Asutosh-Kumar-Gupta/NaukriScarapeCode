FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .
RUN pip install -e . --no-deps

ENV PYTHONUNBUFFERED=1
ENV HEADLESS=true

CMD ["python", "-m", "src.main", "run"]
