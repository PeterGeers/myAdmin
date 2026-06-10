"""
Decision handling for duplicate transaction detection in the PDF processing pipeline.

Handles user decisions (continue/cancel) when duplicate transactions are detected,
including validation, audit logging, file cleanup, and error management.
"""
from datetime import datetime
from typing import Dict, List, Optional


def handle_duplicate_decision(
    decision: str,
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict:
    """
    Handle user decision regarding duplicate transactions with comprehensive error handling.
    
    Processes the user's decision to either continue with the duplicate
    import or cancel it, implementing robust error handling and recovery mechanisms.
    
    Args:
        decision: User decision ('continue' or 'cancel')
        duplicate_info: Information about the duplicate transaction(s)
        transactions: List of formatted transaction dictionaries
        file_data: File data containing URL and metadata
        user_id: Optional user identifier for audit purposes
        session_id: Optional session identifier for tracking
    
    Returns:
        Dictionary containing the result of the decision processing with error details
    
    Requirements: 3.1, 3.3, 4.1, 4.5, 6.1, 6.2, 6.3
    """
    # Input validation with detailed error messages
    validation_result = _validate_duplicate_decision_inputs(
        decision, duplicate_info, transactions, file_data
    )
    if not validation_result['valid']:
        return validation_result['error_response']

    # Initialize error tracking
    errors = []
    warnings = []

    try:
        # Component initialization with error handling
        components = _initialize_duplicate_components()
        if not components['success']:
            return _create_error_response(
                'component_initialization_failed',
                components['error'],
                errors=['Failed to initialize required components'],
                user_message='System components unavailable. Please try again later.'
            )

        db = components['db']
        duplicate_checker = components['duplicate_checker']
        file_cleanup_manager = components['file_cleanup_manager']

        # Audit logging with error handling
        audit_result = _log_duplicate_decision_with_retry(
            duplicate_checker, decision, duplicate_info, user_id, session_id
        )
        if not audit_result['success']:
            warnings.append(f"Audit logging failed: {audit_result['error']}")

        # Process decision with comprehensive error handling
        if decision == 'continue':
            return _handle_continue_decision_enhanced(
                duplicate_info, transactions, file_data,
                audit_result['success'], errors, warnings
            )
        elif decision == 'cancel':
            return _handle_cancel_decision_enhanced(
                duplicate_info, transactions, file_data, file_cleanup_manager,
                audit_result['success'], errors, warnings
            )
        else:
            return _create_error_response(
                'invalid_decision',
                f'Invalid decision: {decision}',
                errors=[f'Decision must be "continue" or "cancel", got: {decision}'],
                user_message='Invalid action selected. Please choose Continue or Cancel.'
            )

    except ImportError as e:
        error_msg = f"Required modules not available: {str(e)}"
        return _create_error_response(
            'import_error', error_msg,
            errors=[error_msg],
            user_message='System components not available. Please contact support.'
        )
    except Exception as e:
        error_msg = f"Unexpected error in duplicate decision handling: {str(e)}"
        print(error_msg)
        return _create_error_response(
            'unexpected_error', error_msg,
            errors=[error_msg],
            user_message='An unexpected error occurred. Please try again or contact support.'
        )


def handle_continue_decision(
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    log_success: bool
) -> Dict:
    """
    Handle the "Continue" decision for duplicate imports.
    
    When user chooses to continue, process the transaction normally while
    maintaining all existing transaction formatting and database insertion logic.
    
    Args:
        duplicate_info: Information about the duplicate transaction(s)
        transactions: List of formatted transaction dictionaries
        file_data: File data containing URL and metadata
        log_success: Whether audit logging was successful
    
    Returns:
        Dictionary containing the result of continue processing
    
    Requirements: 3.1, 3.3
    """
    try:
        # Remove duplicate_info from transactions to prevent it from being stored
        clean_transactions = []
        for transaction in transactions:
            clean_transaction = {k: v for k, v in transaction.items() if k != 'duplicate_info'}
            clean_transactions.append(clean_transaction)

        message_parts = [
            f"Duplicate import approved. Processing {len(clean_transactions)} transaction(s)."
        ]

        if not log_success:
            message_parts.append("Note: Audit logging may have failed.")

        return {
            'success': True,
            'action_taken': 'continue',
            'transactions': clean_transactions,
            'cleanup_performed': False,
            'message': ' '.join(message_parts)
        }

    except Exception as e:
        print(f"Error in continue decision handling: {e}")
        return {
            'success': False,
            'action_taken': 'continue_error',
            'transactions': [],
            'cleanup_performed': False,
            'message': f'Error processing continue decision: {str(e)}'
        }


def handle_cancel_decision(
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    file_cleanup_manager,
    log_success: bool
) -> Dict:
    """
    Handle the "Cancel" decision for duplicate imports.
    
    When user chooses to cancel, perform appropriate file cleanup based on
    URL comparison and return user to pre-import state.
    
    Args:
        duplicate_info: Information about the duplicate transaction(s)
        transactions: List of formatted transaction dictionaries
        file_data: File data containing URL and metadata
        file_cleanup_manager: FileCleanupManager instance for cleanup operations
        log_success: Whether audit logging was successful
    
    Returns:
        Dictionary containing the result of cancel processing
    
    Requirements: 4.1, 4.5
    """
    try:
        cleanup_performed = False
        cleanup_details = []

        # Get URLs for comparison
        new_file_url = file_data.get('url', '')
        new_file_id = file_data.get('name', '')

        # Check existing transactions for file URLs
        existing_transactions = duplicate_info.get('existing_transactions', [])

        if existing_transactions:
            existing_file_url = existing_transactions[0].get('ref3', '')

            # Determine if file cleanup is needed based on URL comparison
            should_cleanup = file_cleanup_manager.should_cleanup_file(
                new_file_url, existing_file_url
            )

            if should_cleanup:
                cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                    new_file_url, new_file_id
                )

                if cleanup_success:
                    cleanup_performed = True
                    cleanup_details.append("New file removed successfully.")
                else:
                    cleanup_details.append("File cleanup attempted but may have failed.")
            else:
                cleanup_details.append("File URLs match - no cleanup performed.")
        else:
            cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                new_file_url, new_file_id
            )

            if cleanup_success:
                cleanup_performed = True
                cleanup_details.append("New file removed successfully.")
            else:
                cleanup_details.append("File cleanup attempted but may have failed.")

        # Build result message
        message_parts = ["Duplicate import cancelled."]
        message_parts.extend(cleanup_details)

        if not log_success:
            message_parts.append("Note: Audit logging may have failed.")

        return {
            'success': True,
            'action_taken': 'cancel',
            'transactions': [],
            'cleanup_performed': cleanup_performed,
            'message': ' '.join(message_parts)
        }

    except Exception as e:
        print(f"Error in cancel decision handling: {e}")
        return {
            'success': False,
            'action_taken': 'cancel_error',
            'transactions': [],
            'cleanup_performed': False,
            'message': f'Error processing cancel decision: {str(e)}'
        }


def _validate_duplicate_decision_inputs(
    decision: str,
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict
) -> Dict:
    """
    Validate inputs for duplicate decision handling with comprehensive error messages.
    
    Args:
        decision: User decision to validate
        duplicate_info: Duplicate information to validate
        transactions: Transaction list to validate
        file_data: File data to validate
    
    Returns:
        Dictionary with validation result and error response if invalid
    """
    try:
        # Validate decision parameter
        if not decision or not isinstance(decision, str):
            return {
                'valid': False,
                'error_response': _create_error_response(
                    'invalid_decision_parameter',
                    'Decision parameter is required and must be a string',
                    errors=['Decision parameter missing or invalid type'],
                    user_message='Invalid action selected. Please choose Continue or Cancel.'
                )
            }

        decision = decision.strip().lower()
        if decision not in ['continue', 'cancel']:
            return {
                'valid': False,
                'error_response': _create_error_response(
                    'invalid_decision_value',
                    f'Invalid decision value: {decision}',
                    errors=[f'Decision must be "continue" or "cancel", got: {decision}'],
                    user_message='Invalid action selected. Please choose Continue or Cancel.'
                )
            }

        # Validate duplicate_info parameter
        if not duplicate_info or not isinstance(duplicate_info, dict):
            return {
                'valid': False,
                'error_response': _create_error_response(
                    'invalid_duplicate_info',
                    'Duplicate info parameter is required and must be a dictionary',
                    errors=['Duplicate info parameter missing or invalid type'],
                    user_message='Invalid duplicate information. Please refresh and try again.'
                )
            }

        # Validate transactions parameter
        if not transactions or not isinstance(transactions, list):
            return {
                'valid': False,
                'error_response': _create_error_response(
                    'invalid_transactions',
                    'Transactions parameter is required and must be a list',
                    errors=['Transactions parameter missing or invalid type'],
                    user_message='Invalid transaction data. Please refresh and try again.'
                )
            }

        # Validate file_data parameter
        if not file_data or not isinstance(file_data, dict):
            return {
                'valid': False,
                'error_response': _create_error_response(
                    'invalid_file_data',
                    'File data parameter is required and must be a dictionary',
                    errors=['File data parameter missing or invalid type'],
                    user_message='Invalid file information. Please refresh and try again.'
                )
            }

        # Validate required fields in file_data
        required_file_fields = ['url', 'name']
        missing_fields = [field for field in required_file_fields if field not in file_data]
        if missing_fields:
            return {
                'valid': False,
                'error_response': _create_error_response(
                    'missing_file_data_fields',
                    f'Missing required file data fields: {missing_fields}',
                    errors=[f'File data missing required fields: {missing_fields}'],
                    user_message='Incomplete file information. Please refresh and try again.'
                )
            }

        return {'valid': True}

    except Exception as e:
        return {
            'valid': False,
            'error_response': _create_error_response(
                'validation_error',
                f'Error during input validation: {str(e)}',
                errors=[f'Validation error: {str(e)}'],
                user_message='Error validating input. Please refresh and try again.'
            )
        }


def _initialize_duplicate_components() -> Dict:
    """
    Initialize duplicate detection components with comprehensive error handling.
    
    Returns:
        Dictionary containing initialized components or error information
    """
    try:
        # Initialize database manager with connection validation
        try:
            from database import DatabaseManager
            db = DatabaseManager()

            # Test database connection
            test_connection = db.get_connection()
            if test_connection:
                test_connection.close()
            else:
                raise Exception("Could not establish database connection")

        except ImportError as e:
            return {
                'success': False,
                'error': f'DatabaseManager not available: {str(e)}',
                'component': 'database_manager'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Database initialization failed: {str(e)}',
                'component': 'database_manager'
            }

        # Initialize duplicate checker
        try:
            from duplicate_checker import DuplicateChecker
            duplicate_checker = DuplicateChecker(db)
        except ImportError as e:
            return {
                'success': False,
                'error': f'DuplicateChecker not available: {str(e)}',
                'component': 'duplicate_checker'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'DuplicateChecker initialization failed: {str(e)}',
                'component': 'duplicate_checker'
            }

        # Initialize file cleanup manager
        try:
            from file_cleanup_manager import FileCleanupManager
            file_cleanup_manager = FileCleanupManager()
        except ImportError as e:
            return {
                'success': False,
                'error': f'FileCleanupManager not available: {str(e)}',
                'component': 'file_cleanup_manager'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'FileCleanupManager initialization failed: {str(e)}',
                'component': 'file_cleanup_manager'
            }

        return {
            'success': True,
            'db': db,
            'duplicate_checker': duplicate_checker,
            'file_cleanup_manager': file_cleanup_manager
        }

    except Exception as e:
        return {
            'success': False,
            'error': f'Unexpected error during component initialization: {str(e)}',
            'component': 'unknown'
        }


def _log_duplicate_decision_with_retry(
    duplicate_checker,
    decision: str,
    duplicate_info: Dict,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> Dict:
    """
    Log duplicate decision with retry logic and comprehensive error handling.
    
    Args:
        duplicate_checker: DuplicateChecker instance
        decision: User decision to log
        duplicate_info: Duplicate information
        user_id: Optional user identifier
        session_id: Optional session identifier
    
    Returns:
        Dictionary containing logging result and error information
    """
    max_retries = 3
    retry_delay = 1  # seconds

    for attempt in range(max_retries):
        try:
            # Extract new transaction data from duplicate_info
            new_transaction_data = duplicate_info.get('new_transaction', {})

            # Attempt to log the decision
            log_success = duplicate_checker.log_duplicate_decision(
                decision=decision,
                duplicate_info=duplicate_info,
                new_transaction_data=new_transaction_data,
                user_id=user_id,
                session_id=session_id
            )

            if log_success:
                return {
                    'success': True,
                    'attempts': attempt + 1,
                    'message': f'Decision logged successfully on attempt {attempt + 1}'
                }
            else:
                if attempt < max_retries - 1:
                    print(f"Audit logging attempt {attempt + 1} failed, retrying...")
                    import time
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    return {
                        'success': False,
                        'attempts': max_retries,
                        'error': 'All audit logging attempts failed',
                        'error_type': 'audit_logging_failed'
                    }

        except Exception as e:
            error_msg = f"Audit logging attempt {attempt + 1} error: {str(e)}"
            print(error_msg)

            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                return {
                    'success': False,
                    'attempts': max_retries,
                    'error': error_msg,
                    'error_type': 'audit_logging_exception'
                }

    return {
        'success': False,
        'attempts': max_retries,
        'error': 'Maximum retry attempts exceeded',
        'error_type': 'max_retries_exceeded'
    }


def _handle_continue_decision_enhanced(
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    audit_success: bool,
    errors: List[str],
    warnings: List[str]
) -> Dict:
    """
    Enhanced continue decision handling with comprehensive error management.
    
    Args:
        duplicate_info: Information about the duplicate transaction(s)
        transactions: List of formatted transaction dictionaries
        file_data: File data containing URL and metadata
        audit_success: Whether audit logging was successful
        errors: List to collect error messages
        warnings: List to collect warning messages
    
    Returns:
        Dictionary containing the result of continue processing with error details
    """
    try:
        # Validate transaction data before processing
        validation_errors = _validate_transaction_data(transactions)
        if validation_errors:
            errors.extend(validation_errors)
            return _create_error_response(
                'transaction_validation_failed',
                'Transaction data validation failed',
                errors=errors,
                warnings=warnings,
                user_message='Invalid transaction data. Please refresh and try again.'
            )

        # Remove duplicate_info from transactions to prevent it from being stored
        clean_transactions = []
        for transaction in transactions:
            try:
                clean_transaction = {k: v for k, v in transaction.items() if k != 'duplicate_info'}
                clean_transactions.append(clean_transaction)
            except Exception as e:
                errors.append(f"Error cleaning transaction data: {str(e)}")

        if not clean_transactions and transactions:
            errors.append("Failed to clean transaction data")
            return _create_error_response(
                'transaction_cleaning_failed',
                'Failed to prepare transaction data',
                errors=errors,
                warnings=warnings,
                user_message='Error preparing transaction data. Please try again.'
            )

        # Build success message with warnings if applicable
        message_parts = [
            f"Duplicate import approved. Processing {len(clean_transactions)} transaction(s)."
        ]

        if not audit_success:
            warnings.append("Audit logging may have failed")
            message_parts.append("Note: Audit logging may have failed.")

        if warnings:
            message_parts.append(f"Warnings: {'; '.join(warnings)}")

        return {
            'success': True,
            'action_taken': 'continue',
            'transactions': clean_transactions,
            'cleanup_performed': False,
            'message': ' '.join(message_parts),
            'errors': errors,
            'warnings': warnings,
            'audit_logged': audit_success
        }

    except Exception as e:
        error_msg = f"Error in enhanced continue decision handling: {str(e)}"
        errors.append(error_msg)
        print(error_msg)

        return _create_error_response(
            'continue_processing_error',
            error_msg,
            errors=errors,
            warnings=warnings,
            user_message='Error processing continue decision. Please try again.'
        )


def _handle_cancel_decision_enhanced(
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    file_cleanup_manager,
    audit_success: bool,
    errors: List[str],
    warnings: List[str]
) -> Dict:
    """
    Enhanced cancel decision handling with comprehensive error management.
    
    Args:
        duplicate_info: Information about the duplicate transaction(s)
        transactions: List of formatted transaction dictionaries
        file_data: File data containing URL and metadata
        file_cleanup_manager: FileCleanupManager instance for cleanup operations
        audit_success: Whether audit logging was successful
        errors: List to collect error messages
        warnings: List to collect warning messages
    
    Returns:
        Dictionary containing the result of cancel processing with error details
    """
    try:
        cleanup_performed = False
        cleanup_details = []
        cleanup_errors = []

        # Get URLs for comparison with error handling
        try:
            new_file_url = file_data.get('url', '')
            new_file_id = file_data.get('name', '')

            if not new_file_url:
                warnings.append("No file URL found for cleanup")
                cleanup_details.append("No file URL available for cleanup.")

        except Exception as e:
            error_msg = f"Error extracting file information: {str(e)}"
            errors.append(error_msg)
            cleanup_errors.append(error_msg)

        # Check existing transactions for file URLs with error handling
        try:
            existing_transactions = duplicate_info.get('existing_transactions', [])

            if existing_transactions and new_file_url:
                existing_file_url = existing_transactions[0].get('ref3', '')

                # Determine if file cleanup is needed based on URL comparison
                try:
                    should_cleanup = file_cleanup_manager.should_cleanup_file(
                        new_file_url, existing_file_url
                    )

                    if should_cleanup:
                        try:
                            cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                                new_file_url, new_file_id
                            )

                            if cleanup_success:
                                cleanup_performed = True
                                cleanup_details.append("New file removed successfully.")
                            else:
                                warnings.append("File cleanup may have failed")
                                cleanup_details.append("File cleanup attempted but may have failed.")

                        except Exception as cleanup_error:
                            error_msg = f"File cleanup error: {str(cleanup_error)}"
                            cleanup_errors.append(error_msg)
                            warnings.append("File cleanup failed")
                            cleanup_details.append("File cleanup failed - manual cleanup may be required.")
                    else:
                        cleanup_details.append("File URLs match - no cleanup performed.")

                except Exception as comparison_error:
                    error_msg = f"URL comparison error: {str(comparison_error)}"
                    cleanup_errors.append(error_msg)
                    warnings.append("Could not compare file URLs")
                    cleanup_details.append("Could not determine if cleanup is needed.")

            elif new_file_url:
                try:
                    cleanup_success = file_cleanup_manager.cleanup_uploaded_file(
                        new_file_url, new_file_id
                    )

                    if cleanup_success:
                        cleanup_performed = True
                        cleanup_details.append("New file removed successfully.")
                    else:
                        warnings.append("File cleanup may have failed")
                        cleanup_details.append("File cleanup attempted but may have failed.")

                except Exception as cleanup_error:
                    error_msg = f"File cleanup error: {str(cleanup_error)}"
                    cleanup_errors.append(error_msg)
                    warnings.append("File cleanup failed")
                    cleanup_details.append("File cleanup failed - manual cleanup may be required.")

        except Exception as e:
            error_msg = f"Error processing existing transactions: {str(e)}"
            errors.append(error_msg)
            cleanup_errors.append(error_msg)

        # Build result message with all details
        message_parts = ["Duplicate import cancelled."]
        message_parts.extend(cleanup_details)

        if not audit_success:
            warnings.append("Audit logging may have failed")
            message_parts.append("Note: Audit logging may have failed.")

        if cleanup_errors:
            errors.extend(cleanup_errors)
            message_parts.append("Some cleanup operations encountered errors.")

        if warnings:
            message_parts.append(f"Warnings: {'; '.join(warnings)}")

        return {
            'success': True,
            'action_taken': 'cancel',
            'transactions': [],
            'cleanup_performed': cleanup_performed,
            'message': ' '.join(message_parts),
            'errors': errors,
            'warnings': warnings,
            'audit_logged': audit_success,
            'cleanup_details': cleanup_details
        }

    except Exception as e:
        error_msg = f"Error in enhanced cancel decision handling: {str(e)}"
        errors.append(error_msg)
        print(error_msg)

        return _create_error_response(
            'cancel_processing_error',
            error_msg,
            errors=errors,
            warnings=warnings,
            user_message='Error processing cancel decision. Please try again.'
        )


def _validate_transaction_data(transactions: List[Dict]) -> List[str]:
    """
    Validate transaction data for required fields and proper formatting.
    
    Args:
        transactions: List of transaction dictionaries to validate
    
    Returns:
        List of validation error messages (empty if valid)
    """
    validation_errors = []

    if not transactions:
        validation_errors.append("No transactions provided for validation")
        return validation_errors

    required_fields = ['date', 'description', 'amount', 'debet', 'credit']

    for i, transaction in enumerate(transactions):
        if not isinstance(transaction, dict):
            validation_errors.append(f"Transaction {i+1} is not a dictionary")
            continue

        # Check required fields
        missing_fields = [field for field in required_fields if field not in transaction]
        if missing_fields:
            validation_errors.append(f"Transaction {i+1} missing fields: {missing_fields}")

        # Validate field types and values
        try:
            if 'amount' in transaction:
                amount = float(transaction['amount'])
                if amount <= 0:
                    validation_errors.append(f"Transaction {i+1} has invalid amount: {amount}")
        except (ValueError, TypeError):
            validation_errors.append(f"Transaction {i+1} has invalid amount format")

        # Validate date format
        if 'date' in transaction:
            date_str = transaction['date']
            if not date_str or not isinstance(date_str, str):
                validation_errors.append(f"Transaction {i+1} has invalid date format")

    return validation_errors


def _create_error_response(
    error_code: str,
    error_message: str,
    errors: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    user_message: Optional[str] = None
) -> Dict:
    """
    Create standardized error response with comprehensive error information.
    
    Args:
        error_code: Unique error code for categorization
        error_message: Detailed error message for logging
        errors: List of specific error messages
        warnings: List of warning messages
        user_message: User-friendly error message
    
    Returns:
        Standardized error response dictionary
    """
    return {
        'success': False,
        'error_code': error_code,
        'error_message': error_message,
        'errors': errors or [],
        'warnings': warnings or [],
        'user_message': user_message or 'An error occurred. Please try again.',
        'timestamp': datetime.now().isoformat(),
        'action_taken': 'error',
        'transactions': [],
        'cleanup_performed': False
    }
