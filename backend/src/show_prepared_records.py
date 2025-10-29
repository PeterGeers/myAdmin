from transaction_logic import TransactionLogic
import json

def show_prepared_records():
    try:
        logic = TransactionLogic()
        
        # Get Booking.com template transactions
        template_transactions = logic.get_last_transactions("Booking.com")
        
        # Simulate new data from PDF processing
        new_data = {
            'folder_name': 'Booking.com',
            'description': 'PDF processed from invoice-1640115935.pdf',
            'amount': 0,
            'drive_url': 'http://localhost:5000/uploads/invoice-1640115935.pdf',
            'filename': 'invoice-1640115935.pdf',
            'vendor_data': {
                'date': '2025-10-03',
                'description': 'Accommodation 4392906 Invoice number: 1640115935 2025-10-03',
                'total_amount': 114.37,
                'vat_amount': 19.85,
                'accommodation_number': '4392906',
                'invoice_number': '1640115935'
            }
        }
        
        # Prepare new transactions
        prepared_transactions = logic.prepare_new_transactions(template_transactions, new_data)
        
        print("=== PREPARED RECORDS FOR DATABASE ===")
        print(f"Number of records: {len(prepared_transactions)}")
        print()
        
        for i, transaction in enumerate(prepared_transactions, 1):
            print(f"RECORD {i}:")
            print(f"  ID: {transaction['ID']}")
            print(f"  TransactionNumber: {transaction['TransactionNumber']}")
            print(f"  TransactionDate: {transaction['TransactionDate']}")
            print(f"  TransactionDescription: {transaction['TransactionDescription']}")
            print(f"  TransactionAmount: {transaction['TransactionAmount']}")
            print(f"  Debet: {transaction['Debet']}")
            print(f"  Credit: {transaction['Credit']}")
            print(f"  ReferenceNumber: {transaction['ReferenceNumber']}")
            print(f"  Ref1: {transaction['Ref1']}")
            print(f"  Ref2: {transaction['Ref2']}")
            print(f"  Ref3: {transaction['Ref3']}")
            print(f"  Ref4: {transaction['Ref4']}")
            print(f"  Administration: {transaction['Administration']}")
            # _template_id removed - not stored in database
            print()
        
        print("=== TEMPLATE TRANSACTIONS (for reference) ===")
        for i, template in enumerate(template_transactions, 1):
            print(f"TEMPLATE {i}:")
            print(f"  TransactionNumber: {template['TransactionNumber']}")
            print(f"  TransactionDate: {template['TransactionDate']}")
            print(f"  TransactionAmount: {template['TransactionAmount']}")
            print(f"  Debet: {template['Debet']}")
            print(f"  Credit: {template['Credit']}")
            print(f"  ReferenceNumber: {template.get('ReferenceNumber', 'N/A')}")
            print(f"  Administration: {template.get('Administration', 'N/A')}")
            print(f"  Ref3: {template['Ref3']}")
            print(f"  Ref4: {template['Ref4']}")
            print()
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    show_prepared_records()