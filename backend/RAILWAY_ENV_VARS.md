# Railway Environment Variables

All environment variables for the Railway backend service.
Keep this in sync with `backend/.env.example` when adding new variables.

**Last updated:** 2026-03-23

## Current Railway Variables (27)

| Variable                       | Category      | Notes                                    |
| ------------------------------ | ------------- | ---------------------------------------- |
| `ALLOW_MIGRATION`              | Migration     | One-time flag, remove when done          |
| `AWS_ACCESS_KEY_ID`            | AWS           | IAM credentials for boto3                |
| `AWS_REGION`                   | AWS           | `eu-west-1`                              |
| `AWS_SECRET_ACCESS_KEY`        | AWS           | IAM credentials for boto3                |
| `COGNITO_CLIENT_ID`            | Auth          | Cognito app client                       |
| `COGNITO_CLIENT_SECRET`        | Auth          | Cognito app client secret                |
| `COGNITO_USER_POOL_ID`         | Auth          | `eu-west-1_Hdp40eWmu`                    |
| `CREDENTIALS_ENCRYPTION_KEY`   | Security      | 64-char hex, encrypts tenant credentials |
| `CSRF_SECRET`                  | Security      | CSRF token for signup forms              |
| `DB_HOST`                      | Database      | `mysql.railway.internal`                 |
| `DB_NAME`                      | Database      | `finance`                                |
| `DB_PASSWORD`                  | Database      | From Railway MySQL service               |
| `DB_PORT`                      | Database      | `3306`                                   |
| `DB_USER`                      | Database      |                                          |
| `FACTUREN_FOLDER_ID`           | Google Drive  | Root folder for invoices                 |
| `FACTUREN_FOLDER_NAME`         | Google Drive  | `Facturen`                               |
| `OPENROUTER_API_KEY`           | AI            | Invoice extraction (optional)            |
| `PROMO_DB_NAME`                | Signup        | `myadmin_promo`                          |
| `SECRET_KEY`                   | Flask         | Random hex for session security          |
| `SES_SENDER_EMAIL`             | Email         | `support@jabaki.nl`                      |
| `SIGNUP_ADMIN_EMAIL`           | Signup        | `peter@jabaki.nl`                        |
| `SIGNUP_COGNITO_APP_CLIENT_ID` | Signup        | Public client (no secret)                |
| `SIGNUP_COGNITO_USER_POOL_ID`  | Signup        | Same pool as main app                    |
| `SIGNUP_REDIRECT_URL`          | Signup        | Post-verification redirect               |
| `SNS_TOPIC_ARN`                | Notifications | Admin alerts via SNS                     |

## Not needed in Railway

| Variable                    | Why                                |
| --------------------------- | ---------------------------------- |
| `FRONTEND_URL`              | Auto-detected from request headers |
| `TEST_MODE`                 | Defaults to `false`                |
| `TEST_DB_NAME`              | Local test mode only               |
| `TEST_FACTUREN_FOLDER_ID`   | Local test mode only               |
| `TEST_FACTUREN_FOLDER_NAME` | Local test mode only               |
| `FLASK_ENV`                 | Railway sets this                  |
| `FLASK_DEBUG`               | Never enable in production         |
