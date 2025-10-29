from transaction_logic import TransactionLogic

def debug_vendor_data():
    try:
        logic = TransactionLogic()
        
        # Simulate the exact data structure from upload
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
        
        print("=== VENDOR DATA DEBUG ===")
        print(f"Vendor data: {new_data['vendor_data']}")
        print()
        
        # Get templates
        templates = logic.get_last_transactions("Booking.com")
        
        # Prepare transactions
        prepared = logic.prepare_new_transactions(templates, new_data)
        
        print("=== PREPARED TRANSACTIONS ===")
        for i, trans in enumerate(prepared):
            print(f"Record {i+1}:")
            print(f"  Date: {trans['TransactionDate']} (should be 2025-10-03)")
            print(f"  Amount: {trans['TransactionAmount']} (should be {114.37 if i==0 else 19.85})")
            print(f"  Description: {trans['TransactionDescription']}")
            print()
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_vendor_data()