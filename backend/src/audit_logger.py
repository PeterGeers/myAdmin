"""
Audit Logging System for Duplicate Invoice Decisions

This module provides comprehensive audit logging capabilities for duplicate invoice
detection decisions, including querying, reporting, and compliance features.

Requirements: 3.2, 6.4, 6.5
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from database import DatabaseManager

# Configure logger
logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Comprehensive audit logging system for duplicate invoice decisions.
    
    Provides functionality for:
    - Recording duplicate detection decisions with full context
    - Querying audit logs with flexible filters
    - Generating compliance reports
    - Data retention management
    - Audit trail analysis
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the AuditLogger with a database manager.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager
        self.table_name = 'duplicate_decision_log'
    
    def log_decision(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float,
        decision: str,
        existing_transaction_id: Optional[int] = None,
        new_file_url: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        operation_id: Optional[str] = None
    ) -> bool:
        """
        Log a duplicate invoice decision to the audit trail.
        
        Args:
            reference_number: The reference number (folder name) of the transaction
            transaction_date: The transaction date in YYYY-MM-DD format
            transaction_amount: The transaction amount
            decision: User decision ('continue' or 'cancel')
            existing_transaction_id: ID of the existing duplicate transaction
            new_file_url: URL of the new file being imported
            user_id: Optional user identifier for audit purposes
            session_id: Optional session identifier for tracking
            operation_id: Optional operation identifier for correlation
        
        Returns:
            Boolean indicating if logging was successful
        
        Requirements: 3.2, 6.4, 6.5
        """
        try:
            query = f"""
                INSERT INTO {self.table_name}
                (timestamp, reference_number, transaction_date, transaction_amount,
                 decision, existing_transaction_id, new_file_url, user_id, session_id, operation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            self.db.execute_query(
                query,
                (
                    datetime.now(),
                    reference_number,
                    transaction_date,
                    transaction_amount,
                    decision,
                    existing_transaction_id,
                    new_file_url,
                    user_id,
                    session_id,
                    operation_id
                ),
                fetch=False,
                commit=True
            )
            
            logger.info(f"Audit log entry created: {decision} for {reference_number} on {transaction_date}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create audit log entry: {e}")
            return False
    
    def query_logs(
        self,
        reference_number: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        decision: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict]:
        """
        Query audit logs with flexible filtering options.
        
        Args:
            reference_number: Filter by reference number (supports wildcards)
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            decision: Filter by decision type ('continue' or 'cancel')
            user_id: Filter by user ID
            limit: Maximum number of records to return
            offset: Number of records to skip (for pagination)
        
        Returns:
            List of audit log entries matching the filters
        
        Requirements: 6.4, 6.5
        """
        try:
            # Build dynamic query based on filters
            conditions = []
            params = []
            
            if reference_number:
                conditions.append("reference_number LIKE %s")
                params.append(f"%{reference_number}%")
            
            if start_date:
                conditions.append("transaction_date >= %s")
                params.append(start_date)
            
            if end_date:
                conditions.append("transaction_date <= %s")
                params.append(end_date)
            
            if decision:
                conditions.append("decision = %s")
                params.append(decision)
            
            if user_id:
                conditions.append("user_id = %s")
                params.append(user_id)
            
            # Build WHERE clause
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            # Build complete query
            query = f"""
                SELECT id, timestamp, reference_number, transaction_date, transaction_amount,
                       decision, existing_transaction_id, new_file_url, user_id, session_id, operation_id
                FROM {self.table_name}
                {where_clause}
                ORDER BY timestamp DESC
                LIMIT %s OFFSET %s
            """
            
            params.extend([limit, offset])
            
            results = self.db.execute_query(query, tuple(params))
            
            logger.info(f"Audit log query returned {len(results) if results else 0} records")
            return results if results else []
            
        except Exception as e:
            logger.error(f"Failed to query audit logs: {e}")
            return []
    
    def get_decision_count(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        decision: Optional[str] = None
    ) -> int:
        """
        Get count of audit log entries matching filters.
        
        Args:
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            decision: Filter by decision type ('continue' or 'cancel')
        
        Returns:
            Count of matching audit log entries
        
        Requirements: 6.4, 6.5
        """
        try:
            conditions = []
            params = []
            
            if start_date:
                conditions.append("transaction_date >= %s")
                params.append(start_date)
            
            if end_date:
                conditions.append("transaction_date <= %s")
                params.append(end_date)
            
            if decision:
                conditions.append("decision = %s")
                params.append(decision)
            
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            query = f"""
                SELECT COUNT(*) as count
                FROM {self.table_name}
                {where_clause}
            """
            
            result = self.db.execute_query(query, tuple(params))
            
            if result and len(result) > 0:
                return result[0]['count']
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to get decision count: {e}")
            return 0
    
    def generate_compliance_report(
        self,
        start_date: str,
        end_date: str,
        include_details: bool = True
    ) -> Dict:
        """
        Generate a comprehensive compliance report for audit purposes.
        
        Args:
            start_date: Report start date (YYYY-MM-DD)
            end_date: Report end date (YYYY-MM-DD)
            include_details: Whether to include detailed transaction information
        
        Returns:
            Dictionary containing compliance report data
        
        Requirements: 6.4, 6.5
        """
        try:
            report = {
                'report_period': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'generated_at': datetime.now().isoformat()
                },
                'summary': {},
                'details': [] if include_details else None,
                'statistics': {}
            }
            
            # Get summary statistics
            total_decisions = self.get_decision_count(start_date, end_date)
            continue_decisions = self.get_decision_count(start_date, end_date, 'continue')
            cancel_decisions = self.get_decision_count(start_date, end_date, 'cancel')
            
            report['summary'] = {
                'total_decisions': total_decisions,
                'continue_decisions': continue_decisions,
                'cancel_decisions': cancel_decisions,
                'continue_percentage': round((continue_decisions / total_decisions * 100) if total_decisions > 0 else 0, 2),
                'cancel_percentage': round((cancel_decisions / total_decisions * 100) if total_decisions > 0 else 0, 2)
            }
            
            # Get detailed records if requested
            if include_details:
                report['details'] = self.query_logs(
                    start_date=start_date,
                    end_date=end_date,
                    limit=10000  # High limit for comprehensive reports
                )
            
            # Get statistics by reference number
            stats_query = f"""
                SELECT reference_number,
                       COUNT(*) as decision_count,
                       SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continue_count,
                       SUM(CASE WHEN decision = 'cancel' THEN 1 ELSE 0 END) as cancel_count,
                       SUM(transaction_amount) as total_amount
                FROM {self.table_name}
                WHERE transaction_date >= %s AND transaction_date <= %s
                GROUP BY reference_number
                ORDER BY decision_count DESC
                LIMIT 50
            """
            
            stats_results = self.db.execute_query(stats_query, (start_date, end_date))
            
            report['statistics'] = {
                'by_reference_number': stats_results if stats_results else [],
                'top_duplicate_vendors': [
                    {
                        'reference_number': r['reference_number'],
                        'decision_count': r['decision_count'],
                        'continue_count': r['continue_count'],
                        'cancel_count': r['cancel_count'],
                        'total_amount': float(r['total_amount']) if r['total_amount'] else 0
                    }
                    for r in (stats_results[:10] if stats_results else [])
                ]
            }
            
            # Get daily statistics
            daily_query = f"""
                SELECT DATE(timestamp) as date,
                       COUNT(*) as decision_count,
                       SUM(CASE WHEN decision = 'continue' THEN 1 ELSE 0 END) as continue_count,
                       SUM(CASE WHEN decision = 'cancel' THEN 1 ELSE 0 END) as cancel_count
                FROM {self.table_name}
                WHERE transaction_date >= %s AND transaction_date <= %s
                GROUP BY DATE(timestamp)
                ORDER BY date DESC
            """
            
            daily_results = self.db.execute_query(daily_query, (start_date, end_date))
            
            report['statistics']['daily_breakdown'] = [
                {
                    'date': str(r['date']),
                    'decision_count': r['decision_count'],
                    'continue_count': r['continue_count'],
                    'cancel_count': r['cancel_count']
                }
                for r in (daily_results if daily_results else [])
            ]
            
            logger.info(f"Compliance report generated for {start_date} to {end_date}")
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate compliance report: {e}")
            return {
                'error': str(e),
                'report_period': {
                    'start_date': start_date,
                    'end_date': end_date,
                    'generated_at': datetime.now().isoformat()
                }
            }
    
    def get_user_activity_report(
        self,
        user_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict:
        """
        Generate a user activity report for audit purposes.
        
        Args:
            user_id: User identifier to generate report for
            start_date: Optional start date filter (YYYY-MM-DD)
            end_date: Optional end date filter (YYYY-MM-DD)
        
        Returns:
            Dictionary containing user activity report data
        
        Requirements: 6.4, 6.5
        """
        try:
            report = {
                'user_id': user_id,
                'report_period': {
                    'start_date': start_date or 'all',
                    'end_date': end_date or 'all',
                    'generated_at': datetime.now().isoformat()
                },
                'summary': {},
                'recent_decisions': []
            }
            
            # Get user summary
            total_decisions = self.get_decision_count(start_date, end_date, None)
            user_decisions = len(self.query_logs(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                limit=10000
            ))
            
            user_continue = len(self.query_logs(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                decision='continue',
                limit=10000
            ))
            
            user_cancel = len(self.query_logs(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                decision='cancel',
                limit=10000
            ))
            
            report['summary'] = {
                'total_decisions': user_decisions,
                'continue_decisions': user_continue,
                'cancel_decisions': user_cancel,
                'percentage_of_all_decisions': round((user_decisions / total_decisions * 100) if total_decisions > 0 else 0, 2)
            }
            
            # Get recent decisions
            report['recent_decisions'] = self.query_logs(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                limit=20
            )
            
            logger.info(f"User activity report generated for user: {user_id}")
            return report
            
        except Exception as e:
            logger.error(f"Failed to generate user activity report: {e}")
            return {
                'error': str(e),
                'user_id': user_id,
                'report_period': {
                    'start_date': start_date or 'all',
                    'end_date': end_date or 'all',
                    'generated_at': datetime.now().isoformat()
                }
            }
    
    def cleanup_old_logs(
        self,
        retention_days: int = 730
    ) -> Tuple[bool, int]:
        """
        Clean up audit logs older than the retention period.
        
        Args:
            retention_days: Number of days to retain logs (default: 730 = 2 years)
        
        Returns:
            Tuple of (success: bool, deleted_count: int)
        
        Requirements: 6.5
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=retention_days)
            
            # First, count how many records will be deleted
            count_query = f"""
                SELECT COUNT(*) as count
                FROM {self.table_name}
                WHERE timestamp < %s
            """
            
            count_result = self.db.execute_query(count_query, (cutoff_date,))
            delete_count = count_result[0]['count'] if count_result else 0
            
            if delete_count == 0:
                logger.info("No old audit logs to clean up")
                return True, 0
            
            # Delete old records
            delete_query = f"""
                DELETE FROM {self.table_name}
                WHERE timestamp < %s
            """
            
            self.db.execute_query(delete_query, (cutoff_date,), fetch=False, commit=True)
            
            logger.info(f"Cleaned up {delete_count} audit log entries older than {retention_days} days")
            return True, delete_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old audit logs: {e}")
            return False, 0
    
    def export_logs_to_csv(
        self,
        output_file: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> bool:
        """
        Export audit logs to CSV file for external analysis.
        
        Args:
            output_file: Path to output CSV file
            start_date: Optional start date filter (YYYY-MM-DD)
            end_date: Optional end date filter (YYYY-MM-DD)
        
        Returns:
            Boolean indicating if export was successful
        
        Requirements: 6.4, 6.5
        """
        try:
            import csv
            
            # Get logs to export
            logs = self.query_logs(
                start_date=start_date,
                end_date=end_date,
                limit=100000  # High limit for exports
            )
            
            if not logs:
                logger.warning("No logs to export")
                return False
            
            # Write to CSV
            with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'id', 'timestamp', 'reference_number', 'transaction_date',
                    'transaction_amount', 'decision', 'existing_transaction_id',
                    'new_file_url', 'user_id', 'session_id', 'operation_id'
                ]
                
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for log in logs:
                    # Convert datetime objects to strings
                    row = {k: str(v) if v is not None else '' for k, v in log.items()}
                    writer.writerow(row)
            
            logger.info(f"Exported {len(logs)} audit log entries to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export audit logs to CSV: {e}")
            return False
    
    def get_audit_trail_for_transaction(
        self,
        reference_number: str,
        transaction_date: str,
        transaction_amount: float
    ) -> List[Dict]:
        """
        Get complete audit trail for a specific transaction.
        
        Args:
            reference_number: The reference number of the transaction
            transaction_date: The transaction date (YYYY-MM-DD)
            transaction_amount: The transaction amount
        
        Returns:
            List of all audit log entries for this transaction
        
        Requirements: 6.4, 6.5
        """
        try:
            query = f"""
                SELECT id, timestamp, reference_number, transaction_date, transaction_amount,
                       decision, existing_transaction_id, new_file_url, user_id, session_id, operation_id
                FROM {self.table_name}
                WHERE reference_number = %s
                  AND transaction_date = %s
                  AND ABS(transaction_amount - %s) < 0.01
                ORDER BY timestamp DESC
            """
            
            results = self.db.execute_query(
                query,
                (reference_number, transaction_date, transaction_amount)
            )
            
            logger.info(f"Retrieved {len(results) if results else 0} audit trail entries for transaction")
            return results if results else []
            
        except Exception as e:
            logger.error(f"Failed to get audit trail for transaction: {e}")
            return []
