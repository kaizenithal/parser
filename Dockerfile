FROM python:3.11-slim AS base

LABEL authors="kaizenithal"

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY app/ app/

EXPOSE 8200

# Explicitly set no silent request body limit (50MB ceiling as safety net)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200", "--limit-request-body", "52428800"]