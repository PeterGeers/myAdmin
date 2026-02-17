# Clear Volume and Start Fresh with MySQL 8.0

## Problem

The volume contains MySQL 9.4 data, but you want to use MySQL 8.0.44. MySQL 8.0 cannot read MySQL 9.4 data files.

## Solution

Clear the volume and let MySQL 8.0 initialize fresh, then import your database.

## Steps

### Option 1: Delete and Recreate Volume (Railway Dashboard)

Unfortunately, Railway doesn't provide a UI to delete volumes for custom services. You'll need to use the CLI or recreate the service.

### Option 2: Use Railway CLI to Delete Volume

```bash
# Install Railway CLI if not already installed
npm i -g @railway/cli

# Login
railway login

# Link to your project
railway link

# List volumes
railway volume list

# Delete the volume (use the volume ID from the logs: vol_5m6mm0ak6spbbsfw)
railway volume delete vol_5m6mm0ak6spbbsfw

# Redeploy the mysql service
railway up -s mysql
```

### Option 3: Recreate the MySQL Service (EASIEST)

1. **Delete the current mysql service:**
   - Go to Railway dashboard
   - Click on the mysql service (devoted-contentment)
   - Settings → Delete Service
   - Confirm deletion

2. **Create new mysql service from your template:**
   - In Railway dashboard, click **+ New**
   - Select **Empty Service**
   - Settings → Connect Repo
   - Select your GitHub repo: PeterGeers/myAdmin
   - Root Directory: `railway/mysql`
   - Branch: `main`

3. **Configure the new service:**
   - Service name: `mysql`
   - Add environment variables:
     ```
     MYSQL_ROOT_PASSWORD=Kx9mP2vL8nQ5wR7jT4MyAdmin2026
     MYSQL_DATABASE=finance
     MYSQL_USER=peter
     MYSQL_PASSWORD=Kx9mP2vL8nQ5wR7jT4MyAdmin2026
     ```

4. **Add TCP proxy:**
   - Settings → Networking → Add TCP Proxy
   - Port: 3306

5. **Wait for deployment** (2-3 minutes)

6. **Note the new internal hostname** (will be different from devoted-contentment.railway.internal)

7. **Update backend environment variables** with new hostname

8. **Import your database:**
   ```bash
   mysql -h <new-tcp-proxy-host> -P <new-tcp-proxy-port> -u peter -p finance < your_database.sql
   ```

### Option 4: Clear Volume Data Manually

If you can connect to the mysql service:

1. Connect via TCP proxy:

   ```bash
   mysql -h metro.proxy.rlwy.net -P 21393 -u root -p
   ```

2. Drop and recreate the database:

   ```sql
   DROP DATABASE IF EXISTS finance;
   CREATE DATABASE finance;
   ```

3. Restart the mysql service in Railway

4. Import your database

## After Clearing Volume

1. MySQL 8.0 will initialize fresh
2. Import your database
3. Data will persist across redeploys
4. No more version mismatch errors

## Recommended Approach

**Option 3 (Recreate Service)** is the cleanest and easiest:

- Fresh start with MySQL 8.0
- No volume conflicts
- Clear configuration
- Takes about 10 minutes total

## Alternative: Switch to MySQL 9.4

If you don't want to deal with clearing the volume, you could:

1. Change Dockerfile to `FROM mysql:9.4`
2. Redeploy
3. MySQL will start with existing data
4. No import needed

But if you specifically need MySQL 8.0.44, follow Option 3 above.
