"""
System Health Routes Blueprint

Handles health check, status, and monitoring endpoints.
Extracted from app.py during refactoring (Phase 1.2)
"""

import os

import psutil
from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from database import DatabaseManager

system_health_bp = Blueprint("system_health", __name__)

# Access to scalability_manager from app.py
# This will be set by app.py after blueprint registration
scalability_manager = None


def set_scalability_manager(manager) -> None:
    """Set the scalability manager reference from app.py"""
    global scalability_manager
    scalability_manager = manager


@system_health_bp.route("/api/test", methods=["GET"])
@cognito_required(required_permissions=[])
def test(user_email, user_roles) -> ResponseReturnValue:
    """Test endpoint"""
    print("Test endpoint called", flush=True)
    return jsonify({"status": "Server is working"})


@system_health_bp.route("/api/status", methods=["GET"])
def get_status() -> ResponseReturnValue:
    """Get environment status - Public endpoint (no authentication required)"""
    try:
        use_test = os.getenv("TEST_MODE", "false").lower() == "true"
        db_name = (
            os.getenv("TEST_DB_NAME", "testfinance")
            if use_test
            else os.getenv("DB_NAME", os.getenv("MYSQL_DATABASE", "finance"))
        )
        folder_name = (
            os.getenv("TEST_FACTUREN_FOLDER_NAME", "testFacturen")
            if use_test
            else os.getenv("FACTUREN_FOLDER_NAME", "Facturen")
        )

        return jsonify(
            {
                "status": "ok",
                "mode": "Test" if use_test else "Production",
                "database": db_name,
                "folder": folder_name,
            }
        )
    except Exception as e:  # noqa: BLE001
        return jsonify({"status": "error", "error": str(e)}), 500


@system_health_bp.route("/api/db-config", methods=["GET"])
def get_db_config() -> ResponseReturnValue:
    """Get database configuration (for diagnostics) - Public endpoint"""
    try:
        use_test = os.getenv("TEST_MODE", "false").lower() == "true"

        # Get all possible database environment variables
        config = {
            "DB_HOST": os.getenv("DB_HOST", "NOT_SET"),
            "RAILWAY_PRIVATE_DOMAIN": os.getenv("RAILWAY_PRIVATE_DOMAIN", "NOT_SET"),
            "DB_PORT": os.getenv("DB_PORT", "NOT_SET"),
            "DB_USER": os.getenv("DB_USER", "NOT_SET"),
            "MYSQL_USER": os.getenv("MYSQL_USER", "NOT_SET"),
            "DB_NAME": os.getenv("DB_NAME", "NOT_SET"),
            "MYSQL_DATABASE": os.getenv("MYSQL_DATABASE", "NOT_SET"),
            "TEST_MODE": os.getenv("TEST_MODE", "NOT_SET"),
            "computed_host": os.getenv(
                "DB_HOST", os.getenv("RAILWAY_PRIVATE_DOMAIN", "localhost")
            ),
            "computed_user": os.getenv("DB_USER", os.getenv("MYSQL_USER", "root")),
            "computed_database": os.getenv("TEST_DB_NAME", "testfinance")
            if use_test
            else os.getenv("DB_NAME", os.getenv("MYSQL_DATABASE", "finance")),
            "computed_port": int(os.getenv("DB_PORT", "3306")),
        }

        # Don't expose password, just indicate if it's set
        config["DB_PASSWORD"] = "SET" if os.getenv("DB_PASSWORD") else "NOT_SET"
        config["MYSQL_PASSWORD"] = "SET" if os.getenv("MYSQL_PASSWORD") else "NOT_SET"

        return jsonify(config)
    except Exception as e:  # noqa: BLE001
        return jsonify({"error": str(e)}), 500


@system_health_bp.route("/api/db-test", methods=["GET"])
def test_db_connection() -> ResponseReturnValue:
    """Test database connection - Public endpoint"""
    try:
        db = DatabaseManager()

        # Try to connect and run a simple query
        result = db.execute_query("SELECT 1 as test")

        return jsonify(
            {
                "status": "success",
                "message": "Database connection successful",
                "config": {
                    "host": db.config["host"],
                    "port": db.config["port"],
                    "user": db.config["user"],
                    "database": db.config["database"],
                },
                "test_query_result": result,
            }
        )
    except Exception as e:  # noqa: BLE001
        return jsonify(
            {"status": "error", "message": str(e), "error_type": type(e).__name__}
        ), 500


@system_health_bp.route("/api/str/test", methods=["GET"])
@cognito_required(required_permissions=[])
def str_test(user_email, user_roles) -> ResponseReturnValue:
    """STR test endpoint"""
    print("STR test endpoint called", flush=True)
    return jsonify({"status": "STR endpoints working", "openpyxl_available": True})


@system_health_bp.route("/api/health", methods=["GET"])
def health() -> ResponseReturnValue:
    """Health check endpoint with scalability information - No authentication required"""
    health_info = {
        "status": "healthy",
        "endpoints": [
            "str/upload",
            "str/scan-files",
            "str/process-files",
            "str/save",
            "str/write-future",
        ],
        "scalability": {
            "manager_active": scalability_manager is not None,
            "concurrent_user_capacity": "10x baseline"
            if scalability_manager
            else "1x baseline",
        },
    }

    if scalability_manager:
        health_status = scalability_manager.get_health_status()
        health_info["scalability"].update(
            {
                "health_score": health_status["health_score"],
                "status": health_status["status"],
                "scalability_ready": health_status["scalability_ready"],
            }
        )

    # Cache statistics
    health_info["caches"] = _collect_cache_stats()

    # Process memory info
    health_info["process"] = _collect_process_stats()

    return jsonify(health_info)


def _collect_cache_stats() -> dict:
    """Collect stats from all cache singletons. Wrapped in try/except per cache."""
    caches = {}

    # MutatiesCache stats
    try:
        from mutaties_cache import get_cache

        mutaties_cache = get_cache()
        stats = mutaties_cache.get_stats()
        caches["mutaties"] = {
            "tenants_loaded": stats.get("tenants_loaded", 0),
            "total_rows": stats.get("total_rows", 0),
            "memory_mb": stats.get("memory_mb", 0.0),
        }
    except Exception:  # noqa: BLE001
        caches["mutaties"] = {"error": "unavailable"}

    # BnbCache stats
    try:
        from bnb_cache import get_bnb_cache

        bnb_cache = get_bnb_cache()
        stats = bnb_cache.get_stats()
        caches["bnb"] = {
            "tenants_loaded": stats.get("tenants_loaded", 0),
            "total_rows": stats.get("total_rows", 0),
            "memory_mb": stats.get("memory_mb", 0.0),
        }
    except Exception:  # noqa: BLE001
        caches["bnb"] = {"error": "unavailable"}

    # QueryCache stats
    try:
        from duplicate_query_optimizer import get_query_optimizer

        optimizer = get_query_optimizer()
        stats = optimizer.cache.get_stats()
        caches["query_cache"] = {
            "entries": stats.get("total_entries", 0),
            "max_size": stats.get("max_size", 0),
            "hit_rate_percent": stats.get("hit_rate_percent", 0.0),
        }
    except Exception:  # noqa: BLE001
        caches["query_cache"] = {"error": "unavailable"}

    return caches


def _collect_process_stats() -> dict:
    """Collect process RSS and alert threshold."""
    alert_threshold_mb = int(os.environ.get("MEMORY_ALERT_THRESHOLD_MB", "512"))

    try:
        rss_bytes = psutil.Process().memory_info().rss
        rss_mb = round(rss_bytes / 1024 / 1024, 1)
    except Exception:  # noqa: BLE001
        rss_mb = 0.0

    result = {
        "rss_mb": rss_mb,
        "alert_threshold_mb": alert_threshold_mb,
    }

    if rss_mb > alert_threshold_mb:
        result["memory_alert"] = True

    return result


@system_health_bp.route("/api/google-drive/token-health", methods=["GET"])
@cognito_required(required_roles=["SysAdmin", "Tenant_Admin"])
def google_drive_token_health(user_email, user_roles) -> ResponseReturnValue:
    """Check Google Drive token health for all tenants"""
    from datetime import datetime

    from services.credential_service import CredentialService

    try:
        db = DatabaseManager()
        credential_service = CredentialService(db)

        tenants_result = db.execute_query(
            "SELECT DISTINCT administration FROM rekeningschema WHERE administration IS NOT NULL"
        )
        tenants = (
            [r["administration"] for r in tenants_result] if tenants_result else []
        )
        results = {}

        for tenant in tenants:
            try:
                token_data = credential_service.get_credential(
                    tenant, "google_drive_token"
                )

                if not token_data or "expiry" not in token_data:
                    results[tenant] = {
                        "status": "error",
                        "message": "Token not found",
                        "action_required": True,
                    }
                    continue

                # Parse expiry date
                expiry_str = token_data["expiry"]
                try:
                    expiry_date = datetime.fromisoformat(
                        expiry_str.replace("Z", "+00:00")
                    )
                except Exception:  # noqa: BLE001
                    try:
                        expiry_date = datetime.strptime(expiry_str, "%d-%m-%Y %H:%M:%S")  # noqa: DTZ007
                    except Exception:  # noqa: BLE001
                        results[tenant] = {
                            "status": "error",
                            "message": f"Invalid expiry format: {expiry_str}",
                            "action_required": True,
                        }
                        continue

                now = datetime.now()  # noqa: DTZ005
                if expiry_date.tzinfo:
                    from datetime import timezone

                    now = datetime.now(timezone.utc)

                days_until_expiry = (expiry_date - now).days

                if days_until_expiry < 0:
                    results[tenant] = {
                        "status": "expired",
                        "message": f"Token expired {abs(days_until_expiry)} days ago",
                        "expiry_date": expiry_str,
                        "action_required": True,
                        "recovery_steps": [
                            "python backend/refresh_google_token.py",
                            f"python scripts/credentials/migrate_credentials_to_db.py --tenant {tenant}",
                            "docker-compose restart backend",
                        ],
                    }
                elif days_until_expiry <= 7:
                    results[tenant] = {
                        "status": "warning",
                        "message": f"Token expires in {days_until_expiry} days",
                        "expiry_date": expiry_str,
                        "action_required": False,
                        "recommendation": "Refresh token soon",
                    }
                else:
                    results[tenant] = {
                        "status": "healthy",
                        "message": f"Token valid for {days_until_expiry} days",
                        "expiry_date": expiry_str,
                        "action_required": False,
                    }

            except Exception as e:  # noqa: BLE001
                results[tenant] = {
                    "status": "error",
                    "message": str(e),
                    "action_required": True,
                }

        # Overall status
        overall_status = "healthy"
        if any(r["status"] == "expired" for r in results.values()):
            overall_status = "critical"
        elif any(r["status"] == "warning" for r in results.values()):
            overall_status = "warning"
        elif any(r["status"] == "error" for r in results.values()):
            overall_status = "error"

        return jsonify(
            {
                "overall_status": overall_status,
                "tenants": results,
                "checked_at": datetime.now().isoformat(),  # noqa: DTZ005
            }
        )

    except Exception as e:  # noqa: BLE001
        return jsonify({"overall_status": "error", "message": str(e)}), 500
