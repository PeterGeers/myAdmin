"""
Test both Revolut balance endpoints to compare results
"""
import requests
import json

BASE_URL = "http://localhost:5000"

def test_debug_endpoint():
    """Test the debug endpoint (first 10 transactions)"""
    print("\n=== TESTING DEBUG ENDPOINT ===")
    url = f"{BASE_URL}/api/banking/check-revolut-balance-debug"
    params = {
        'iban': 'NL08REVO7549383472',
        'account_code': '1022',
        'start_date': '2025-05-01',
        'expected_balance': '262.54'
    }
    
    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Total transactions: {data.get('total_transactions')}")
        print(f"\nFirst 10 transactions:")
        for tx in data.get('first_10_transactions', [])[:10]:
            print(f"  ID: {tx['id']}, Date: {tx['transaction_date']}, "
                  f"Desc: {tx['description'][:30]}, "
                  f"Calc: {tx['calculated_balance']}, Ref3: {tx['ref3_balance']}, "
                  f"Discrepancy: {tx['discrepancy']}")
        
        # Save to file
        with open('revolut_debug_new.json', 'w') as f:
            json.dump(data, f, indent=2)
        print("\nSaved to revolut_debug_new.json")
    else:
        print(f"Error: {response.text}")

def test_full_endpoint():
    """Test the full endpoint (gaps only)"""
    print("\n=== TESTING FULL ENDPOINT ===")
    url = f"{BASE_URL}/api/banking/check-revolut-balance"
    params = {
        'iban': 'NL08REVO7549383472',
        'account_code': '1022',
        'start_date': '2025-05-01',
        'expected_balance': '262.54'
    }
    
    response = requests.get(url, params=params)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Total transactions: {data.get('total_transactions')}")
        print(f"Balance gaps found: {data.get('balance_gaps_found')}")
        print(f"Final discrepancy: {data.get('final_discrepancy')}")
        
        print(f"\nFirst 10 transactions with gaps:")
        for tx in data.get('transactions_with_gaps', [])[:10]:
            print(f"  ID: {tx['id']}, Date: {tx['transaction_date']}, "
                  f"Desc: {tx['description'][:30]}, "
                  f"Calc: {tx['calculated_balance']}, Ref3: {tx['ref3_balance']}, "
                  f"Discrepancy: {tx['discrepancy']}")
        
        # Save to file
        with open('revolut_gaps_new.json', 'w') as f:
            json.dump(data, f, indent=2)
        print("\nSaved to revolut_gaps_new.json")
    else:
        print(f"Error: {response.text}")

if __name__ == '__main__':
    test_debug_endpoint()
    test_full_endpoint()
