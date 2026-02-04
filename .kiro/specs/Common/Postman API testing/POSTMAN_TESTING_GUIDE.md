# Postman API Testing Guide - STR Channel BTW Rate

## Quick Reference

**Collection:** STR Channel Revenue API - BTW Rate Testing (Auto-Auth)  
**Environment:** myAdmin Local  
**Token Refresh:** Every 1 hour (get from frontend localStorage)

---

## Running the Tests

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

### 4. Run Collection

Find "STR Channel Revenue API - BTW Rate Testing (Auto-Auth)" → Run

---

## Expected Results

✅ **8/8 tests pass:**

- December 2025: 9% rate, account '2021'
- January 2026: 21% rate, account '2020'
- February 2026: 21% rate, account '2020'

---

## Token Expiration

**Tokens expire after 1 hour**

When tests fail with 401:

1. Get fresh token from frontend (steps above)
2. Update Postman environment
3. Run again

The pre-request script logs helpful instructions in Postman Console.

---

## Troubleshooting

**401 Unauthorized:**

- Token expired → Get fresh token
- Missing "Bearer " prefix → Add it
- Wrong environment → Select "myAdmin Local"

**Cannot connect:**

- Backend not running → `docker-compose up -d`

**Tests fail immediately:**

- Check environment is "myAdmin Local" (not "webshopBeackend")

---

## Why Desktop App Only?

Postman cloud runner runs on Postman's servers and cannot reach localhost:5000.

For localhost testing: ✅ Desktop App  
For deployed APIs: ✅ Cloud runner works

---

## Documentation

- Collection ID: `.postman.json`
