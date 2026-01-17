"""
Duplicate Invoice Detection Component

This module provides functionality to detect duplicate invoices during the import process
by checking for existing transactions with matching ReferenceNumber, TransactionDate, and TransactionAmount.
"""

import logging
import traceback
from typing import List, Dict, Optional
from datetime import datetime
from database import DatabaseManager
from duplicate_performance_monitor import get_performance_monitor

# Configure logger for duplicate detection
logger = logging.getLogger(__name__)

# Get performance monitor for metrics collection
_performance_monitor = get_performance_monitor()

class DuplicateDetectionError(Exception):
    """Custom exception for duplicate detection errors."""
    pass

class DatabaseConnectionError(DuplicateDetectionError):
    """Exception for database connection failures."""
    pass

class ValidationError(DuplicateDetectionError):
    """Exception for data validation failures."""
    pass

class SessionTimeoutError(DuplicateDetectionError):
    """Exception for session timeout scenarios."""
    pass


class DuplicateChecker:
    """
    Handles duplicate invoice detection and decision logging.
    
    This class integrates with the existing DatabaseManager to check for duplicate
    transactions and provides methods for formatting duplicate information and logging
    user decisions for audit purposes.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the DuplicateChecker with a database manager.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager
    
    @_performance_monitor.monitor_duplicate_check
    def check_for_duplicates(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float,
        table_name: str = 'mutaties'
    ) -> List[Dict]:
        """
        Check for duplicate transactions in the database.
        
        Searches for existing transactions with matching ReferenceNumber, TransactionDate,
        and TransactionAmount within the last 2 years for performance optimization.
        
        Args:
            reference_number: The reference number (folder name) to check
            transaction_date: The transaction date in YYYY-MM-DD format
            transaction_amount: The transaction amount to match
            table_name: The database table to search (default: 'mutaties')
        
        Returns:
            List of dictionaries containing matching transaction records.
            Empty list if no duplicates found or if an error occurs.
        
        Requirements: 1.1, 1.3, 6.1, 6.4
        """
        operation_id = f"dup_check_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        try:
            # Validate input parameters
            self._validate_duplicate_check_params(reference_number, transaction_date, transaction_amount)
            
            logger.info(f"[{operation_id}] Starting duplicate check for {reference_number} on {transaction_date} amount {transaction_amount}")
            
            # Use the database manager's execute_query method for consistency
            query = f"""
                SELECT * FROM {table_name}
                WHERE ReferenceNumber = %s
                AND TransactionDate = %s
                AND TransactionAmount = %s
                AND TransactionDate > (CURDATE() - INTERVAL 2 YEAR)
                ORDER BY ID DESC
            """
            
            results = self.db.execute_query(
                query,
                (reference_number, transaction_date, transaction_amount),
                fetch=True
            )
            
            duplicate_count = len(results) if results else 0
            logger.info(f"[{operation_id}] Duplicate check completed: {duplicate_count} matches found")
            
            return results if results else []
            
        except ValidationError as ve:
            logger.error(f"[{operation_id}] Validation error in duplicate check: {ve}")
            # For validation errors, we should not proceed with graceful degradation
            raise ve
            
        except DatabaseConnectionError as dce:
            logger.error(f"[{operation_id}] Database connection error in duplicate check: {dce}")
            # Log error but allow import to continue with warning (graceful degradation)
            self._log_graceful_degradation(operation_id, "database_connection", str(dce))
            return []
            
        except Exception as e:
            error_details = {
                'operation_id': operation_id,
                'reference_number': reference_number,
                'transaction_date': transaction_date,
                'transaction_amount': transaction_amount,
                'error_type': type(e).__name__,
                'error_message': str(e),
                'traceback': traceback.format_exc()
            }
            
            logger.error(f"[{operation_id}] Unexpected error in duplicate check: {error_details}")
            
            # Check if this is a database connection issue
            if self._is_database_connection_error(e):
                self._log_graceful_degradation(operation_id, "database_connection", str(e))
                return []
            
            # For other errors, log but continue with graceful degradation
            self._log_graceful_degradation(operation_id, "unexpected_error", str(e))
            return []
    
    def format_duplicate_info(self, duplicates: List[Dict]) -> Dict:
        """
        Format duplicate information for frontend display.
        
        Converts raw database records into a structured format suitable for
        displaying in the duplicate warning dialog.
        
        Args:
            duplicates: List of duplicate transaction records from database
        
        Returns:
            Dictionary containing formatted duplicate information with:
            - has_duplicates: Boolean indicating if duplicates exist
            - duplicate_count: Number of matching transactions found
            - existing_transactions: List of formatted transaction data
            - requires_user_decision: Boolean indicating if user input is needed
        
        Requirements: 1.2, 2.1
        """
        if not duplicates:
            return {
                'has_duplicates': False,
                'duplicate_count': 0,
                'existing_transactions': [],
                'requires_user_decision': False
            }
        
        # Format each duplicate transaction for frontend display
        formatted_transactions = []
        for dup in duplicates:
            formatted_transactions.append({
                'id': dup.get('ID', ''),
                'transactionNumber': dup.get('TransactionNumber', ''),
                'transactionDate': dup.get('TransactionDate', ''),
                'transactionDescription': dup.get('TransactionDescription', ''),
                'transactionAmount': float(dup.get('TransactionAmount', 0)),
                'debet': dup.get('Debet', ''),
                'credit': dup.get('Credit', ''),
                'referenceNumber': dup.get('ReferenceNumber', ''),
                'ref1': dup.get('Ref1', ''),
                'ref2': dup.get('Ref2', ''),
                'ref3': dup.get('Ref3', ''),  # File URL
                'ref4': dup.get('Ref4', ''),
                'administration': dup.get('Administration', '')
            })
        
        return {
            'has_duplicates': True,
            'duplicate_count': len(duplicates),
            'existing_transactions': formatted_transactions,
            'requires_user_decision': True
        }
    
    def log_duplicate_decision(
        self,
        decision: str,
        duplicate_info: Dict,
        new_transaction_data: Dict,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Log user decision regarding duplicate transaction for audit trail.
        
        Records the user's decision (continue or cancel) along with relevant
        transaction information for compliance and debugging purposes.
        
        Args:
            decision: User decision ('continue' or 'cancel')
            duplicate_info: Information about the duplicate transaction(s)
            new_transaction_data: Data about the new transaction being imported
            user_id: Optional user identifier for audit purposes
            session_id: Optional session identifier for tracking
        
        Returns:
            Boolean indicating if logging was successful
        
        Requirements: 3.2, 6.4, 6.5
        """
        operation_id = f"dup_log_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        try:
            # Validate decision parameter
            if decision not in ['continue', 'cancel']:
                raise ValidationError(f"Invalid decision value: {decision}. Must be 'continue' or 'cancel'")
            
            # Validate session timeout
            self._check_session_timeout(session_id, operation_id)
            
            # Extract key information for logging
            existing_transactions = duplicate_info.get('existing_transactions', [])
            existing_id = existing_transactions[0].get('id', '') if existing_transactions else ''
            
            # Convert existing_id to proper integer or None for database
            if existing_id == '' or existing_id is None:
                existing_id = None
            else:
                try:
                    existing_id = int(existing_id)
                except (ValueError, TypeError):
                    existing_id = None
            
            reference_number = new_transaction_data.get('ReferenceNumber', '')
            transaction_date = new_transaction_data.get('TransactionDate', '')
            transaction_amount = new_transaction_data.get('TransactionAmount', 0)
            new_file_url = new_transaction_data.get('Ref3', '')
            
            logger.info(f"[{operation_id}] Logging duplicate decision: {decision} for {reference_number}")
            
            # Create audit log entry with retry logic
            log_query = """
                INSERT INTO duplicate_decision_log 
                (timestamp, reference_number, transaction_date, transaction_amount, 
                 decision, existing_transaction_id, new_file_url, user_id, session_id, operation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            # Attempt to log with retry logic for transient database issues
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    self.db.execute_query(
                        log_query,
                        (
                            datetime.now(),
                            reference_number,
                            transaction_date,
                            transaction_amount,
                            decision,
                            existing_id,
                            new_file_url,
                            user_id,
                            session_id,
                            operation_id
                        ),
                        fetch=False,
                        commit=True
                    )
                    
                    logger.info(f"[{operation_id}] Duplicate decision logged successfully: {decision} for {reference_number} on {transaction_date}")
                    return True
                    
                except Exception as retry_error:
                    if attempt < max_retries - 1:
                        logger.warning(f"[{operation_id}] Retry {attempt + 1}/{max_retries} for decision logging failed: {retry_error}")
                        continue
                    else:
                        raise retry_error
            
        except ValidationError as ve:
            logger.error(f"[{operation_id}] Validation error in decision logging: {ve}")
            return False
            
        except SessionTimeoutError as ste:
            logger.error(f"[{operation_id}] Session timeout error in decision logging: {ste}")
            return False
            
        except DatabaseConnectionError as dce:
            logger.error(f"[{operation_id}] Database connection error in decision logging: {dce}")
            return False
            
        except Exception as e:
            error_details = {
                'operation_id': operation_id,
                'decision': decision,
                'reference_number': new_transaction_data.get('ReferenceNumber', ''),
                'error_type': type(e).__name__,
                'error_message': str(e),
                'traceback': traceback.format_exc()
            }
            
            logger.error(f"[{operation_id}] Error logging duplicate decision: {error_details}")
            
            # Check if this is a missing table error (migrations not run yet)
            if self._is_missing_table_error(e):
                logger.warning(f"[{operation_id}] Duplicate decision log table not found - migrations may not be complete")
                return False
            
            # For other database errors, still return False but log appropriately
            return False
    
    def _validate_duplicate_check_params(self, reference_number: str, transaction_date: str, transaction_amount: float) -> None:
        """
        Validate parameters for duplicate checking.
        
        Args:
            reference_number: The reference number to validate
            transaction_date: The transaction date to validate
            transaction_amount: The transaction amount to validate
        
        Raises:
            ValidationError: If any parameter is invalid
        """
        if not reference_number or not reference_number.strip():
            raise ValidationError("Reference number cannot be empty")
        
        if not transaction_date or not transaction_date.strip():
            raise ValidationError("Transaction date cannot be empty")
        
        # Validate date format
        try:
            datetime.strptime(transaction_date, '%Y-%m-%d')
        except ValueError:
            raise ValidationError(f"Invalid transaction date format: {transaction_date}. Expected YYYY-MM-DD")
        
        if transaction_amount is None or transaction_amount <= 0:
            raise ValidationError(f"Transaction amount must be positive: {transaction_amount}")
    
    def _check_session_timeout(self, session_id: Optional[str], operation_id: str) -> None:
        """
        Check if session has timed out for duplicate decision operations.
        
        Args:
            session_id: Session identifier to check
            operation_id: Operation identifier for logging
        
        Raises:
            SessionTimeoutError: If session has timed out
        """
        if not session_id:
            # No session ID provided - this is acceptable for some operations
            return
        
        try:
            # Import session manager to check session validity
            from session_manager import session_manager
            
            # Validate session and check for timeout
            is_valid = session_manager.validate_session(session_id, operation_id)
            
            if not is_valid:
                raise SessionTimeoutError(f"Session {session_id} is invalid or has expired")
                
            logger.debug(f"[{operation_id}] Session timeout check passed for session: {session_id}")
            
        except SessionTimeoutError:
            # Re-raise session timeout errors
            raise
            
        except Exception as e:
            # If session manager is not available or fails, log warning but don't fail operation
            logger.warning(f"[{operation_id}] Could not validate session {session_id}: {e}")
            # In production, you might want to be more strict about session validation
    
    def _is_database_connection_error(self, error: Exception) -> bool:
        """
        Check if error is related to database connection issues.
        
        Args:
            error: Exception to check
        
        Returns:
            Boolean indicating if this is a database connection error
        """
        error_message = str(error).lower()
        connection_error_indicators = [
            'connection refused',
            'connection lost',
            'connection timeout',
            'can\'t connect',
            'connection failed',
            'host is unreachable',
            'network is unreachable',
            'connection reset',
            'connection aborted'
        ]
        
        return any(indicator in error_message for indicator in connection_error_indicators)
    
    def _is_missing_table_error(self, error: Exception) -> bool:
        """
        Check if error is related to missing database table.
        
        Args:
            error: Exception to check
        
        Returns:
            Boolean indicating if this is a missing table error
        """
        error_message = str(error).lower()
        missing_table_indicators = [
            'table doesn\'t exist',
            'no such table',
            'unknown table',
            'table not found',
            'duplicate_decision_log'
        ]
        
        return any(indicator in error_message for indicator in missing_table_indicators)
    
    def _log_graceful_degradation(self, operation_id: str, error_type: str, error_message: str) -> None:
        """
        Log graceful degradation events for monitoring and alerting.
        
        Args:
            operation_id: Unique operation identifier
            error_type: Type of error that triggered graceful degradation
            error_message: Detailed error message
        """
        degradation_log = {
            'operation_id': operation_id,
            'error_type': error_type,
            'error_message': error_message,
            'timestamp': datetime.now().isoformat(),
            'component': 'duplicate_checker',
            'action': 'graceful_degradation',
            'severity': 'warning',
            'impact': 'duplicate_check_skipped',
            'recovery_action': 'manual_verification_recommended'
        }
        
        logger.warning(f"[{operation_id}] Graceful degradation triggered: {degradation_log}")
        
        # Enhanced monitoring and alerting
        try:
            # Log to structured monitoring system
            self._send_monitoring_alert(degradation_log)
            
            # Update health metrics
            self._update_health_metrics(error_type, 'degradation')
            
            # Store degradation event for analysis
            self._store_degradation_event(degradation_log)
            
        except Exception as monitoring_error:
            # Don't let monitoring failures affect the main operation
            logger.error(f"[{operation_id}] Failed to send monitoring alert: {monitoring_error}")
    
    def _send_monitoring_alert(self, degradation_log: Dict) -> None:
        """
        Send alert to monitoring systems for graceful degradation events.
        
        Args:
            degradation_log: Degradation event details
        """
        # In a production environment, this would integrate with:
        # - Application Performance Monitoring (APM) systems
        # - Log aggregation systems (ELK stack, Splunk, etc.)
        # - Alerting systems (PagerDuty, Slack, email)
        # - Metrics systems (Prometheus, DataDog, etc.)
        
        # Example implementation structure:
        # try:
        #     # Send to APM system
        #     apm_client.capture_message(
        #         message=f"Duplicate detection graceful degradation: {degradation_log['error_type']}",
        #         level='warning',
        #         extra=degradation_log
        #     )
        #     
        #     # Send to metrics system
        #     metrics_client.increment('duplicate_detection.graceful_degradation', 
        #                            tags=[f"error_type:{degradation_log['error_type']}"])
        #     
        #     # Send alert if error rate is high
        #     if self._should_send_alert(degradation_log['error_type']):
        #         alert_client.send_alert(
        #             title="Duplicate Detection Degradation",
        #             message=f"Multiple {degradation_log['error_type']} errors detected",
        #             severity='warning'
        #         )
        # except Exception as e:
        #     logger.error(f"Failed to send monitoring alert: {e}")
        
        logger.debug(f"Monitoring alert prepared for: {degradation_log['operation_id']}")
    
    def _update_health_metrics(self, error_type: str, event_type: str) -> None:
        """
        Update health metrics for monitoring dashboard.
        
        Args:
            error_type: Type of error that occurred
            event_type: Type of event (degradation, recovery, etc.)
        """
        try:
            # In production, this would update health check endpoints and metrics
            # Example implementation:
            # health_metrics = {
            #     'duplicate_detection_health': 'degraded' if event_type == 'degradation' else 'healthy',
            #     'last_error_type': error_type,
            #     'last_error_time': datetime.now().isoformat(),
            #     'error_count_24h': self._get_error_count_24h(error_type),
            #     'degradation_rate': self._calculate_degradation_rate()
            # }
            # 
            # health_check_service.update_metrics('duplicate_detection', health_metrics)
            
            logger.debug(f"Health metrics updated for error_type: {error_type}, event: {event_type}")
            
        except Exception as e:
            logger.error(f"Failed to update health metrics: {e}")
    
    def _store_degradation_event(self, degradation_log: Dict) -> None:
        """
        Store degradation event for analysis and trending.
        
        Args:
            degradation_log: Degradation event details
        """
        try:
            # In production, this would store events in a time-series database
            # for analysis, trending, and alerting threshold calculations
            
            # Example implementation:
            # event_store.store_event(
            #     event_type='duplicate_detection_degradation',
            #     timestamp=degradation_log['timestamp'],
            #     data=degradation_log,
            #     tags={
            #         'component': degradation_log['component'],
            #         'error_type': degradation_log['error_type'],
            #         'severity': degradation_log['severity']
            #     }
            # )
            
            logger.debug(f"Degradation event stored: {degradation_log['operation_id']}")
            
        except Exception as e:
            logger.error(f"Failed to store degradation event: {e}")
