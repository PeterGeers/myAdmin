# Backend Environment Variables for Railway

## Instructions

1. Go to Railway dashboard: https://railway.app/
2. Select your project
3. Click on the **backend** service
4. Go to the **Variables** tab
5. Add these environment variables:

## Required Variables

```
DB_HOST=<railway-internal-hostname>
DB_PORT=3306
DB_USER=<db-user>
DB_PASSWORD=<set-via-railway-dashboard>
DB_NAME=finance
```

## Optional Variables (if not already set)

```
TEST_MODE=false
FLASK_ENV=production
```

## AWS & Landing Page Variables

```
AWS_ACCESS_KEY_ID=<from terraform output railway_backend_access_key_id>
AWS_SECRET_ACCESS_KEY=<from terraform output -raw railway_backend_secret_access_key>
AWS_DEFAULT_REGION=eu-west-1

# Landing Pages
CLOUDFRONT_PUBLIC_PAGES_DOMAIN=<from terraform output cloudfront_public_pages_domain_name>
CLOUDFRONT_PUBLIC_PAGES_DISTRIBUTION_ID=<from terraform output cloudfront_public_pages_distribution_id>
LANDING_PAGES_BUCKET=<from terraform output s3_public_pages_bucket_name>
LANDING_PAGE_BASE_URL=https://<cloudfront-domain>

# Custom Domains (KVS for domain→slug mapping at CloudFront edge)
CLOUDFRONT_KVS_ARN=<from terraform output cloudfront_kvs_domain_mapping_arn>

# SES Email
SES_SENDER_EMAIL=<from terraform output ses_sender_email>
SES_CONFIGURATION_SET=<from terraform output ses_configuration_set_name>

# Contact Form
CONTACT_FORM_API_URL=<railway-backend-public-url>
```

## After Setting Variables

1. The backend service should automatically redeploy
2. If not, click **Deploy** → **Redeploy** on the backend service
3. Check the deployment logs to verify the connection

## Verification

After redeployment, check the logs for:

- ✅ Should see: "Connected to database: finance"
- ❌ Should NOT see: "Can't connect to MySQL server on 'mysql:3306'"

## Current Issue

The backend is trying to connect to `mysql:3306` (Docker Compose hostname) instead of `devoted-contentment.railway.internal:3306` (Railway internal hostname).

Setting these environment variables will override the Docker Compose defaults and make the backend connect to the Railway MySQL service.
