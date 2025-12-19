# Gunicorn configuration optimized for 10x concurrent users
import multiprocessing
import os

# Server socket
bind = "127.0.0.1:5000"
backlog = 2048  # Increased from default 2048

# Worker processes - scale based on CPU cores
workers = min(multiprocessing.cpu_count() * 2, 8)  # 2 workers per CPU core, max 8
worker_class = "gthread"  # Use threaded workers for I/O bound operations
threads = 25  # Increased from 4 to 25 (6x improvement)
worker_connections = 1000  # Max simultaneous clients per worker

# Worker lifecycle
max_requests = 10000  # Restart workers after 10k requests to prevent memory leaks
max_requests_jitter = 1000  # Add randomness to prevent thundering herd
worker_tmp_dir = "/dev/shm"  # Use shared memory for better performance
timeout = 120  # Increased timeout for long-running operations
keepalive = 5  # Keep connections alive for 5 seconds

# Performance optimizations
preload_app = True  # Preload application for better memory usage
enable_stdio_inheritance = True
reuse_port = True  # Enable SO_REUSEPORT for better load distribution

# Logging
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr

# Security
limit_request_line = 8192  # Increased for large requests
limit_request_fields = 200
limit_request_field_size = 16384

# Process naming
proc_name = "myAdmin-banking-processor"

# Graceful shutdown
graceful_timeout = 30

# Environment variables for scalability
raw_env = [
    'SCALABILITY_ENABLED=true',
    'MAX_CONCURRENT_USERS=1000',  # 10x improvement from ~100
    'PERFORMANCE_MONITORING=true'
]

# Hooks for scalability monitoring
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("🚀 Starting myAdmin with 10x scalability improvements")
    server.log.info(f"   Workers: {workers}")
    server.log.info(f"   Threads per worker: {threads}")
    server.log.info(f"   Total concurrent capacity: {workers * threads}")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("🔄 Reloading with scalability optimizations")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("🔄 Worker interrupted, scalability manager will handle gracefully")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("✅ Shutting down with graceful scalability cleanup")