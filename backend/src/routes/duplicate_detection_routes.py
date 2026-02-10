"""
Duplicate Detection Routes Blueprint
Handles duplicate transaction detection and user decision logging
"""
from flask import Blueprint, request, jsonify, Response
from auth.cognito_utils import cognito_required
from database import DatabaseManager
from duplicate_checker import DuplicateChecker
from datetime import datetime
import json

# Create blueprint
duplicate_detection_bp = Blueprint('duplicate_detection', __name__)

# Global variables set by app.py
flag = False  # Test mode flag

def set_test_mode(test_mode):
    """Set test mode flag"""
    global flag
    flag = test_mode


@duplicate_detection_bp.route('/api/check-duplicate', methods=['POST'])
@cognito_required(required_permissions=['invoices_read'])
def check_duplicate(user_email, user_roles):
    """Check for duplicate transactions during import process"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['referenceNumber', 'transactionDate', 'transactionAmount']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'Missing required field: {field}'
                }), 400
        
        reference_number = data.get('referenceNumber')
        transaction_date = data.get('transactionDate')
        transaction_amount = float(data.get('transactionAmount'))
        table_name = data.get('tableName', 'mutaties')
        new_file_url = data.get('newFileUrl', '')
        new_file_id = data.get('newFileId', '')
        
        # Initialize duplicate checker with database manager
        db_manager = DatabaseManager(test_mode=flag)
        duplicate_checker = DuplicateChecker(db_manager)
        
        # Check for duplicates
        duplicates = duplicate_checker.check_for_duplicates(
            reference_number, transaction_date, transaction_amount, table_name
        )
        
        # Format duplicate information for frontend
        duplicate_info = duplicate_checker.format_duplicate_info(duplicates)
        
        # Add additional metadata for frontend
        duplicate_info.update({
            'newFileUrl': new_file_url,
            'newFileId': new_file_id,
            'tableName': table_name,
            'checkTimestamp': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'duplicateInfo': duplicate_info
        })
        
    except ValueError as e:
        return jsonify({
            'success': False, 
            'error': f'Invalid data format: {str(e)}'
        }), 400
    except Exception as e:
        print(f"Duplicate check error: {e}", flush=True)
        # Return graceful degradation - allow import to continue with warning
        return jsonify({
            'success': True,
            'duplicateInfo': {
                'has_duplicates': False,
                'duplicate_count': 0,
                'existing_transactions': [],
                'requires_user_decision': False,
                'error_message': f'Duplicate check failed: {str(e)}',
                'checkTimestamp': datetime.now().isoformat()
            }
        }), 200


@duplicate_detection_bp.route('/api/log-duplicate-decision', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
def log_duplicate_decision(user_email, user_roles):
    """Log user decision regarding duplicate transaction for audit trail"""
    try:
        data = request.get_json()
        print(f"Received duplicate decision data: {data}", flush=True)
        
        # Validate required fields
        decision = data.get('decision')
        if not decision:
            return jsonify({
                'success': False, 
                'error': 'Missing required field: decision'
            }), 400
        
        # Get duplicate info and new transaction data
        # Support both camelCase (from frontend) and snake_case
        duplicate_info = data.get('duplicateInfo') or data.get('duplicate_info')
        new_transaction_data = data.get('newTransactionData') or data.get('new_transaction_data')
        
        # Validate that we have the required data
        if not new_transaction_data:
            return jsonify({
                'success': False,
                'error': 'Missing required field: newTransactionData'
            }), 400
        
        # Ensure duplicate_info is at least an empty dict
        if duplicate_info is None:
            duplicate_info = {}
        
        # Fix existing_transaction_id - convert empty string to None for NULL in database
        existing_id = duplicate_info.get('existing_transaction_id', '')
        if existing_id == '' or existing_id is None:
            existing_id = None
        else:
            try:
                existing_id = int(existing_id)
            except (ValueError, TypeError):
                existing_id = None
        
        user_id = data.get('userId')
        session_id = data.get('sessionId')
        
        # Validate decision value
        if decision not in ['continue', 'cancel']:
            return jsonify({
                'success': False, 
                'error': 'Decision must be either "continue" or "cancel"'
            }), 400
        
        # Initialize duplicate checker with database manager
        db_manager = DatabaseManager(test_mode=flag)
        duplicate_checker = DuplicateChecker(db_manager)
        
        # Log the decision
        log_success = duplicate_checker.log_duplicate_decision(
            decision=decision,
            duplicate_info=duplicate_info,
            new_transaction_data=new_transaction_data,
            user_id=user_id,
            session_id=session_id
        )
        
        if log_success:
            return jsonify({
                'success': True,
                'message': f'Decision "{decision}" logged successfully',
                'logTimestamp': datetime.now().isoformat()
            })
        else:
            # Even if logging fails, don't block the user's workflow
            return jsonify({
                'success': True,
                'message': f'Decision "{decision}" processed (logging may have failed)',
                'warning': 'Audit logging encountered an issue',
                'logTimestamp': datetime.now().isoformat()
            })
        
    except Exception as e:
        print(f"Decision logging error: {e}", flush=True)
        # Don't fail the user's workflow even if logging fails
        return jsonify({
            'success': True,
            'message': 'Decision processed (logging failed)',
            'error': str(e),
            'logTimestamp': datetime.now().isoformat()
        }), 200


@duplicate_detection_bp.route('/api/handle-duplicate-decision', methods=['POST'])
@cognito_required(required_permissions=['invoices_create'])
def handle_duplicate_decision(user_email, user_roles):
    """Handle user decision for duplicate transactions with full workflow processing"""
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['decision', 'duplicateInfo', 'transactions', 'fileData']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False, 
                    'error': f'Missing required field: {field}'
                }), 400
        
        decision = data.get('decision')
        duplicate_info = data.get('duplicateInfo')
        transactions = data.get('transactions')
        file_data = data.get('fileData')
        user_id = data.get('userId')
        session_id = data.get('sessionId')
        
        # Validate decision value
        if decision not in ['continue', 'cancel']:
            return jsonify({
                'success': False, 
                'error': 'Decision must be either "continue" or "cancel"'
            }), 400
        
        # Initialize PDF processor for decision handling
        from pdf_processor import PDFProcessor
        pdf_processor = PDFProcessor(test_mode=flag)
        
        # Handle the user decision
        result = pdf_processor.handle_duplicate_decision(
            decision, duplicate_info, transactions, file_data, user_id, session_id
        )
        
        # If decision was to continue, we need to process the transactions
        if result['success'] and decision == 'continue' and result['transactions']:
            try:
                # Initialize database manager for transaction insertion
                db_manager = DatabaseManager(test_mode=flag)
                
                # Insert transactions into database
                inserted_count = 0
                for transaction in result['transactions']:
                    # Format transaction for database insertion
                    db_transaction = {
                        'TransactionDate': transaction['date'],
                        'TransactionDescription': transaction['description'],
                        'TransactionAmount': transaction['amount'],
                        'Debet': transaction['debet'],
                        'Credit': transaction['credit'],
                        'ReferenceNumber': transaction['ref'],
                        'Ref1': transaction.get('ref1'),
                        'Ref2': transaction.get('ref2'),
                        'Ref3': transaction.get('ref3'),
                        'Ref4': transaction.get('ref4'),
                        'Administration': 'GoodwinSolutions2024'  # Default administration
                    }
                    
                    # Insert transaction
                    success = db_manager.insert_transaction(db_transaction)
                    if success:
                        inserted_count += 1
                
                # Update result with database insertion information
                result['transactions_inserted'] = inserted_count
                result['message'] += f' {inserted_count} transaction(s) inserted into database.'
                
            except Exception as db_error:
                print(f"Database insertion error: {db_error}")
                result['success'] = False
                result['message'] = f"Decision processed but database insertion failed: {str(db_error)}"
        
        return jsonify({
            'success': result['success'],
            'actionTaken': result['action_taken'],
            'message': result['message'],
            'cleanupPerformed': result.get('cleanup_performed', False),
            'transactionsProcessed': len(result.get('transactions', [])),
            'transactionsInserted': result.get('transactions_inserted', 0),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Duplicate decision handling error: {e}", flush=True)
        return jsonify({
            'success': False,
            'error': f'Error handling duplicate decision: {str(e)}',
            'timestamp': datetime.now().isoformat()
        }), 500
