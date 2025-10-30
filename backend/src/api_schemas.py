EXPECTED_SCHEMAS = {
    '/api/reports/actuals-profitloss': {
        'required_fields': ['Parent', 'ledger', 'jaar', 'Amount'],
        'description': 'Profit/Loss data with hierarchical structure'
    },
    '/api/reports/actuals-balance': {
        'required_fields': ['Parent', 'ledger', 'Amount'],
        'description': 'Balance data grouped by Parent and ledger'
    }
}

def validate_response_schema(endpoint, data):
    """Validate API response matches expected schema"""
    if endpoint not in EXPECTED_SCHEMAS:
        return True
    
    schema = EXPECTED_SCHEMAS[endpoint]
    if not data or not isinstance(data, list) or not data:
        return True
    
    first_record = data[0]
    missing_fields = [field for field in schema['required_fields'] if field not in first_record]
    
    if missing_fields:
        print(f"⚠️  SCHEMA MISMATCH in {endpoint}: Missing fields {missing_fields}")
        return False
    return True