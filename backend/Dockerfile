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
# Run from src directory where imports work correctly
CMD ["sh", "-c", "if [ -n \"$RAILWAY_ENVIRONMENT\" ]; then python validate_env.py && cd src && FLASK_RUN_PORT=${PORT:-5000} FLASK_DEBUG=false python app.py; else python src/app.py; fi"]
