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

# Expose port (Railway will override with PORT env var)
EXPOSE 5000

# Note: Railway handles health checks via railway.json, no need for HEALTHCHECK here

# Start the application
# Run from src directory where imports work correctly
CMD ["sh", "-c", "if [ -n \"$RAILWAY_ENVIRONMENT\" ]; then python validate_env.py && cd src && FLASK_RUN_PORT=${PORT:-5000} FLASK_RUN_HOST=0.0.0.0 FLASK_DEBUG=false python app.py; else python src/app.py; fi"]
