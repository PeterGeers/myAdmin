FROM python:3.11-slim

# Suppress debconf warnings
ENV DEBIAN_FRONTEND=noninteractive
ENV DEBCONF_NONINTERACTIVE_SEEN=true

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Health check (Railway uses PORT env var)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-5000}/api/health || exit 1

# Start the application with environment validation and production server
# Updated: 2026-02-11 - Using --call flag for Waitress
CMD python validate_env.py && echo "Starting Waitress on port ${PORT:-5000}..." && PYTHONPATH=/app waitress-serve --host=0.0.0.0 --port=${PORT:-5000} src.wsgi:app
