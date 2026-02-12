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

# Add /app/src to PYTHONPATH so imports work correctly
ENV PYTHONPATH=/app/src

# Expose port
EXPOSE 5000

# Health check (Railway uses PORT env var)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:${PORT:-5000}/api/health || exit 1

# Start the application
# For Railway: Use waitress with proper PYTHONPATH, stay in /app directory
# For local Docker: Use Flask dev server
CMD ["sh", "-c", "if [ -n \"$RAILWAY_ENVIRONMENT\" ]; then python validate_env.py && waitress-serve --host=0.0.0.0 --port=${PORT:-5000} src.app:app; else python src/app.py; fi"]
