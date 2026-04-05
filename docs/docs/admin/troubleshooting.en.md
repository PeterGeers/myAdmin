# Troubleshooting

> Common platform issues and solutions.

## Overview

This page describes common problems you may encounter as SysAdmin and how to resolve them.

## Application won't start

| Symptom                            | Possible cause              | Solution                                                            |
| ---------------------------------- | --------------------------- | ------------------------------------------------------------------- |
| Backend gives "Connection refused" | MySQL not ready yet         | Wait 40 seconds after `docker-compose up -d` or restart the backend |
| "Module not found" error           | Python dependencies missing | Run `docker-compose up -d --build` to rebuild                       |
| Frontend shows white page          | Build is outdated           | Rebuild the frontend with `npm run build` in the frontend directory |
| Health check fails                 | Backend crashes on startup  | Check logs with `docker-compose logs backend`                       |

## Database issues

| Symptom                | Possible cause               | Solution                                            |
| ---------------------- | ---------------------------- | --------------------------------------------------- |
| "Access denied"        | Wrong credentials            | Check `DB_USER` and `DB_PASSWORD` in `backend/.env` |
| "Table doesn't exist"  | Views not created            | Run `python scripts/database/fix_database_views.py` |
| Slow performance       | Large tables without indexes | Check indexes and consider archiving old data       |
| "Too many connections" | Connection pool exhausted    | Restart the backend container                       |

## Authentication issues

| Symptom                | Possible cause                  | Solution                                                |
| ---------------------- | ------------------------------- | ------------------------------------------------------- |
| "Invalid token"        | Cognito configuration incorrect | Check `COGNITO_USER_POOL_ID` and `AWS_REGION` in `.env` |
| User can't log in      | Account not activated           | Check user status in AWS Cognito Console                |
| "Access denied" on API | Missing role                    | Assign the correct Cognito group to the user            |
| Token expired          | Session inactive too long       | User needs to log in again                              |

## Google Drive issues

| Symptom                       | Possible cause             | Solution                                    |
| ----------------------------- | -------------------------- | ------------------------------------------- |
| "OAuth credentials not found" | Credentials not configured | Configure Google Drive OAuth for the tenant |
| Upload fails                  | Token expired              | Refresh the Google Drive OAuth token        |
| Files not accessible          | Insufficient permissions   | Check Google Drive permissions              |

## Tenant issues

| Symptom             | Possible cause            | Solution                                                               |
| ------------------- | ------------------------- | ---------------------------------------------------------------------- |
| Tenant sees no data | Wrong administration name | Check that the administration name matches in Cognito and the database |
| Modules not visible | Modules not assigned      | Assign modules via the SysAdmin panel                                  |
| Provisioning failed | AWS Cognito API error     | Check AWS credentials and try reprovisioning                           |

## Diagnostic commands

### Container status

```bash
docker-compose ps
docker-compose logs --tail=50 backend
docker-compose logs --tail=50 mysql
```

### Database connectivity

```bash
docker-compose exec mysql mysqladmin -u peter -p ping
```

### API health check

```bash
curl http://localhost:5000/api/health
```

### Disk usage

```bash
du -sh ./mysql_data/
docker system df
```

## Tips

!!! tip
Always save the last 50 lines of backend logs when reporting a problem. This helps quickly identify the cause.

- Always check logs before restarting containers
- Most problems are caused by incorrect `.env` configuration
- When in doubt: restart containers with `docker-compose down && docker-compose up -d`
