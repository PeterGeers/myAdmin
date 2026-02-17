# Using Railway's Native MySQL Database

## Overview

Railway provides a managed MySQL service with built-in persistent storage, automatic backups, and easy configuration. This is the recommended approach instead of custom Dockerfiles.

## Setup Steps

### Step 1: Add MySQL Database in Railway (2 minutes)

1. Go to Railway dashboard: https://railway.app/
2. Click **+ New**
3. Select **Database** → **Add MySQL**
4. Railway will create a MySQL service (currently MySQL 9.x) with persistent storage
5. Wait for deployment (1-2 minutes)

**Note**: Railway uses the latest stable MySQL version (currently 9.x). This is fully compatible with your Python MySQL connector and provides better performance than MySQL 8.0.

### Step 2: Get MySQL Connection Details (1 minute)

After the MySQL service is created:

1. Click on the MySQL service
2. Go to **Variables** tab
3. Note these values (Railway auto-generates them):
   - `MYSQLHOST` - Internal hostname (e.g., `mysql.railway.internal`)
     - **Important**: Copy the actual hostname value, not `${{RAILWAY_PRIVATE_DOMAIN}}`
   - `MYSQLPORT` - Port (usually `3306`)
   - `MYSQLUSER` - Username (usually `root`)
   - `MYSQLPASSWORD` - Auto-generated password
   - `MYSQLDATABASE` - Database name (usually `railway`)
   - `MYSQL_URL` - Full connection string

### Step 3: Update Backend Environment Variables (2 minutes)

In your **backend** service, add/update these variables:

```
DB_HOST = <actual MYSQLHOST value, e.g., mysql.railway.internal>
DB_PORT = 3306
DB_USER = <MYSQLUSER from MySQL service>
DB_PASSWORD = <MYSQLPASSWORD from MySQL service>
DB_NAME = <MYSQLDATABASE from MySQL service>
```

**Important**: Use the actual hostname value (like `mysql.railway.internal`), not the template variable `${{RAILWAY_PRIVATE_DOMAIN}}`.

Or use the connection string:

```
DATABASE_URL = <MYSQL_URL from MySQL service>
```

### Step 4: Get TCP Proxy for External Access (1 minute)

To import data from your local machine:

1. Click on the MySQL service
2. Go to **Settings** → **Networking**
3. Under **Public Networking**, click **Add TCP Proxy**
4. Port: `3306`
5. Note the proxy address (e.g., `proxy.railway.app:12345`)

### Step 5: Import Your Database (5-10 minutes)

Using the TCP proxy:

```bash
mysql -h <proxy-host> -P <proxy-port> -u <user> -p <database> < your_database.sql
```

Example:

```bash
mysql -h proxy.railway.app -P 12345 -u root -p railway < myDatabaseForRailway.sql
```

### Step 6: Verify Everything Works (2 minutes)

1. Check backend logs - should see successful database connection
2. Visit: https://invigorating-celebration-production.up.railway.app/api/db-test
   - Should show `status: success`
3. Test frontend: https://petergeers.github.io/myAdmin/
   - Log in and verify data loads

### Step 7: Delete Old Custom MySQL Service (1 minute)

**ONLY after verifying everything works:**

1. Go to Railway dashboard
2. Click on the old custom MySQL service (the crashing one)
3. Go to **Settings** → **Delete Service**
4. Confirm deletion

---

## Total Time: ~15 minutes

---

## Benefits of Native MySQL

✅ **Persistent Storage**: Built-in, no configuration needed
✅ **Automatic Backups**: Railway handles backups
✅ **Easy Management**: UI for queries, monitoring, logs
✅ **Reliable**: Tested and optimized by Railway
✅ **No Dockerfile**: No custom configuration to maintain
✅ **Auto-scaling**: Handles resource allocation
✅ **Monitoring**: Built-in metrics and alerts

## Database Management

### View Data

1. Click on MySQL service
2. Go to **Data** tab
3. Run queries directly in the UI

### Monitor Performance

1. Click on MySQL service
2. Go to **Metrics** tab
3. View CPU, memory, connections

### Backup/Restore

Railway automatically backs up your database. Contact Railway support for restore operations.

## Connection from Backend

Your backend's `database.py` already supports this configuration:

```python
config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'finance'),
    'port': int(os.getenv('DB_PORT', '3306'))
}
```

Just set the environment variables in Railway and it will work.

## Troubleshooting

### Backend can't connect

- Check environment variables are set in backend service
- Verify MySQL service is running
- Check internal hostname is correct

### Can't import data

- Verify TCP proxy is enabled
- Check firewall isn't blocking the proxy port
- Ensure you're using the correct credentials

### Data not persisting

- Railway's native MySQL has persistent storage by default
- No additional configuration needed
- Data survives redeploys automatically

## Cost

Railway's MySQL service is included in your plan:

- Hobby plan: Included with resource limits
- Pro plan: Pay for resources used
- Check Railway dashboard for current usage

## Next Steps

After MySQL is set up:

1. Import your database
2. Verify backend connection
3. Test the application
4. Set up regular backups (optional)
5. Monitor performance

## Support

If you encounter issues:

- Check Railway's status page
- Review Railway documentation: https://docs.railway.app/
- Contact Railway support through dashboard
