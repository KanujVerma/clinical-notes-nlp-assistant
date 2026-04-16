# Dockerfile

# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python backend + serve frontend
FROM python:3.11-slim AS runtime
WORKDIR /app/backend

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libmupdf-dev \
    tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

# Copy backend
COPY backend/ .

# Copy built frontend into static/
COPY --from=frontend-build /app/frontend/dist ./static

# Copy data and scripts
WORKDIR /app
COPY data/ data/
COPY scripts/ scripts/

ENV FLASK_ENV=production
ENV PYTHONPATH=/app/backend

EXPOSE 5000
CMD ["gunicorn", "--chdir", "/app/backend", "app:create_app()", "--bind", "0.0.0.0:5000", "--workers", "2"]
