"""Image upload endpoint for the landing page editor.

Handlers resolve shared helpers/classes through the
``routes.landing_page_routes`` package namespace at call time so the test
suite's ``patch('routes.landing_page_routes.<name>')`` calls keep working.
"""

import logging
import os

from botocore.exceptions import ClientError
from flask import jsonify, request
from flask.typing import ResponseReturnValue

from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from routes import landing_page_routes as pkg

logger = logging.getLogger(__name__)

landing_page_bp = pkg.landing_page_bp


@landing_page_bp.route("/api/landing/images/upload", methods=["POST"])
@cognito_required(required_roles=["Tenant_Admin"])
@tenant_required()
def upload_image(user_email, user_roles, tenant, user_tenants) -> ResponseReturnValue:
    """
    Upload an image to the public S3 bucket via MediaAssetService.

    Authorization: Tenant_Admin role required

    Accepts multipart/form-data with a 'file' field.
    MediaAssetService validates file type (extension + magic bytes) and size.

    Returns:
        JSON with image_key and public URL on success, or error on failure.
    """
    try:
        # Validate file is present
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400

        file = request.files["file"]

        if not file.filename:
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Read file data
        file_data = file.read()

        # Get slug for tenant (used as entity_id for reference tracking)
        slug_service = pkg._get_slug_service()
        slug = slug_service.get_slug(tenant)

        if not slug:
            return jsonify(
                {
                    "success": False,
                    "error": "No slug configured for this tenant. Set a slug first.",
                }
            ), 400

        # Upload via MediaAssetService (handles validation, S3 upload, and registry)
        test_mode = os.getenv("TEST_MODE", "false").lower() == "true"
        db = pkg.DatabaseManager(test_mode=test_mode)
        ps = pkg.ParameterService(db)
        asset_svc = pkg.MediaAssetService(db, ps)

        result = asset_svc.store_and_register(
            tenant=tenant,
            file_data=file_data,
            filename=file.filename,
            category="landing-pages",
            entity_type="landing_page",
            entity_id=str(slug),
            metadata={"slug": slug},
        )

        if not result["success"]:
            return jsonify(
                {"success": False, "error": result.get("error", "Upload failed")}
            ), 400

        s3_key = result["asset"]["s3_key"]

        # Build public URL (CloudFront or direct S3)
        cloudfront_domain = os.environ.get("CLOUDFRONT_PUBLIC_PAGES_DOMAIN", "")
        if cloudfront_domain:
            url = f"https://{cloudfront_domain}/{s3_key}"
        else:
            env = os.environ.get("ENVIRONMENT", "production")
            bucket_name = os.environ.get(
                "LANDING_PAGES_BUCKET", f"myadmin-public-pages-{env}"
            )
            region = os.environ.get("AWS_DEFAULT_REGION", "eu-west-1")
            url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{s3_key}"

        logger.info(f"Image uploaded by {user_email} for tenant {tenant}: {s3_key}")

        return jsonify(
            {
                "success": True,
                "data": {
                    "image_key": s3_key,
                    "url": url,
                },
            }
        )

    except ValueError as e:
        # MediaAssetService raises ValueError for validation failures
        logger.warning(f"Image validation error for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 400
    except ClientError as e:
        logger.error(f"S3 upload error for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": "Failed to upload image"}), 500
    except Exception as e:
        logger.error(f"Error uploading image for tenant {tenant}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
