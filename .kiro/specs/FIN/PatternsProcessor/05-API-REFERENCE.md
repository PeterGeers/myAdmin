# API Reference

**Version**: 2.0  
**Last Updated**: January 27, 2026

---

## Authentication

All endpoints require Cognito JWT authentication.

**Header**: `Authorization: Bearer <token>`

---

## Endpoints

### Apply Patterns

**Endpoint**: `POST /api/banking/apply-patterns`  
**Permission**: `banking_process`  
**Tenant**: Required

**Request Body**:

```json
{
  "transactions": [
    {
      "TransactionDescription": "NETFLIX INTERNATIONAL B.V. Netflix Monthly Subscription",
      "Debet": "",
      "Credit": "1002",
      "ReferenceNumber": "",
      "administration": "GoodwinSolutions"
    }
  ],
  "test_mode": true,
  "use_enhanced": true
}
```

**Response**:

```json
{
  "success": true,
  "transactions": [
    {
      "TransactionDescription": "NETFLIX INTERNATIONAL B.V. Netflix Monthly Subscription",
      "Debet": "1300",
      "Credit": "1002",
      "ReferenceNumber": "NETFLIX",
      "administration": "GoodwinSolutions",
      "_debet_confidence": 1.0,
      "_reference_confidence": 1.0
    }
  ],
  "enhanced_results": {
    "predictions_made": {
      "debet": 1,
      "credit": 0,
      "reference": 1
    },
    "average_confidence": 1.0,
    "total_transactions": 1,
    "confidence_scores": [1.0, 1.0],
    "failed_predictions": 0
  },
  "method": "enhanced"
}
```

**Note**:

- `transactions` array contains the updated transactions with predicted values filled in
- Fields with predictions have corresponding `_<field>_confidence` metadata
- `enhanced_results` contains summary statistics about the predictions

---

### Save Transactions

**Endpoint**: `POST /api/banking/save-transactions`  
**Permission**: `transactions_create`  
**Tenant**: Required

**Request Body**:

```json
{
  "transactions": [...],
  "test_mode": true
}
```

**Response**:

```json
{
  "success": true,
  "saved_count": 10,
  "total_count": 12,
  "duplicate_count": 2,
  "table": "mutaties",
  "tenant": "GoodwinSolutions"
}
```

---

### Analyze Patterns

**Endpoint**: `POST /api/patterns/analyze/<administration>`  
**Permission**: `banking_process`

**Request Body**:

```json
{
  "incremental": false
}
```

**Response**:

```json
{
  "success": true,
  "analysis_type": "full",
  "administration": "GoodwinSolutions",
  "analysis_time": 10.234,
  "results": {
    "total_transactions": 2708,
    "patterns_discovered": 92
  }
}
```

---

### Get Pattern Summary

**Endpoint**: `GET /api/patterns/summary/<administration>`  
**Permission**: `banking_read`

**Response**:

```json
{
  "success": true,
  "summary": {
    "administration": "GoodwinSolutions",
    "total_patterns": 92,
    "date_range": {
      "from": "2024-01-27",
      "to": "2026-01-27"
    }
  }
}
```

---

### Get Incremental Stats

**Endpoint**: `GET /api/patterns/incremental-stats/<administration>`  
**Permission**: `banking_read`

**Response**:

```json
{
  "success": true,
  "incremental_stats": {
    "last_analysis": {
      "date": "2026-01-27T11:09:11",
      "transactions_analyzed": 2708,
      "patterns_discovered": 92
    },
    "pending_incremental_update": {
      "transactions_to_process": 12,
      "efficiency_gain": "99.6% reduction in processing"
    }
  }
}
```

---

## Error Responses

**400 Bad Request**:

```json
{
  "success": false,
  "error": "No transactions provided"
}
```

**401 Unauthorized**:

```json
{
  "error": "Missing Authorization header"
}
```

**500 Internal Server Error**:

```json
{
  "success": false,
  "error": "Database connection failed"
}
```

---

## Rate Limits

No rate limits currently enforced.

---

## References

- **Implementation**: See `03-IMPLEMENTATION.md` for code details
- **Architecture**: See `02-ARCHITECTURE.md` for system design
