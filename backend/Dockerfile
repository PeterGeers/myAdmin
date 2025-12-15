# Multi-stage build example
FROM python:3.9-slim AS builder
WORKDIR /app

# Cache dependencies for faster builds
COPY requirements.txt .
RUN pip install --user -r requirements.txt

FROM python:3.9-alpine
WORKDIR /app

# Create non-root user
RUN adduser -D myuser
USER myuser

# Copy only necessary files and use caching
COPY --from=builder /root/.local /root/.local
COPY . .
ENV PATH=/root/.local/bin:$PATH

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:5000/health || exit 1
