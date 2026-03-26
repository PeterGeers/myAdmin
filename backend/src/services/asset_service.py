"""
Asset Service

Business logic for asset administration:
- CRUD operations on the assets table
- Purchase transaction generation in mutaties
- Book value calculation from depreciation history
- Asset disposal with write-off transactions

Transactions are linked to assets via Ref1 = 'ASSET-{asset_id}'.
See .kiro/specs/FIN/Data Model/mutaties_ref_fields.md
"""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional, List

logger = logging.getLogger(__name__)


class AssetService:
    """Asset administration service."""

    def __init__(self, db_manager):
        self.db = db_manager

    def create_asset(self, administration: str, data: dict) -> dict:
        """
        Create a new asset and optionally insert the purchase transaction.

        Args:
            administration: Tenant identifier
            data: Asset data dict with keys matching the assets table columns

        Returns:
            {'success': True, 'asset_id': int, 'transaction_created': bool}
        """
        # Insert asset record — returns lastrowid when commit=True
        asset_id = self.db.execute_query(
            """
            INSERT INTO assets (
                administration, description, category, ledger_account,
                depreciation_account, purchase_date, purchase_amount,
                depreciation_method, depreciation_frequency,
                useful_life_years, residual_value, reference_number, notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                administration,
                data['description'],
                data.get('category'),
                data['ledger_account'],
                data.get('depreciation_account'),
                data['purchase_date'],
                data['purchase_amount'],
                data.get('depreciation_method', 'straight_line'),
                data.get('depreciation_frequency', 'annual'),
                data.get('useful_life_years'),
                data.get('residual_value', 0),
                data.get('reference_number'),
                data.get('notes'),
            ),
            commit=True
        )

        if not asset_id:
            raise Exception("Failed to retrieve asset ID after insert")

        # Optionally create purchase transaction in mutaties
        transaction_created = False
        if data.get('create_transaction', True):
            credit_account = data.get('credit_account')  # e.g., bank account
            if credit_account:
                self._insert_transaction(
                    administration=administration,
                    date=data['purchase_date'],
                    description=f"Aankoop: {data['description']}",
                    amount=data['purchase_amount'],
                    debet=data['ledger_account'],
                    credit=credit_account,
                    reference_number=data.get('reference_number', f'Asset-{asset_id}'),
                    ref1=f'ASSET-{asset_id}',
                )
                transaction_created = True

        logger.info(
            f"Asset {asset_id} created for '{administration}': "
            f"{data['description']} ({data['purchase_amount']})"
        )
        return {
            'success': True,
            'asset_id': asset_id,
            'transaction_created': transaction_created
        }

    def get_assets(
        self, administration: str,
        status: Optional[str] = None,
        category: Optional[str] = None,
        ledger_account: Optional[str] = None,
    ) -> List[dict]:
        """
        List assets with current book values.

        Book value = purchase_amount - SUM(depreciation transactions).
        """
        where = ["a.administration = %s"]
        params: list = [administration]

        if status:
            where.append("a.status = %s")
            params.append(status)
        if category:
            where.append("a.category = %s")
            params.append(category)
        if ledger_account:
            where.append("a.ledger_account = %s")
            params.append(ledger_account)

        query = f"""
            SELECT
                a.*,
                COALESCE(dep.total_depreciation, 0) AS total_depreciation,
                a.purchase_amount - COALESCE(dep.total_depreciation, 0) AS book_value
            FROM assets a
            LEFT JOIN (
                SELECT
                    SUBSTRING(Ref1, 7) AS asset_id_str,
                    SUM(ABS(TransactionAmount)) AS total_depreciation
                FROM mutaties
                WHERE Ref1 LIKE 'ASSET-%%'
                AND ReferenceNumber LIKE 'Afschrijving%%'
                AND administration = %s
                GROUP BY SUBSTRING(Ref1, 7)
            ) dep ON dep.asset_id_str = CAST(a.id AS CHAR)
            WHERE {' AND '.join(where)}
            ORDER BY a.purchase_date DESC
        """
        params_full = [administration] + params

        results = self.db.execute_query(query, tuple(params_full), fetch=True)
        assets = []
        for row in (results or []):
            asset = dict(row)
            for field in ('purchase_date', 'disposal_date', 'created_at', 'updated_at'):
                if asset.get(field) and hasattr(asset[field], 'isoformat'):
                    asset[field] = asset[field].isoformat()
            # Convert Decimal to float for JSON
            for field in ('purchase_amount', 'residual_value', 'disposal_amount',
                          'total_depreciation', 'book_value'):
                if isinstance(asset.get(field), Decimal):
                    asset[field] = float(asset[field])
            assets.append(asset)

        return assets

    def get_asset(self, administration: str, asset_id: int) -> Optional[dict]:
        """
        Get single asset with transaction history.
        """
        # Get asset record
        result = self.db.execute_query(
            "SELECT * FROM assets WHERE id = %s AND administration = %s",
            (asset_id, administration), fetch=True
        )
        if not result:
            return None

        asset = dict(result[0])
        for field in ('purchase_date', 'disposal_date', 'created_at', 'updated_at'):
            if asset.get(field) and hasattr(asset[field], 'isoformat'):
                asset[field] = asset[field].isoformat()
        for field in ('purchase_amount', 'residual_value', 'disposal_amount'):
            if isinstance(asset.get(field), Decimal):
                asset[field] = float(asset[field])

        # Get linked transactions
        transactions = self.db.execute_query(
            """
            SELECT ID, TransactionDate, TransactionDescription, TransactionAmount,
                   Debet, Credit, ReferenceNumber, Ref1, Ref2
            FROM mutaties
            WHERE Ref1 = %s AND administration = %s
            ORDER BY TransactionDate
            """,
            (f'ASSET-{asset_id}', administration), fetch=True
        )

        asset['transactions'] = []
        total_depreciation = 0
        for tx in (transactions or []):
            t = dict(tx)
            if hasattr(t.get('TransactionDate'), 'isoformat'):
                t['TransactionDate'] = t['TransactionDate'].isoformat()
            if isinstance(t.get('TransactionAmount'), Decimal):
                t['TransactionAmount'] = float(t['TransactionAmount'])
            # Determine transaction type from ReferenceNumber
            ref = t.get('ReferenceNumber', '')
            if ref.startswith('Afschrijving'):
                t['type'] = 'depreciation'
                total_depreciation += abs(t['TransactionAmount'])
            elif ref.startswith('Afboeking'):
                t['type'] = 'disposal'
            else:
                t['type'] = 'purchase'
            asset['transactions'].append(t)

        asset['total_depreciation'] = total_depreciation
        asset['book_value'] = float(asset['purchase_amount']) - total_depreciation

        return asset

    def update_asset(self, administration: str, asset_id: int, data: dict) -> dict:
        """
        Update asset metadata.

        Financial fields (purchase_amount, purchase_date, ledger_account) cannot
        be changed after the first depreciation entry exists.
        """
        # Check asset exists
        existing = self.db.execute_query(
            "SELECT id FROM assets WHERE id = %s AND administration = %s",
            (asset_id, administration), fetch=True
        )
        if not existing:
            return {'success': False, 'error': 'Asset not found'}

        # Check if depreciation entries exist (locks financial fields)
        dep_count = self.db.execute_query(
            """
            SELECT COUNT(*) as cnt FROM mutaties
            WHERE Ref1 = %s AND administration = %s
            AND ReferenceNumber LIKE 'Afschrijving%%'
            """,
            (f'ASSET-{asset_id}', administration), fetch=True
        )
        has_depreciation = dep_count and dep_count[0]['cnt'] > 0

        # Build update
        allowed_fields = {
            'description': 'description',
            'category': 'category',
            'depreciation_account': 'depreciation_account',
            'depreciation_method': 'depreciation_method',
            'depreciation_frequency': 'depreciation_frequency',
            'useful_life_years': 'useful_life_years',
            'residual_value': 'residual_value',
            'reference_number': 'reference_number',
            'notes': 'notes',
        }
        # Financial fields only if no depreciation yet
        if not has_depreciation:
            allowed_fields.update({
                'purchase_amount': 'purchase_amount',
                'purchase_date': 'purchase_date',
                'ledger_account': 'ledger_account',
            })

        updates = []
        params = []
        locked_fields = []
        for key, col in allowed_fields.items():
            if key in data:
                updates.append(f"{col} = %s")
                params.append(data[key])

        # Report locked fields that were attempted
        if has_depreciation:
            for key in ('purchase_amount', 'purchase_date', 'ledger_account'):
                if key in data:
                    locked_fields.append(key)

        if not updates:
            return {'success': False, 'error': 'No fields to update'}

        params.extend([asset_id, administration])
        self.db.execute_query(
            f"UPDATE assets SET {', '.join(updates)} WHERE id = %s AND administration = %s",
            tuple(params), commit=True
        )

        result = {'success': True, 'asset_id': asset_id}
        if locked_fields:
            result['locked_fields'] = locked_fields
            result['warning'] = (
                f"Fields {locked_fields} cannot be changed after depreciation has started"
            )
        return result

    def dispose_asset(
        self, administration: str, asset_id: int,
        disposal_date: str, disposal_amount: float,
        credit_account: Optional[str] = None,
    ) -> dict:
        """
        Dispose an asset: mark as disposed and create write-off transaction.

        Args:
            administration: Tenant identifier
            asset_id: Asset ID
            disposal_date: Date of disposal (YYYY-MM-DD)
            disposal_amount: Sale price (0 if scrapped)
            credit_account: Bank account for sale proceeds (optional)
        """
        asset = self.get_asset(administration, asset_id)
        if not asset:
            return {'success': False, 'error': 'Asset not found'}
        if asset['status'] == 'disposed':
            return {'success': False, 'error': 'Asset already disposed'}

        book_value = asset['book_value']
        write_off = book_value - disposal_amount

        # Update asset status
        self.db.execute_query(
            """
            UPDATE assets
            SET status = 'disposed', disposal_date = %s, disposal_amount = %s
            WHERE id = %s AND administration = %s
            """,
            (disposal_date, disposal_amount, asset_id, administration),
            commit=True
        )

        # Create write-off transaction if there's remaining book value
        if abs(write_off) > 0.01:
            self._insert_transaction(
                administration=administration,
                date=disposal_date,
                description=f"Afboeking: {asset['description']}",
                amount=abs(write_off),
                debet=asset['depreciation_account'] or '8099',
                credit=asset['ledger_account'],
                reference_number=f"Afboeking ASSET-{asset_id}",
                ref1=f'ASSET-{asset_id}',
            )

        # Create sale proceeds transaction if sold (not scrapped)
        if disposal_amount > 0 and credit_account:
            self._insert_transaction(
                administration=administration,
                date=disposal_date,
                description=f"Verkoop: {asset['description']}",
                amount=disposal_amount,
                debet=credit_account,
                credit=asset['ledger_account'],
                reference_number=f"Afboeking ASSET-{asset_id}",
                ref1=f'ASSET-{asset_id}',
            )

        logger.info(
            f"Asset {asset_id} disposed for '{administration}': "
            f"book_value={book_value}, disposal={disposal_amount}, "
            f"write_off={write_off}"
        )
        return {
            'success': True,
            'asset_id': asset_id,
            'book_value': book_value,
            'disposal_amount': disposal_amount,
            'write_off': write_off,
        }

    # -------------------------------------------------------------------------
    # Depreciation generation
    # -------------------------------------------------------------------------

    def generate_depreciation(
        self, administration: str, period: str, year: int
    ) -> dict:
        """
        Generate depreciation entries for a given period.

        Idempotent — skips assets that already have a depreciation entry
        for this period.

        Args:
            administration: Tenant identifier
            period: Period identifier — 'annual', 'Q1'-'Q4', or 'M01'-'M12'
            year: Year (e.g., 2026)

        Returns:
            {
                'success': True,
                'year': 2026,
                'period': 'Q1',
                'assets_processed': 5,
                'entries_created': 3,
                'entries_skipped': 2,
                'details': [{'asset_id': 1, 'description': '...', 'amount': 750, 'status': 'created'}, ...]
            }
        """
        ref2 = f'{year}-{period}' if period != 'annual' else str(year)
        reference_number = f'Afschrijving {year}'

        # Get active assets that need depreciation
        assets = self.db.execute_query(
            """
            SELECT id, description, purchase_amount, residual_value,
                   useful_life_years, depreciation_method, depreciation_frequency,
                   ledger_account, depreciation_account
            FROM assets
            WHERE administration = %s
            AND status = 'active'
            AND depreciation_method != 'none'
            AND useful_life_years > 0
            """,
            (administration,), fetch=True
        )

        results = {
            'success': True,
            'year': year,
            'period': period,
            'assets_processed': 0,
            'entries_created': 0,
            'entries_skipped': 0,
            'details': [],
        }

        for asset in (assets or []):
            asset_id = asset['id']
            results['assets_processed'] += 1

            # Check if this period's depreciation already exists (idempotent)
            existing = self.db.execute_query(
                """
                SELECT COUNT(*) as cnt FROM mutaties
                WHERE Ref1 = %s AND Ref2 = %s AND administration = %s
                AND ReferenceNumber LIKE 'Afschrijving%%'
                """,
                (f'ASSET-{asset_id}', ref2, administration), fetch=True
            )
            if existing and existing[0]['cnt'] > 0:
                results['entries_skipped'] += 1
                results['details'].append({
                    'asset_id': asset_id,
                    'description': asset['description'],
                    'status': 'skipped',
                    'reason': f'Already exists for {ref2}',
                })
                continue

            # Calculate period amount
            amount = self._calculate_period_amount(asset, period)
            if amount <= 0:
                results['entries_skipped'] += 1
                results['details'].append({
                    'asset_id': asset_id,
                    'description': asset['description'],
                    'status': 'skipped',
                    'reason': 'Calculated amount is zero',
                })
                continue

            # Determine the transaction date
            tx_date = self._period_end_date(year, period)

            # Insert depreciation transaction
            dep_account = asset['depreciation_account'] or '4017'
            self._insert_transaction(
                administration=administration,
                date=tx_date,
                description=f"Afschrijving: {asset['description']}",
                amount=round(amount, 2),
                debet=dep_account,
                credit=asset['ledger_account'],
                reference_number=reference_number,
                ref1=f'ASSET-{asset_id}',
                ref2=ref2,
            )

            results['entries_created'] += 1
            results['details'].append({
                'asset_id': asset_id,
                'description': asset['description'],
                'amount': round(amount, 2),
                'status': 'created',
            })

        logger.info(
            f"Depreciation for '{administration}' {year}/{period}: "
            f"{results['entries_created']} created, "
            f"{results['entries_skipped']} skipped"
        )
        return results

    def _calculate_period_amount(self, asset: dict, period: str) -> float:
        """
        Calculate depreciation amount for a single period.

        Straight-line: (purchase - residual) / useful_life / periods_per_year
        Declining balance: book_value * (2 / useful_life) / periods_per_year
        """
        purchase = float(asset['purchase_amount'])
        residual = float(asset.get('residual_value') or 0)
        life = asset['useful_life_years']
        method = asset['depreciation_method']
        frequency = asset.get('depreciation_frequency', 'annual')

        if life <= 0:
            return 0

        # Periods per year based on frequency
        periods = {'annual': 1, 'quarterly': 4, 'monthly': 12}.get(frequency, 1)

        # Check period matches frequency
        if not self._period_matches_frequency(period, frequency):
            return 0

        if method == 'straight_line':
            annual = (purchase - residual) / life
            return annual / periods

        elif method == 'declining_balance':
            # For declining balance, we'd need current book value
            # Simplified: use double-declining rate
            rate = 2.0 / life
            annual = purchase * rate  # simplified — should use current book value
            return annual / periods

        return 0

    def _period_matches_frequency(self, period: str, frequency: str) -> bool:
        """Check if the requested period matches the asset's depreciation frequency."""
        if frequency == 'annual':
            return period == 'annual'
        elif frequency == 'quarterly':
            return period in ('Q1', 'Q2', 'Q3', 'Q4')
        elif frequency == 'monthly':
            return period.startswith('M') and len(period) == 3
        return False

    def _period_end_date(self, year: int, period: str) -> str:
        """Return the last day of the period as YYYY-MM-DD."""
        if period == 'annual':
            return f'{year}-12-31'
        elif period == 'Q1':
            return f'{year}-03-31'
        elif period == 'Q2':
            return f'{year}-06-30'
        elif period == 'Q3':
            return f'{year}-09-30'
        elif period == 'Q4':
            return f'{year}-12-31'
        elif period.startswith('M'):
            month = int(period[1:])
            if month == 12:
                return f'{year}-12-31'
            from calendar import monthrange
            _, last_day = monthrange(year, month)
            return f'{year}-{month:02d}-{last_day:02d}'
        return f'{year}-12-31'

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _insert_transaction(
        self, administration: str, date: str, description: str,
        amount: float, debet: str, credit: str,
        reference_number: str, ref1: str, ref2: str = '',
    ):
        """Insert a transaction into mutaties."""
        self.db.execute_query(
            """
            INSERT INTO mutaties (
                TransactionNumber, TransactionDate, TransactionDescription,
                TransactionAmount, Debet, Credit, ReferenceNumber,
                Ref1, Ref2, Ref3, Ref4, Administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                f'ASSET-{datetime.now().strftime("%Y%m%d%H%M%S")}',
                date, description, amount,
                debet, credit, reference_number,
                ref1, ref2, '', '', administration
            ),
            commit=True
        )
