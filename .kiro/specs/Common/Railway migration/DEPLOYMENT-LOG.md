https://invigorating-celebration-production.up.railway.app/api/health


  "endpoints": [
    "str/upload",
    "str/scan-files",
    "str/process-files",
    "str/save",
    "str/write-future"
  ],
  "scalability": {
    "concurrent_user_capacity": "1x baseline",
    "manager_active": false
  },
  "status": "healthy"
}


https://invigorating-celebration-production.up.railway.app/api/status
{
  "error": "Suspicious request detected"
}


https://invigorating-celebration-production.up.railway.app/api/reports/
{
  "error": "Suspicious request detected"
}


The last 2 errors ["error": "Suspicious request detected"] are probably due to the need for JWT Tokens coming from Cognito Access