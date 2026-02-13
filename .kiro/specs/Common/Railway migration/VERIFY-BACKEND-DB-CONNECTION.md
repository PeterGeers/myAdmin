# Verify Backend Can Connect to Railway Database

**Task**: Confirm the backend application can successfully connect to the Railway MySQL database.

---

## Understanding Railway Database Connection

### On Railway (Production)

When the backend runs on Railway, it uses **internal service references**:

```bash
DB_HOST=${{mysql.RAILWAY_PRIVATE_DOMAIN}}
```

Railway automatically resolves this to the MySQL service's internal hostname (e.g., `mysql.railway.internal`). This only works within Railway's private network.

### From Local Machine (Testing)

To test the Railway database from your local machine, you need the **public connection details**:

1. Go to Railway Dashboard → MySQL service
2. Click **Connect** tab
3. Look for **Public TCP Proxy** section
4. Copy the connection details:
   - Host: `monorail.proxy.rlwy.net` (or similar)
   - Port: `12345` (unique port number)
   - Username: `peter`
   - Password: (from Railway variables)
   - Database: `finance`

---

## Verification Methods

### Method 1: Check Railway Deployment Logs

The easiest way to verify the backend can connect is to check the Railway deployment logs:

1. Go to Railway Dashboard → Backend service
2. Click **Deployments** tab
3. View the latest deployment logs
4. Look for:
   - ✅ "DatabaseManager initialized successfully"
   - ✅ "Connection pool initialized"
   - ❌ Any MySQL connection errors

### Method 2: Test Health Endpoint

The backend health endpoint will fail if database connection is broken:

```bash
curl https://invigorating-celebration-production.up.railway.app/api/health
```

Expected response:

```json
{
  "status": "healthy",
  "endpoints": [...],
  "scalability": {...}
}
```

If database connection fails, you'll see errors in Railway logs.

### Method 3: Test from Local Machine (Optional)

To test Railway database from your local machine:

1. **Get Railway MySQL public connection details** (see above)

2. **Update `backend/.env` temporarily**:

   ```bash
   DB_HOST=monorail.proxy.rlwy.net  # Railway public host
   DB_PORT=12345                     # Railway public port
   DB_USER=peter
   DB_PASSWORD=<from-railway>
   DB_NAME=finance
   ```

3. **Run the test script**:

   ```bash
   python backend/test_railway_connection.py
   ```

4. **Expected output**:

   ```
   ✅ Successfully imported DatabaseManager
   ✅ DatabaseManager initialized successfully
   ✅ Successfully obtained database connection
   ✅ Successfully executed test query
   ✅ Found X tables in database
   ✅ mutaties table has X rows
   ✅ ALL TESTS PASSED
   ```

5. **Revert `backend/.env`** back to `localhost` for local development

---

## Success Criteria

The task "Backend can connect to database" is complete when:

- ✅ Backend is deployed on Railway
- ✅ Railway deployment logs show successful database connection
- ✅ Health endpoint returns `{"status": "healthy"}`
- ✅ No database connection errors in Railway logs
- ✅ Backend can query database tables (verified via logs or test endpoints)

---

## Current Status

Based on the deployment documentation:

- ✅ Backend deployed to Railway
- ✅ MySQL service provisioned
- ✅ Environment variables configured with `${{mysql.RAILWAY_PRIVATE_DOMAIN}}`
- ✅ Health endpoint working: https://invigorating-celebration-production.up.railway.app/api/health
- ⏳ Database imported (pending - see IMPORT-EXISTING-BACKUP.md)

**Note**: The backend can connect to the Railway MySQL service, but the database is currently empty. Once you import your local database (Phase 6.3 in TASKS.md), the backend will have access to all your data.

---

## Troubleshooting

### Error: "Unknown MySQL server host"

**From local machine**: You're using the internal hostname. Use the public Railway MySQL hostname instead.

**From Railway**: The MySQL service may not be running. Check Railway dashboard.

### Error: "Access denied for user"

Check that Railway environment variables match:

- `DB_USER` matches MySQL username
- `DB_PASSWORD` matches `${{mysql.MYSQL_PASSWORD}}`

### Error: "Can't connect to MySQL server"

- Check MySQL service is running in Railway dashboard
- Verify `DB_HOST=${{mysql.RAILWAY_PRIVATE_DOMAIN}}` is set correctly
- Check Railway logs for MySQL service errors

---

## Next Steps

Once backend connection is verified:

1. Import local database to Railway (see IMPORT-EXISTING-BACKUP.md)
2. Test database queries work
3. Deploy frontend
4. Test end-to-end functionality
