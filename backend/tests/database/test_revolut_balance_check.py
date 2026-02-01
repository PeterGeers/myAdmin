"""
Test script for Revolut balance gap detection
"""
import requests
import json

def test_revolut_balance_check():
    """Test the Revolut balance gap detection endpoint"""
    
    # API endpoint
    url = 'http://localhost:5000/api/banking/check-revolut-balance'
    
    # Parameters
    params = {
        'iban': 'NL08REVO7549383472',
        'account_code': '1022',
        'start_date': '2025-02-01',
        'expected_balance': '262.54'
    }
    
    print("Testing Revolut Balance Gap Detection")
    print("=" * 60)
    print(f"IBAN: {params['iban']}")
    print(f"Account: {params['account_code']}")
    print(f"Start Date: {params['start_date']}")
    print(f"Expected Balance: €{params['expected_balance']}")
    print("=" * 60)
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            print("\n✅ SUCCESS\n")
            
            # Summary
            print("SUMMARY:")
            print(f"  Total Transactions: {data['total_transactions']}")
            print(f"  Calculated Balance: €{data['calculated_final_balance']}")
            print(f"  Expected Balance: €{data['expected_final_balance']}")
            print(f"  Discrepancy: €{data['final_discrepancy']}")
            print(f"  Balance Gaps Found: {data['balance_gaps_found']}")
            
            # Balance gaps
            if data['balance_gaps_found'] > 0:
                print("\n⚠️  BALANCE GAPS DETECTED:")
                print("-" * 60)
                for gap in data['balance_gaps']:
                    print(f"\nDate: {gap['date']}")
                    print(f"Description: {gap['description']}")
                    print(f"Calculated: €{gap['calculated_balance']}")
                    print(f"Ref3 Balance: €{gap['ref3_balance']}")
                    print(f"Discrepancy: €{gap['discrepancy']}")
                    print(f"Ref2: {gap['ref2']}")
            else:
                print("\n✅ No balance gaps detected")
            
            # Show first few transactions
            print("\n\nFIRST 5 TRANSACTIONS:")
            print("-" * 60)
            for tx in data['all_transactions'][:5]:
                print(f"\n{tx['date']} - {tx['description']}")
                print(f"  Amount: €{tx['amount']} ({tx['direction']})")
                print(f"  Balance Change: €{tx['balance_change']}")
                print(f"  Calculated Balance: €{tx['calculated_balance']}")
                if tx['ref3_balance']:
                    print(f"  Ref3 Balance: €{tx['ref3_balance']}")
                    if tx['discrepancy']:
                        print(f"  Discrepancy: €{tx['discrepancy']}")
            
            # Summary analysis
            print("\n\nANALYSIS:")
            print("-" * 60)
            summary = data['summary']
            if summary['has_discrepancy']:
                if summary['missing_amount'] > 0:
                    print(f"⚠️  Missing transactions worth: €{summary['missing_amount']}")
                if summary['extra_amount'] > 0:
                    print(f"⚠️  Extra transactions worth: €{summary['extra_amount']}")
            else:
                print("✅ Balance matches perfectly!")
            
        else:
            print(f"\n❌ ERROR: {data.get('error', 'Unknown error')}")
            
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Request failed: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")

if __name__ == '__main__':
    test_revolut_balance_check()
