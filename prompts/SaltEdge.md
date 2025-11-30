Salt Edge PSD2/Open Banking

Features:
✅ Free tier (100 connections/month)
✅ Unlimited transaction downloads once connected
✅ 90-day access per authorization
✅ All 7 bank accounts mapped
✅ CSV import still works

Done! Duplicate prevention:

Unique ID: Each Salt Edge transaction gets SE_{transaction_id} in Ref2

Database check: Queries existing Ref2 values for that IBAN

Filter duplicates: Only returns new transactions

User feedback: Shows how many duplicates were filtered

Same logic as CSV imports - uses the existing get_existing_sequences() method.

Do you have a layout of the records we receive from Salt Edge


Context
Based on Salt Edge API documentation, transaction records look like this:

{
  "id": "123456789",
  "duplicated": false,
  "mode": "normal",
  "status": "posted",
  "made_on": "2025-11-30",
  "amount": -50.00,
  "currency_code": "EUR",
  "description": "Payment to Store XYZ",
  "category": "shopping",
  "extra": {
    "account_balance_snapshot": 1234.56,
    "account_number": "NL80RABO0107936917",
    "payee": "Store XYZ",
    "payee_information": "Invoice 12345",
    "posting_date": "2025-11-30",
    "time": "14:30:00",
    "type": "card_transaction"
  },
  "account_id": "987654321",
  "created_at": "2025-11-30T14:30:00Z",
  "updated_at": "2025-11-30T14:30:00Z"
}


Copy
json
Key fields we use:

id → Ref2 (as SE_{id} for uniqueness)
made_on → TransactionDate
description → TransactionDescription
amount → TransactionAmount (absolute value)
amount sign → determines Debet/Credit
Fields we could add:
extra.account_balance_snapshot → Ref3 (like Revolut balance)
extra.payee → append to description
category → could map to account codes
Understood: The Salt Edge integration is ready and documented. When you're ready to enhance the field mapping, just let me know.

Summary:
✅ Salt Edge API integrated
✅ Duplicate prevention via Ref2
✅ Bank accounts from database
✅ Waiting for account approval (2 business days)
📝 Field mapping can be enhanced later