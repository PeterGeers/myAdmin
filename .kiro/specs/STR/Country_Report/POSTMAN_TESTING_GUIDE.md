# Postman API Testing Guide - Country Report

## Quick Reference

**Endpoint:** `GET /api/bnb/generate-country-report`  
**Environment:** myAdmin Local  
**Token Refresh:** Every 1 hour (get from frontend localStorage)

---

## Running the Test

### 1. Open Postman Desktop App

(Cloud runner cannot reach localhost)

### 2. Select Environment

Top-right dropdown → **"myAdmin Local"**

### 3. Set Authentication Token

**Get token from frontend:**

1. Open http://localhost:3000 (login if needed)
2. DevTools (F12) → Application → Local Storage
3. Copy `idToken` value

**Set in Postman:**

1. Environment dropdown → "myAdmin Local" → Edit
2. Set `auth_token` = `Bearer <paste-token>`
3. Save

### 4. Create Request

**Method:** GET  
**URL:** `{{base_url}}/api/bnb/generate-country-report`

**Headers:**

- `Authorization: {{auth_token}}`

**Tests Script:**

```javascript
pm.test("Status code is 200", function () {
  pm.response.to.have.status(200);
});

pm.test("Response has success flag", function () {
  var jsonData = pm.response.json();
  pm.expect(jsonData.success).to.eql(true);
});

pm.test("Response has file path", function () {
  var jsonData = pm.response.json();
  pm.expect(jsonData.file_path).to.exist;
  pm.expect(jsonData.file_path).to.include("country_bookings_report.html");
});

pm.test("Response has statistics", function () {
  var jsonData = pm.response.json();
  pm.expect(jsonData.total_bookings).to.be.a("number");
  pm.expect(jsonData.countries).to.be.a("number");
  pm.expect(jsonData.regions).to.be.a("number");
});

console.log("Report generated at:", pm.response.json().file_path);
```

### 5. Run Request

Click **Send**

---

## Expected Response

```json
{
  "success": true,
  "message": "Report generated successfully",
  "file_path": "c:\\Users\\peter\\aws\\myAdmin\\backend\\reports\\country_bookings_report.html",
  "total_bookings": 150,
  "countries": 25,
  "regions": 5
}
```

---

## Verify HTML File

After successful API call:

1. Navigate to the `file_path` from the response
2. Open `country_bookings_report.html` in browser
3. Verify report contains:
   - Summary statistics (total bookings, countries, regions)
   - Region breakdown with percentages
   - Country details table
   - Beautiful styling with gradients

---

## Token Expiration

**Tokens expire after 1 hour**

When tests fail with 401:

1. Get fresh token from frontend (steps above)
2. Update Postman environment
3. Run again

---

## Troubleshooting

**401 Unauthorized:**

- Token expired → Get fresh token
- Missing "Bearer " prefix → Add it
- Wrong environment → Select "myAdmin Local"
- User lacks `str_read` permission → Check Cognito user groups

**Cannot connect:**

- Backend not running → `docker-compose up -d`

**500 Internal Server Error:**

- Check backend logs: `docker-compose logs -f backend`
- Verify database connection
- Check user has valid tenants

**File not found:**

- Check `backend/reports/` directory exists
- Verify write permissions

---

## Why Desktop App Only?

Postman cloud runner runs on Postman's servers and cannot reach localhost:5000.

For localhost testing: ✅ Desktop App  
For deployed APIs: ✅ Cloud runner works

---

## Multi-Tenant Testing

The endpoint filters data by user's tenants. To test different tenant data:

1. Login as different users in frontend
2. Get their respective tokens
3. Run the same request with different tokens
4. Verify each report shows only their tenant's data

---

## Documentation

- Implementation: `backend/src/bnb_routes.py` (line 477)
- Service: `backend/src/services/country_report_service.py`
- Spec: `.kiro/specs/STR/Country_Report/README.md`
