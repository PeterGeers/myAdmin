# myAdmin Setup Guide

## Prerequisites

- Docker Desktop installed and running
- AWS account with Cognito configured
- AWS IAM credentials with Cognito permissions

---

## Initial Setup

### 1. Configure Backend Environment

```powershell
# Copy the example file
Copy-Item backend/.env.example backend/.env

# Edit backend/.env and fill in all required values
notepad backend/.env
```

**Required Variables:**

- `COGNITO_USER_POOL_ID` - From AWS Cognito Console
- `COGNITO_CLIENT_ID` - From AWS Cognito Console
- `COGNITO_CLIENT_SECRET` - From AWS Cognito Console
- `AWS_REGION` - Your AWS region (e.g., eu-west-1)
- `AWS_ACCESS_KEY_ID` - From ~/.aws/credentials or AWS IAM
- `AWS_SECRET_ACCESS_KEY` - From ~/.aws/credentials or AWS IAM
- `DB_PASSWORD` - Your MySQL password
- `FACTUREN_FOLDER_ID` - Google Drive folder ID
- `OPENROUTER_API_KEY` - OpenRouter API key

### 2. Verify Setup

```powershell
# Run the verification script
.\scripts\verify-setup.ps1
```

This will check:

- ✅ All required environment variables are set
- ✅ Docker is running
- ✅ Containers are running

### 3. Start the Application

```powershell
# Start all containers
docker-compose up -d

# Check logs
docker logs myadmin-backend-1 --tail 50
```

---

## Common Issues

### "NoCredentialsError: Unable to locate credentials"

**Cause**: Missing AWS_ACCESS_KEY_ID or AWS_SECRET_ACCESS_KEY

**Solution**:

1. Check if you have `~/.aws/credentials` file
2. Copy the credentials to `backend/.env`:
   ```
   AWS_ACCESS_KEY_ID=your-key-here
   AWS_SECRET_ACCESS_KEY=your-secret-here
   ```
3. Restart backend: `docker restart myadmin-backend-1`

### "System Administration page shows 500 error"

**Cause**: Missing AWS credentials or Cognito configuration

**Solution**:

1. Run `.\scripts\verify-setup.ps1` to check configuration
2. Ensure all AWS variables are set in `backend/.env`
3. Restart backend after fixing

### "Database connection failed"

**Cause**: MySQL container not running or wrong credentials

**Solution**:

1. Check MySQL is running: `docker ps | findstr mysql`
2. Verify DB_PASSWORD in `backend/.env` matches MYSQL_ROOT_PASSWORD
3. Restart containers: `docker-compose restart`

---

## Environment Variable Reference

### AWS Cognito (Required)

```
COGNITO_USER_POOL_ID=eu-west-1_XXXXXXXXX
COGNITO_CLIENT_ID=your-client-id
COGNITO_CLIENT_SECRET=your-client-secret
AWS_REGION=eu-west-1
```

### AWS IAM (Required for backend API calls)

```
AWS_ACCESS_KEY_ID=AKIAXXXXXXXXXXXXXXXX
AWS_SECRET_ACCESS_KEY=your-secret-access-key
```

### Database (Required)

```
DB_HOST=localhost
DB_USER=peter
DB_PASSWORD=your-password
DB_NAME=finance
MYSQL_ROOT_PASSWORD=your-password
```

### Google Drive (Required)

```
FACTUREN_FOLDER_ID=your-folder-id
FACTUREN_FOLDER_NAME=Facturen
```

### OpenRouter AI (Required)

```
OPENROUTER_API_KEY=sk-or-v1-your-key
```

### AWS SNS (Optional)

```
SNS_TOPIC_ARN=arn:aws:sns:eu-west-1:account-id:topic-name
```

---

## Maintenance

### Update Environment Variables

1. Edit `backend/.env`
2. Restart backend: `docker restart myadmin-backend-1`
3. Verify: `.\scripts\verify-setup.ps1`

### Check Backend Logs

```powershell
# View recent logs
docker logs myadmin-backend-1 --tail 100

# Follow logs in real-time
docker logs myadmin-backend-1 --follow
```

### Rebuild Containers

```powershell
# Rebuild and restart
docker-compose up -d --build
```

---

## Security Notes

- ⚠️ **NEVER commit .env files to git**
- ⚠️ **Keep AWS credentials secure**
- ⚠️ **Rotate credentials regularly**
- ⚠️ **Use IAM roles with minimal permissions**

---

## Getting Help

If you encounter issues:

1. Run verification: `.\scripts\verify-setup.ps1`
2. Check backend logs: `docker logs myadmin-backend-1 --tail 100`
3. Verify all environment variables are set
4. Ensure Docker containers are running
5. Check AWS credentials are valid

---

## Quick Reference

```powershell
# Verify setup
.\scripts\verify-setup.ps1

# Start application
docker-compose up -d

# Stop application
docker-compose down

# Restart backend
docker restart myadmin-backend-1

# View logs
docker logs myadmin-backend-1 --tail 50

# Rebuild
docker-compose up -d --build
```
