"""
Tenant Settings Service

This service handles tenant-specific settings and activity tracking.
Settings are stored in the tenants table settings column as JSON.
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from database import DatabaseManager

logger = logging.getLogger(__name__)


class TenantSettingsService:
    """
    Service for managing tenant settings and activity.
    """
    
    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize the tenant settings service.
        
        Args:
            db_manager: DatabaseManager instance for database operations
        """
        self.db = db_manager
        logger.info("TenantSettingsService initialized")
    
    def get_settings(self, administration: str) -> Dict[str, Any]:
        """
        Get all settings for a tenant.
        
        Args:
            administration: The tenant/administration identifier
            
        Returns:
            Dict with tenant settings
            
        Raises:
            Exception: If tenant not found or query fails
        """
        try:
            query = """
                SELECT config_key, config_value, is_secret
                FROM tenant_config
                WHERE administration = %s
            """
            
            results = self.db.execute_query(query, (administration,))
            
            # Build nested settings dict from key-value pairs
            settings = {}
            for row in results:
                key = row['config_key']
                value = row['config_value']
                
                # Parse JSON values if they look like JSON
                if value and (value.startswith('{') or value.startswith('[')):
                    try:
                        value = json.loads(value)
                    except:
                        pass  # Keep as string if not valid JSON
                
                # Build nested structure from dot notation (e.g., "storage.facturen_folder_id")
                if '.' in key:
                    parts = key.split('.')
                    current = settings
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = value
                else:
                    settings[key] = value
            
            logger.info(f"Retrieved settings for tenant {administration}")
            
            return settings
            
        except Exception as e:
            logger.error(f"Failed to get settings for {administration}: {e}")
            raise
    
    def update_settings(self, administration: str, settings: Dict[str, Any]) -> bool:
        """
        Update settings for a tenant.
        
        Stores settings as key-value pairs in tenant_config table.
        
        Args:
            administration: The tenant/administration identifier
            settings: Dict with settings to update
            
        Returns:
            True if successful
            
        Raises:
            Exception: If update fails
        """
        try:
            # Flatten nested dict to key-value pairs with dot notation
            flat_settings = self._flatten_dict(settings)
            
            # Insert or update each setting
            for key, value in flat_settings.items():
                # Convert value to string (JSON for complex types)
                if isinstance(value, (dict, list)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value) if value is not None else None
                
                query = """
                    INSERT INTO tenant_config (administration, config_key, config_value, is_secret)
                    VALUES (%s, %s, %s, FALSE)
                    ON DUPLICATE KEY UPDATE
                        config_value = VALUES(config_value),
                        updated_at = CURRENT_TIMESTAMP
                """
                
                self.db.execute_query(
                    query,
                    (administration, key, value_str),
                    fetch=False,
                    commit=True
                )
            
            logger.info(f"Updated settings for tenant {administration}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update settings for {administration}: {e}")
            raise
    
    def _flatten_dict(self, d: Dict, parent_key: str = '', sep: str = '.') -> Dict:
        """
        Flatten a nested dictionary using dot notation.
        
        Args:
            d: Dictionary to flatten
            parent_key: Parent key prefix
            sep: Separator for nested keys
            
        Returns:
            Flattened dictionary
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
    
    def get_activity(self, administration: str, date_range: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Get activity statistics for a tenant.
        
        Args:
            administration: The tenant/administration identifier
            date_range: Optional dict with 'start_date' and 'end_date' (ISO format)
            
        Returns:
            Dict with activity statistics
            
        Raises:
            Exception: If query fails
        """
        try:
            # Parse date range
            if date_range:
                start_date = date_range.get('start_date')
                end_date = date_range.get('end_date')
            else:
                # Default to last 30 days
                end_date = datetime.now().isoformat()
                start_date = (datetime.now() - timedelta(days=30)).isoformat()
            
            # Get activity from audit_log table
            activity_stats = {
                'date_range': {
                    'start': start_date,
                    'end': end_date
                },
                'total_actions': 0,
                'actions_by_type': {},
                'actions_by_user': {},
                'recent_actions': []
            }
            
            # Check if audit_log table exists
            try:
                # Get total actions
                query = """
                    SELECT COUNT(*) as count
                    FROM audit_log
                    WHERE tenant = %s
                    AND timestamp >= %s
                    AND timestamp <= %s
                """
                
                results = self.db.execute_query(query, (administration, start_date, end_date))
                activity_stats['total_actions'] = results[0]['count'] if results else 0
                
                # Get actions by type
                query = """
                    SELECT action_type, COUNT(*) as count
                    FROM audit_log
                    WHERE tenant = %s
                    AND timestamp >= %s
                    AND timestamp <= %s
                    GROUP BY action_type
                    ORDER BY count DESC
                """
                
                results = self.db.execute_query(query, (administration, start_date, end_date))
                activity_stats['actions_by_type'] = {
                    row['action_type']: row['count']
                    for row in results
                }
                
                # Get actions by user
                query = """
                    SELECT user_email, COUNT(*) as count
                    FROM audit_log
                    WHERE tenant = %s
                    AND timestamp >= %s
                    AND timestamp <= %s
                    GROUP BY user_email
                    ORDER BY count DESC
                    LIMIT 10
                """
                
                results = self.db.execute_query(query, (administration, start_date, end_date))
                activity_stats['actions_by_user'] = {
                    row['user_email']: row['count']
                    for row in results
                }
                
                # Get recent actions
                query = """
                    SELECT action_type, user_email, timestamp, details
                    FROM audit_log
                    WHERE tenant = %s
                    AND timestamp >= %s
                    AND timestamp <= %s
                    ORDER BY timestamp DESC
                    LIMIT 20
                """
                
                results = self.db.execute_query(query, (administration, start_date, end_date))
                activity_stats['recent_actions'] = [
                    {
                        'action_type': row['action_type'],
                        'user_email': row['user_email'],
                        'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None,
                        'details': row.get('details', {})
                    }
                    for row in results
                ]
                
            except Exception as e:
                # Audit log table might not exist or be accessible
                logger.warning(f"Could not retrieve audit log data: {e}")
                activity_stats['error'] = 'Audit log not available'
            
            logger.info(f"Retrieved activity for tenant {administration}")
            
            return activity_stats
            
        except Exception as e:
            logger.error(f"Failed to get activity for {administration}: {e}")
            raise
    
    def _deep_merge(self, dict1: Dict, dict2: Dict) -> Dict:
        """
        Deep merge two dictionaries.
        
        Args:
            dict1: Base dictionary
            dict2: Dictionary to merge into dict1
            
        Returns:
            Merged dictionary
        """
        result = dict1.copy()
        
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
