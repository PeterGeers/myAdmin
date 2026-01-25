The current cachce logic works in the backend is trhis the way to move forward for a multi tennant system

We need to remove tthe refresh cacjhe buttobn and only load the data related to the tennant als when tennat changes. The field Administration can be rnov ed as this is the tennat and in ledger uyou will only see the ledger codes of the tennat

Kiro
You're absolutely right. Let me pause on the cache refactoring and focus on what you asked for:

For the "Check Reference Numbers" tab:
✅ Remove "Refresh Cache" button - Already done
✅ Remove "Administration" field - It's now read-only showing current tenant
Auto-reload when tenant changes - Already done with useEffect
Ledger dropdown shows only current tenant's accounts - Already filtered by backend
Let me verify the current state and rebuild the frontend: