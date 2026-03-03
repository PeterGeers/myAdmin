"""
Year-End Closure Configuration Service

Manages account purpose configuration for year-end closure process.
Uses parameters JSON column in rekeningschema table.

Account Purposes:
- equity_result: Where net P&L result is recorded (e.g., 3080)
- pl_closing: Used in year-end closure transaction (e.g., 8099)

Note: Opening balances use equity_result account for balancing (no separate interim account needed).
"""

from database import DatabaseManager


class YearEndConfigService:
    """Service for managing year-end closure configuration"""
    
    # Required account purposes for year-end closure
    REQUIRED_PURPOSES = {
        'equity_result': {
            'description': 'Equity result account (where net P&L is recorded)',
            'expected_vw': 'N',  # Balance sheet account
            'example': '3080'
        },
        'pl_closing': {
            'description': 'P&L closing account (used in closure transaction)',
            'expected_vw': 'Y',  # P&L account
            'example': '8099'
        }
    }
    
    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)
    
    def get_account_by_purpose(self, administration, purpose):
        """
        Get account code by parameter purpose.
        
        Args:
            administration: Tenant identifier
            purpose: Account purpose (equity_result, pl_closing)
            
        Returns:
            str: Account code or None if not found
        """
        query = """
            SELECT Account, AccountName, VW
            FROM rekeningschema
            WHERE administration = %s
            AND JSON_EXTRACT(parameters, '$.purpose') = %s
        """
        
        result = self.db.execute_query(query, [administration, purpose])
        return result[0] if result else None
    
    def set_account_purpose(self, administration, account_code, purpose):
        """
        Set purpose for an account.
        
        Args:
            administration: Tenant identifier
            account_code: Account code
            purpose: Account purpose to assign
            
        Returns:
            bool: True if successful
            
        Raises:
            ValueError: If account doesn't exist or purpose is invalid
        """
        # Validate purpose
        if purpose not in self.REQUIRED_PURPOSES:
            raise ValueError(f"Invalid purpose: {purpose}. Must be one of: {', '.join(self.REQUIRED_PURPOSES.keys())}")
        
        # Check if account exists
        account = self._get_account(administration, account_code)
        if not account:
            raise ValueError(f"Account {account_code} not found for administration {administration}")
        
        # Validate VW classification
        expected_vw = self.REQUIRED_PURPOSES[purpose]['expected_vw']
        if account['VW'] != expected_vw:
            raise ValueError(
                f"Account {account_code} has VW='{account['VW']}' but purpose '{purpose}' requires VW='{expected_vw}'"
            )
        
        # Check if purpose is already assigned to another account
        existing = self.get_account_by_purpose(administration, purpose)
        if existing and existing['Account'] != account_code:
            raise ValueError(
                f"Purpose '{purpose}' is already assigned to account {existing['Account']}. "
                f"Remove it first or use update_account_purpose()."
            )
        
        # Set the purpose
        update_query = """
            UPDATE rekeningschema
            SET parameters = JSON_SET(COALESCE(parameters, '{}'), '$.purpose', %s)
            WHERE administration = %s
            AND Account = %s
        """
        
        self.db.execute_query(update_query, [purpose, administration, account_code], fetch=False, commit=True)
        return True
    
    def remove_account_purpose(self, administration, account_code):
        """
        Remove purpose from an account.
        
        Args:
            administration: Tenant identifier
            account_code: Account code
            
        Returns:
            bool: True if successful
        """
        update_query = """
            UPDATE rekeningschema
            SET parameters = JSON_REMOVE(COALESCE(parameters, '{}'), '$.purpose')
            WHERE administration = %s
            AND Account = %s
        """
        
        self.db.execute_query(update_query, [administration, account_code], fetch=False, commit=True)
        return True
    
    def get_all_configured_purposes(self, administration):
        """
        Get all configured account purposes for an administration.
        
        Args:
            administration: Tenant identifier
            
        Returns:
            dict: Dictionary mapping purpose names to account info
        """
        query = """
            SELECT 
                Account,
                AccountName,
                VW,
                JSON_EXTRACT(parameters, '$.purpose') as purpose
            FROM rekeningschema
            WHERE administration = %s
            AND JSON_EXTRACT(parameters, '$.purpose') IS NOT NULL
        """
        
        results = self.db.execute_query(query, [administration])
        
        # Convert to dictionary keyed by purpose
        configured = {}
        for row in results:
            purpose = row['purpose'].strip('"') if row['purpose'] else None
            if purpose:
                configured[purpose] = {
                    'account_code': row['Account'],
                    'account_name': row['AccountName'],
                    'vw': row['VW']
                }
        
        return configured
    
    def validate_configuration(self, administration):
        """
        Validate year-end closure configuration for an administration.
        
        Args:
            administration: Tenant identifier
            
        Returns:
            dict: Validation result with 'valid', 'errors', 'warnings', 'configured_purposes'
        """
        validation = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'configured_purposes': {}
        }
        
        # Get all configured purposes
        configured = self.get_all_configured_purposes(administration)
        validation['configured_purposes'] = configured
        
        # Check for required purposes
        for purpose, info in self.REQUIRED_PURPOSES.items():
            if purpose not in configured:
                validation['valid'] = False
                validation['errors'].append(
                    f"Missing required purpose '{purpose}': {info['description']} (example: {info['example']})"
                )
            else:
                # Validate VW classification
                account = configured[purpose]
                if account['vw'] != info['expected_vw']:
                    validation['valid'] = False
                    validation['errors'].append(
                        f"Account {account['account_code']} for purpose '{purpose}' has VW='{account['vw']}' "
                        f"but should be VW='{info['expected_vw']}'"
                    )
        
        # Check for duplicate purpose assignments (shouldn't happen but validate anyway)
        purpose_counts = {}
        for purpose in configured.keys():
            purpose_counts[purpose] = purpose_counts.get(purpose, 0) + 1
        
        for purpose, count in purpose_counts.items():
            if count > 1:
                validation['valid'] = False
                validation['errors'].append(f"Purpose '{purpose}' is assigned to multiple accounts")
        
        return validation
    
    def _get_account(self, administration, account_code):
        """Get account details"""
        query = """
            SELECT Account, AccountName, VW, parameters
            FROM rekeningschema
            WHERE administration = %s
            AND Account = %s
        """
        
        result = self.db.execute_query(query, [administration, account_code])
        return result[0] if result else None
    
    def get_available_accounts(self, administration, vw_filter=None):
        """
        Get available accounts for purpose assignment.
        
        Args:
            administration: Tenant identifier
            vw_filter: Optional VW filter ('Y' or 'N')
            
        Returns:
            list: List of account dictionaries
        """
        query = """
            SELECT 
                Account,
                AccountName,
                VW,
                JSON_EXTRACT(parameters, '$.purpose') as current_purpose
            FROM rekeningschema
            WHERE administration = %s
        """
        
        params = [administration]
        
        if vw_filter:
            query += " AND VW = %s"
            params.append(vw_filter)
        
        query += " ORDER BY Account"
        
        results = self.db.execute_query(query, params)
        
        # Clean up purpose field
        for row in results:
            if row['current_purpose']:
                row['current_purpose'] = row['current_purpose'].strip('"')
        
        return results

    
    def get_vat_netting_accounts(self, administration):
        """
        Get all accounts with VAT netting enabled.
        
        Args:
            administration: Tenant identifier
            
        Returns:
            list: List of account dictionaries with VAT netting enabled
        """
        query = """
            SELECT 
                Account,
                AccountName,
                VW,
                JSON_EXTRACT(parameters, '$.vat_netting') as vat_netting,
                JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
            FROM rekeningschema
            WHERE administration = %s
            AND (
                JSON_EXTRACT(parameters, '$.vat_netting') = true
                OR JSON_EXTRACT(parameters, '$.vat_netting') = 'true'
            )
            ORDER BY Account
        """
        
        results = self.db.execute_query(query, [administration])
        
        # Clean up JSON extracted values
        for row in results:
            if row.get('vat_netting'):
                # Handle both boolean true and string "true"
                vat_netting_val = row['vat_netting']
                if isinstance(vat_netting_val, str):
                    row['vat_netting'] = vat_netting_val.strip('"').lower() == 'true'
                else:
                    row['vat_netting'] = bool(vat_netting_val)
            if row.get('vat_primary'):
                vat_primary_val = row['vat_primary']
                if isinstance(vat_primary_val, str):
                    row['vat_primary'] = vat_primary_val.strip('"')
                else:
                    row['vat_primary'] = str(vat_primary_val) if vat_primary_val else None
        
        return results
    
    def get_vat_primary_account(self, administration):
        """
        Get the primary VAT account code.
        
        Args:
            administration: Tenant identifier
            
        Returns:
            str: Primary VAT account code or None
        """
        query = """
            SELECT JSON_EXTRACT(parameters, '$.vat_primary') as vat_primary
            FROM rekeningschema
            WHERE administration = %s
            AND (
                JSON_EXTRACT(parameters, '$.vat_netting') = true
                OR JSON_EXTRACT(parameters, '$.vat_netting') = 'true'
            )
            LIMIT 1
        """
        
        result = self.db.execute_query(query, [administration])
        
        if result and result[0].get('vat_primary'):
            vat_primary_val = result[0]['vat_primary']
            if isinstance(vat_primary_val, str):
                return vat_primary_val.strip('"')
            else:
                return str(vat_primary_val) if vat_primary_val else None
        
        return None
    
    def configure_vat_netting(self, administration, vat_accounts, primary_account):
        """
        Configure VAT netting for specified accounts.
        
        Args:
            administration: Tenant identifier
            vat_accounts: List of account codes to net together
            primary_account: Primary account for net balance
            
        Returns:
            bool: True if successful
        """
        # First, remove VAT netting from all accounts
        self.remove_vat_netting(administration)
        
        # Then, configure specified accounts
        update_query = """
            UPDATE rekeningschema
            SET parameters = JSON_SET(
                COALESCE(parameters, '{}'),
                '$.vat_netting', true,
                '$.vat_primary', %s
            )
            WHERE administration = %s
            AND Account = %s
        """
        
        for account in vat_accounts:
            self.db.execute_query(
                update_query,
                [primary_account, administration, account],
                fetch=False,
                commit=True
            )
        
        return True
    
    def remove_vat_netting(self, administration):
        """
        Remove VAT netting configuration from all accounts.
        
        Args:
            administration: Tenant identifier
            
        Returns:
            bool: True if successful
        """
        update_query = """
            UPDATE rekeningschema
            SET parameters = JSON_REMOVE(
                COALESCE(parameters, '{}'),
                '$.vat_netting',
                '$.vat_primary'
            )
            WHERE administration = %s
            AND JSON_EXTRACT(parameters, '$.vat_netting') IS NOT NULL
        """
        
        self.db.execute_query(update_query, [administration], fetch=False, commit=True)
        return True
