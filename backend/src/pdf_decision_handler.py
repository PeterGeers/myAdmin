"""
Decision handling for duplicate transaction detection in the PDF processing pipeline.

Handles user decisions (continue/cancel) when duplicate transactions are detected,
including validation, audit logging, file cleanup, and error management.

Internal helpers (validation, retry logic, enhanced processing) are in pdf_decision_helpers.py.
"""

from typing import Dict, List, Optional

from pdf_decision_helpers import (
    validate_duplicate_decision_inputs,
    initialize_duplicate_components,
    log_duplicate_decision_with_retry,
    handle_continue_decision_enhanced,
    handle_cancel_decision_enhanced,
    create_error_response,
)


def handle_duplicate_decision(
    decision: str,
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
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
    validation_result = validate_duplicate_decision_inputs(
        decision, duplicate_info, transactions, file_data
    )
    if not validation_result["valid"]:
        return validation_result["error_response"]

    # Initialize error tracking
    errors = []
    warnings = []

    try:
        # Component initialization with error handling
        components = initialize_duplicate_components()
        if not components["success"]:
            return create_error_response(
                "component_initialization_failed",
                components["error"],
                errors=["Failed to initialize required components"],
                user_message="System components unavailable. Please try again later.",
            )

        _db = components["db"]
        duplicate_checker = components["duplicate_checker"]
        file_cleanup_manager = components["file_cleanup_manager"]

        # Audit logging with error handling
        audit_result = log_duplicate_decision_with_retry(
            duplicate_checker, decision, duplicate_info, user_id, session_id
        )
        if not audit_result["success"]:
            warnings.append(f"Audit logging failed: {audit_result['error']}")

        # Process decision with comprehensive error handling
        if decision == "continue":
            return handle_continue_decision_enhanced(
                duplicate_info,
                transactions,
                file_data,
                audit_result["success"],
                errors,
                warnings,
            )
        elif decision == "cancel":
            return handle_cancel_decision_enhanced(
                duplicate_info,
                transactions,
                file_data,
                file_cleanup_manager,
                audit_result["success"],
                errors,
                warnings,
            )
        else:
            return create_error_response(
                "invalid_decision",
                f"Invalid decision: {decision}",
                errors=[f'Decision must be "continue" or "cancel", got: {decision}'],
                user_message="Invalid action selected. Please choose Continue or Cancel.",
            )

    except ImportError as e:
        error_msg = f"Required modules not available: {str(e)}"
        return create_error_response(
            "import_error",
            error_msg,
            errors=[error_msg],
            user_message="System components not available. Please contact support.",
        )
    except Exception as e:
        error_msg = f"Unexpected error in duplicate decision handling: {str(e)}"
        print(error_msg)
        return create_error_response(
            "unexpected_error",
            error_msg,
            errors=[error_msg],
            user_message="An unexpected error occurred. Please try again or contact support.",
        )


def handle_continue_decision(
    duplicate_info: Dict, transactions: List[Dict], file_data: Dict, log_success: bool
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
        clean_transactions = []
        for transaction in transactions:
            clean_transaction = {
                k: v for k, v in transaction.items() if k != "duplicate_info"
            }
            clean_transactions.append(clean_transaction)

        message_parts = [
            f"Duplicate import approved. Processing {len(clean_transactions)} transaction(s)."
        ]

        if not log_success:
            message_parts.append("Note: Audit logging may have failed.")

        return {
            "success": True,
            "action_taken": "continue",
            "transactions": clean_transactions,
            "cleanup_performed": False,
            "message": " ".join(message_parts),
        }

    except Exception as e:
        print(f"Error in continue decision handling: {e}")
        return {
            "success": False,
            "action_taken": "continue_error",
            "transactions": [],
            "cleanup_performed": False,
            "message": f"Error processing continue decision: {str(e)}",
        }


def handle_cancel_decision(
    duplicate_info: Dict,
    transactions: List[Dict],
    file_data: Dict,
    file_cleanup_manager,
    log_success: bool,
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

        new_file_url = file_data.get("url", "")
        new_file_id = file_data.get("name", "")

        existing_transactions = duplicate_info.get("existing_transactions", [])

        if existing_transactions:
            existing_file_url = existing_transactions[0].get("ref3", "")

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
                    cleanup_details.append(
                        "File cleanup attempted but may have failed."
                    )
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

        message_parts = ["Duplicate import cancelled."]
        message_parts.extend(cleanup_details)

        if not log_success:
            message_parts.append("Note: Audit logging may have failed.")

        return {
            "success": True,
            "action_taken": "cancel",
            "transactions": [],
            "cleanup_performed": cleanup_performed,
            "message": " ".join(message_parts),
        }

    except Exception as e:
        print(f"Error in cancel decision handling: {e}")
        return {
            "success": False,
            "action_taken": "cancel_error",
            "transactions": [],
            "cleanup_performed": False,
            "message": f"Error processing cancel decision: {str(e)}",
        }
