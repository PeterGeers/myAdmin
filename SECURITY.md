# Security Policy

## Overview

myAdmin is a financial transaction processing and administrative system that handles sensitive financial data, multi-tenant operations, and integrates with AWS and Railway services. We take security seriously and appreciate the security community's efforts to responsibly disclose vulnerabilities.

## Supported Versions

We provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| main    | :white_check_mark: |
| dev     | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

If you discover a security vulnerability in myAdmin, please report it privately:

### Preferred Method

1. **Email**: Send details to [pjageers@gmail.com]
2. **Subject Line**: `[SECURITY] myAdmin Vulnerability Report`
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if available)
   - Your contact information

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Timeline**: Depends on severity (see below)

### Severity Levels

| Severity     | Response Time | Examples                                  |
| ------------ | ------------- | ----------------------------------------- |
| **Critical** | 24-48 hours   | Authentication bypass, SQL injection, RCE |
| **High**     | 3-7 days      | XSS, CSRF, privilege escalation           |
| **Medium**   | 14-30 days    | Information disclosure, weak encryption   |
| **Low**      | 30-90 days    | Minor configuration issues                |

## Security Measures

### Authentication & Authorization

- **AWS Cognito Integration**: User authentication via AWS Cognito
- **JWT Tokens**: Secure token-based authentication with python-jose
- **Multi-tenant Isolation**: Tenant context middleware ensures data isolation
- **Role-based Access**: User permissions managed through Cognito groups

### Data Protection

- **Encryption at Rest**:
  - Tenant credentials encrypted using `cryptography` library
  - Encryption key stored in environment variables (`CREDENTIALS_ENCRYPTION_KEY`)
- **Encryption in Transit**:
  - HTTPS enforced for all API communications
  - TLS 1.2+ required
- **Database Security**:
  - MySQL 9.0 with secure connection parameters
  - Prepared statements to prevent SQL injection
  - Database credentials in environment variables

### Infrastructure Security

- **Railway Deployment**:
  - Backend (Flask) and MySQL hosted on Railway.app
  - Automatic deployments from GitHub main branch
  - Environment variables managed via Railway dashboard
  - Private networking between backend and MySQL services
  - Railway's built-in SSL/TLS certificates
- **GitHub Pages**:
  - Static frontend (React) hosted on GitHub Pages
  - HTTPS enforced via GitHub's CDN
  - Automatic deployments from repository
- **AWS Services**:
  - AWS SNS for secure notifications
  - AWS Cognito for identity management
  - IAM roles with least privilege principle
- **Secret Management**:
  - Railway environment variables for backend secrets
  - `.env` files excluded from version control
  - `.env.example` templates provided without sensitive data
- **Local Development**: Docker Compose for local testing with isolated environments

### API Security

- **CORS Configuration**: Flask-CORS with restricted origins
- **Input Validation**: Comprehensive validation on all endpoints
- **Rate Limiting**: (Recommended to implement)
- **API Documentation**: Swagger/OpenAPI via Flasgger

### Code Security

- **Dependency Scanning**:
  - GitGuardian for credential leak detection (`.gitguardian.yaml`)
  - Regular dependency updates
- **Static Analysis**: ESLint for frontend, pytest for backend
- **Security Headers**: (Recommended to implement)
  - Content-Security-Policy
  - X-Frame-Options
  - X-Content-Type-Options

### Testing

- **Unit Tests**: pytest with 69+ tests
- **Integration Tests**: API and database testing
- **E2E Tests**: Playwright for frontend workflows
- **Property-based Testing**: fast-check for edge cases

## Known Security Considerations

### Test Mode

- **TEST_MODE Environment Variable**: Switches between test and production databases
- **Warning**: Ensure `TEST_MODE=false` in production environments
- **Recommendation**: Use separate AWS accounts for test/production

### Third-party Integrations

- **Google Drive API**: OAuth2 credentials stored encrypted
- **OpenRouter API**: API keys in environment variables
- **AWS Services**: IAM credentials managed via AWS SDK

### File Uploads

- **PDF Processing**: PyPDF2, pypdf, pdfplumber for invoice extraction
- **File Validation**: Type checking on uploaded files
- **Storage**: Temporary storage in `backend/uploads/` directory
- **Recommendation**: Implement file size limits and virus scanning

## Security Best Practices for Deployment

### Railway Backend Configuration

Configure the following environment variables in Railway dashboard:

```bash
# Application Mode
TEST_MODE=false

# Database (Railway MySQL)
DB_HOST=<railway-mysql-host>
DB_PORT=3306
DB_USER=<db-user>
DB_PASSWORD=<strong-password>
DB_NAME=myAdmin

# Security Keys
CREDENTIALS_ENCRYPTION_KEY=<strong-random-key>
JWT_SECRET_KEY=<strong-random-key>

# AWS Configuration
AWS_ACCESS_KEY_ID=<iam-key>
AWS_SECRET_ACCESS_KEY=<iam-secret>
AWS_REGION=<region>
SNS_TOPIC_ARN=<sns-topic-arn>

# Cognito Configuration
COGNITO_USER_POOL_ID=<pool-id>
COGNITO_CLIENT_ID=<client-id>
COGNITO_REGION=<region>

# API Keys
OPENROUTER_API_KEY=<api-key>  # Optional for AI invoice extraction

# Google Drive (Optional)
GOOGLE_DRIVE_CREDENTIALS=<encrypted-credentials>
```

### Railway Security Settings

- **Private Networking**: MySQL service accessible only from backend service
- **Environment Variables**: All secrets stored in Railway dashboard (never in code)
- **Automatic HTTPS**: Railway provides SSL/TLS certificates automatically
- **Deploy Hooks**: Secure webhook for GitHub integration
- **Resource Limits**: Configure appropriate CPU/memory limits
- **Health Checks**: Implement `/health` endpoint for monitoring

### GitHub Pages Frontend Configuration

```bash
# frontend/.env.production
REACT_APP_API_URL=https://<your-railway-backend>.railway.app

# AWS Cognito (public configuration)
REACT_APP_AWS_REGION=<region>
REACT_APP_USER_POOL_ID=<pool-id>
REACT_APP_USER_POOL_WEB_CLIENT_ID=<client-id>
```

**Important**: Frontend `.env` values are public (embedded in static build). Never include secrets.

### Network Security

- **Railway Private Network**: MySQL only accessible from backend service
- **CORS Configuration**: Backend restricts origins to GitHub Pages domain
- **API Gateway**: Consider Cloudflare or AWS API Gateway for additional protection
- **Rate Limiting**: Implement in Flask backend or via Railway proxy
- **DDoS Protection**: Railway provides basic protection; consider Cloudflare for enhanced security

### Local Development Security (Docker)

For local Docker development:

```yaml
# docker-compose.yml security recommendations
services:
  mysql:
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
    volumes:
      - ./mysql_data:/var/lib/mysql
    networks:
      - internal # Internal network only
    ports:
      - "127.0.0.1:3306:3306" # Bind to localhost only

  backend:
    environment:
      - TEST_MODE=true # Use test mode locally
    networks:
      - internal
    ports:
      - "127.0.0.1:5000:5000" # Bind to localhost only
```

### Database Security

Railway MySQL is pre-configured with security best practices:

```sql
-- Verify user privileges (Railway manages this automatically)
SHOW GRANTS FOR CURRENT_USER;

-- Railway automatically:
-- - Restricts external access (private networking)
-- - Provides automatic backups
-- - Manages user permissions
-- - Enforces secure connections
```

**Best Practices**:

- Use Railway's private networking (enabled by default)
- Rotate database passwords regularly via Railway dashboard
- Enable automatic backups in Railway settings
- Monitor database metrics via Railway dashboard

## Vulnerability Disclosure Policy

### Our Commitment

- We will acknowledge receipt of your report within 48 hours
- We will provide regular updates on our progress
- We will credit you in our security advisories (unless you prefer anonymity)
- We will not take legal action against researchers who follow this policy

### Safe Harbor

We consider security research conducted under this policy to be:

- Authorized in accordance with applicable laws
- Lawful and helpful to the security of myAdmin
- Conducted in good faith

### Out of Scope

The following are explicitly out of scope:

- Social engineering attacks
- Physical attacks against myAdmin infrastructure
- Denial of Service (DoS/DDoS) attacks
- Spam or social engineering of myAdmin staff
- Attacks against third-party services (AWS, Google Drive, etc.)

## Security Updates

Security updates will be:

1. Developed and tested privately
2. Released as patches to supported versions
3. Announced via GitHub Security Advisories
4. Documented in CHANGELOG.md

## Compliance

myAdmin handles financial data and should be deployed in compliance with:

- **GDPR**: For EU personal data (if applicable)
- **PCI DSS**: For payment card data (if applicable)
- **SOC 2**: For service organization controls (recommended)
- **Local Regulations**: Financial data regulations in your jurisdiction

## Security Checklist for Deployment

### Railway Backend

- [ ] All environment variables configured in Railway dashboard
- [ ] `TEST_MODE=false` in production Railway service
- [ ] Railway private networking enabled for MySQL
- [ ] Strong database password set
- [ ] AWS IAM roles configured with least privilege
- [ ] Railway health checks configured
- [ ] Railway resource limits set appropriately
- [ ] Automatic deployments from `main` branch only

### GitHub Pages Frontend

- [ ] `REACT_APP_API_URL` points to Railway backend
- [ ] No secrets in frontend `.env` files
- [ ] HTTPS enforced on GitHub Pages
- [ ] Custom domain configured (if applicable)
- [ ] Build artifacts excluded from repository

### General Security

- [ ] CORS configured to allow only GitHub Pages domain
- [ ] Security headers implemented in Flask backend
- [ ] Rate limiting enabled on API endpoints
- [ ] File upload validation and size limits
- [ ] Regular dependency updates scheduled
- [ ] Audit logging enabled and monitored
- [ ] AWS CloudWatch logging configured
- [ ] Regular backups configured (Railway automatic backups enabled)
- [ ] Monitoring and alerting configured

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Railway Security Documentation](https://docs.railway.app/reference/private-networking)
- [GitHub Pages Security](https://docs.github.com/en/pages/getting-started-with-github-pages/securing-your-github-pages-site-with-https)
- [AWS Security Best Practices](https://aws.amazon.com/security/best-practices/)
- [Flask Security Considerations](https://flask.palletsprojects.com/en/latest/security/)
- [React Security Best Practices](https://reactjs.org/docs/dom-elements.html#dangerouslysetinnerhtml)

## Contact

For security-related questions or concerns:

- **Security Email**: [pjageers@gmail.com]
- **General Contact**: [peter@pgeers.nl]
- **GitHub Issues**: For non-security bugs only

---

**Last Updated**: 2026-03-07  
**Version**: 1.0
