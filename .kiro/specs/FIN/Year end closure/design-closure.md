# Year-End Closure - Feature Design

**Status**: Draft  
**Related**: requirements.md (Tasks 2 & 3: Calculate Net P&L Result and Create Opening Balances)  
**Purpose**: User-facing feature for closing fiscal years

## Overview

This design covers the year-end closure feature that allows users to close fiscal years. When a year is closed, the system:

1. Calculates net P&L result and records it in equity
2. Creates opening balance transactions for the next year
3. Marks the year as closed
4. Provides audit trail

## Goals

1. Provide intuitive UI for closing years
2. Validate year is ready to be closed
3. Create year-end closure and opening balance transactions
4. Track closure status and history
5. Support retrospective closure (closing past years)

## Architecture

### Component Overview

```
Frontend (React)
├── YearEndClosureScreen.tsx - Main UI
├── YearClosureWizard.tsx - Step-by-step wizard
└── ClosedYearsTable.tsx - View closed years

Backend (Flask)
├── routes/year_end_routes.py - API endpoints
├── year_end_closure.py - Business logic
└── services/year_end_service.py - Core service

Database
├── mutaties - Transaction storage
├── year_closure_status - Closure tracking
└── rekeningschema - Account configuration
```

## Database Schema

### New Table: year_closure_status

```sql
CREATE TABLE year_closure_status (
  id INT AUTO_INCREMENT PRIMARY KEY,
  administration VARCHAR(50) NOT NULL,
  year INT NOT NULL,
  closed_date DATETIME NOT NULL,
  closed_by VARCHAR(255) NOT NULL,
  closure_transaction_number VARCHAR(50),
  opening_balance_transaction_number VARCHAR(50),
  notes TEXT,
  UNIQUE KEY unique_admin_year (administration, year),
  INDEX idx_administration (administration),
  INDEX idx_year (year),
  INDEX idx_closure_txn (closure_transaction_number),
  INDEX idx_opening_txn (opening_balance_transaction_number)
);
```

**Note**: Uses TransactionNumber (VARCHAR) instead of transaction IDs because:

- Opening balance transactions create MULTIPLE records (one per balance sheet account)
- All records share the same TransactionNumber (e.g., "OpeningBalance 2025")
- TransactionNumber can reference all related records

### Modified Table: rekeningschema

```sql
ALTER TABLE rekeningschema
ADD COLUMN parameters JSON;

-- Example data:
UPDATE rekeningschema
SET parameters = '{"role": "equity_result"}'
WHERE Reknum = '3080' AND administration = 'GoodwinSolutions';

UPDATE rekeningschema
SET parameters = '{"role": "pl_closing"}'
WHERE Reknum = '8099' AND administration = 'GoodwinSolutions';

UPDATE rekeningschema
SET parameters = '{"role": "interim_opening_balance"}'
WHERE Reknum = '2001' AND administration = 'GoodwinSolutions';
```

## Backend Design

### API Endpoints

```python
# backend/src/routes/year_end_routes.py

from flask import Blueprint, request, jsonify
from auth.cognito_utils import cognito_required
from auth.tenant_context import tenant_required
from year_end_closure import YearEndClosureService

year_end_bp = Blueprint('year_end', __name__)

@year_end_bp.route('/api/year-end/available-years', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_available_years(user_email, user_roles, tenant, user_tenants):
    """Get list of years that can be closed"""
    service = YearEndClosureService()
    years = service.get_available_years(tenant)
    return jsonify(years)

@year_end_bp.route('/api/year-end/validate', methods=['POST'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def validate_year(user_email, user_roles, tenant, user_tenants):
    """Validate if year is ready to be closed"""
    data = request.get_json()
    year = data.get('year')

    service = YearEndClosureService()
    validation = service.validate_year_closure(tenant, year)
    return jsonify(validation)

@year_end_bp.route('/api/year-end/close', methods=['POST'])
@cognito_required(required_permissions=['finance_write'])
@tenant_required()
def close_year(user_email, user_roles, tenant, user_tenants):
    """Close a fiscal year"""
    data = request.get_json()
    year = data.get('year')
    notes = data.get('notes', '')

    service = YearEndClosureService()
    result = service.close_year(tenant, year, user_email, notes)
    return jsonify(result)

@year_end_bp.route('/api/year-end/closed-years', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_closed_years(user_email, user_roles, tenant, user_tenants):
    """Get list of closed years"""
    service = YearEndClosureService()
    closed_years = service.get_closed_years(tenant)
    return jsonify(closed_years)

@year_end_bp.route('/api/year-end/status/<int:year>', methods=['GET'])
@cognito_required(required_permissions=['finance_read'])
@tenant_required()
def get_year_status(year, user_email, user_roles, tenant, user_tenants):
    """Get closure status for specific year"""
    service = YearEndClosureService()
    status = service.get_year_status(tenant, year)
    return jsonify(status)
```

### Core Service Class

```python
# backend/src/year_end_closure.py

from database import DatabaseManager
from datetime import datetime

class YearEndClosureService:
    def __init__(self, test_mode=False):
        self.db = DatabaseManager(test_mode=test_mode)

    def get_available_years(self, administration):
        """Get years that have transactions and are not closed"""
        query = """
            SELECT DISTINCT jaar as year
            FROM vw_mutaties
            WHERE administration = %s
            AND jaar IS NOT NULL
            AND jaar NOT IN (
                SELECT year
                FROM year_closure_status
                WHERE administration = %s
            )
            ORDER BY jaar DESC
        """
        return self.db.execute_query(query, [administration, administration])

    def validate_year_closure(self, administration, year):
        """Validate if year is ready to be closed"""
        validation = {
            'can_close': True,
            'errors': [],
            'warnings': [],
            'info': {}
        }

        # Check if already closed
        if self._is_year_closed(administration, year):
            validation['can_close'] = False
            validation['errors'].append(f"Year {year} is already closed")
            return validation

        # Check if previous year is closed (except for first year)
        first_year = self._get_first_year(administration)
        if year > first_year:
            if not self._is_year_closed(administration, year - 1):
                validation['can_close'] = False
                validation['errors'].append(
                    f"Previous year {year - 1} must be closed first"
                )

        # Check if required accounts are configured
        required_roles = ['equity_result', 'pl_closing', 'interim_opening_balance']
        for role in required_roles:
            account = self._get_account_by_role(administration, role)
            if not account:
                validation['can_close'] = False
                validation['errors'].append(
                    f"Required account role '{role}' not configured"
                )

        # Calculate net P&L result
        net_result = self._calculate_net_pl_result(administration, year)
        validation['info']['net_result'] = net_result
        validation['info']['net_result_formatted'] = f"€{net_result:,.2f}"

        # Count balance sheet accounts with non-zero balances
        balance_count = self._count_balance_sheet_accounts(administration, year)
        validation['info']['balance_sheet_accounts'] = balance_count

        # Optional warnings (don't prevent closure)
        if net_result == 0:
            validation['warnings'].append("Net P&L result is zero")

        return validation

    def close_year(self, administration, year, user_email, notes=''):
        """Close a fiscal year"""
        # Validate first
        validation = self.validate_year_closure(administration, year)
        if not validation['can_close']:
            raise Exception(f"Cannot close year: {', '.join(validation['errors'])}")

        conn = self.db.get_connection()
        cursor = conn.cursor()

        try:
            # Step 1: Create year-end closure transaction
            closure_transaction_id = self._create_closure_transaction(
                administration, year, cursor
            )

            # Step 2: Create opening balance transactions
            opening_transaction_ids = self._create_opening_balances(
                administration, year + 1, cursor
            )

            # Step 3: Record closure status
            self._record_closure_status(
                administration,
                year,
                user_email,
                closure_transaction_id,
                opening_transaction_ids,
                notes,
                cursor
            )

            conn.commit()

            return {
                'success': True,
                'year': year,
                'closure_transaction_id': closure_transaction_id,
                'opening_transaction_count': len(opening_transaction_ids),
                'message': f'Year {year} closed successfully'
            }

        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to close year {year}: {str(e)}")
        finally:
            cursor.close()
            conn.close()
```

    def _create_closure_transaction(self, administration, year, cursor):
        """Create year-end closure transaction (P&L to equity)"""
        # Get required accounts
        equity_account = self._get_account_by_role(administration, 'equity_result')
        pl_closing_account = self._get_account_by_role(administration, 'pl_closing')

        # Calculate net P&L result
        net_result = self._calculate_net_pl_result(administration, year)

        if net_result == 0:
            return None  # No transaction needed if result is zero

        # Determine debit and credit based on profit/loss
        if net_result > 0:
            # Profit: Debit P&L closing, Credit equity
            debet = pl_closing_account
            credit = equity_account
            amount = net_result
        else:
            # Loss: Debit equity, Credit P&L closing
            debet = equity_account
            credit = pl_closing_account
            amount = abs(net_result)

        # Insert transaction
        insert_query = """
            INSERT INTO mutaties (
                TransactionNumber,
                TransactionDate,
                TransactionDescription,
                TransactionAmount,
                Debet,
                Credit,
                ReferenceNumber,
                administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        transaction_number = f"YearClose {year}"
        transaction_date = f"{year}-12-31"
        description = f"Year-end closure {year} - {administration}"

        cursor.execute(insert_query, [
            transaction_number,
            transaction_date,
            description,
            amount,
            debet,
            credit,
            transaction_number,
            administration
        ])

        return cursor.lastrowid

    def _create_opening_balances(self, administration, year, cursor):
        """Create opening balance transactions for next year"""
        # Get interim account
        interim_account = self._get_account_by_role(
            administration, 'interim_opening_balance'
        )

        # Get ending balances from previous year
        ending_balances = self._get_ending_balances(administration, year - 1, cursor)

        if not ending_balances:
            return []

        transaction_number = f"OpeningBalance {year}"
        transaction_date = f"{year}-01-01"
        description = f"Opening balance for year {year} of Administration {administration}"

        insert_query = """
            INSERT INTO mutaties (
                TransactionNumber,
                TransactionDate,
                TransactionDescription,
                TransactionAmount,
                Debet,
                Credit,
                ReferenceNumber,
                administration
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        transaction_ids = []

        for balance_info in ending_balances:
            account = balance_info['account']
            balance = balance_info['balance']

            if balance > 0:
                debet = account
                credit = interim_account
                amount = balance
            else:
                debet = interim_account
                credit = account
                amount = abs(balance)

            cursor.execute(insert_query, [
                transaction_number,
                transaction_date,
                description,
                amount,
                debet,
                credit,
                transaction_number,
                administration
            ])

            transaction_ids.append(cursor.lastrowid)

        return transaction_ids

```

```

    def _record_closure_status(self, administration, year, user_email,
                               closure_transaction_id, opening_transaction_ids,
                               notes, cursor):
        """Record year closure in status table"""
        insert_query = """
            INSERT INTO year_closure_status (
                administration,
                year,
                closed_date,
                closed_by,
                closure_transaction_id,
                opening_balance_transaction_id,
                notes
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        # Use first opening balance transaction ID for reference
        opening_id = opening_transaction_ids[0] if opening_transaction_ids else None

        cursor.execute(insert_query, [
            administration,
            year,
            datetime.now(),
            user_email,
            closure_transaction_id,
            opening_id,
            notes
        ])

    def _calculate_net_pl_result(self, administration, year):
        """Calculate net P&L result for the year"""
        query = """
            SELECT COALESCE(SUM(Amount), 0) as net_result
            FROM vw_mutaties
            WHERE VW='Y'
            AND jaar = %s
            AND administration = %s
        """
        result = self.db.execute_query(query, [year, administration])
        return float(result[0]['net_result'])

    def _get_ending_balances(self, administration, year, cursor):
        """Get ending balances for all balance sheet accounts"""
        query = """
            SELECT
                Reknum as account,
                AccountName as account_name,
                SUM(Amount) as balance
            FROM vw_mutaties
            WHERE VW='N'
            AND TransactionDate <= %s
            AND administration = %s
            GROUP BY Reknum, AccountName
            HAVING SUM(Amount) <> 0
            ORDER BY Reknum
        """
        end_date = f"{year}-12-31"
        cursor.execute(query, [end_date, administration])

        balances = []
        for row in cursor.fetchall():
            balances.append({
                'account': row['account'],
                'account_name': row['account_name'],
                'balance': float(row['balance'])
            })
        return balances

    def _get_account_by_role(self, administration, role):
        """Get account code by parameter role"""
        query = """
            SELECT Reknum
            FROM rekeningschema
            WHERE administration = %s
            AND JSON_EXTRACT(parameters, '$.role') = %s
        """
        result = self.db.execute_query(query, [administration, role])
        return result[0]['Reknum'] if result else None

    def _is_year_closed(self, administration, year):
        """Check if year is already closed"""
        query = """
            SELECT COUNT(*) as count
            FROM year_closure_status
            WHERE administration = %s
            AND year = %s
        """
        result = self.db.execute_query(query, [administration, year])
        return result[0]['count'] > 0

    def _get_first_year(self, administration):
        """Get first year with transactions"""
        query = """
            SELECT MIN(jaar) as first_year
            FROM vw_mutaties
            WHERE administration = %s
            AND jaar IS NOT NULL
        """
        result = self.db.execute_query(query, [administration])
        return result[0]['first_year']

    def _count_balance_sheet_accounts(self, administration, year):
        """Count balance sheet accounts with non-zero balances"""
        query = """
            SELECT COUNT(DISTINCT Reknum) as count
            FROM vw_mutaties
            WHERE VW='N'
            AND TransactionDate <= %s
            AND administration = %s
            GROUP BY Reknum
            HAVING SUM(Amount) <> 0
        """
        end_date = f"{year}-12-31"
        result = self.db.execute_query(query, [end_date, administration])
        return len(result)

    def get_closed_years(self, administration):
        """Get list of closed years with details"""
        query = """
            SELECT
                year,
                closed_date,
                closed_by,
                notes
            FROM year_closure_status
            WHERE administration = %s
            ORDER BY year DESC
        """
        return self.db.execute_query(query, [administration])

    def get_year_status(self, administration, year):
        """Get detailed status for a specific year"""
        query = """
            SELECT *
            FROM year_closure_status
            WHERE administration = %s
            AND year = %s
        """
        result = self.db.execute_query(query, [administration, year])
        return result[0] if result else None

```

```

## Frontend Design

### Year-End Closure Screen

```typescript
// frontend/src/pages/YearEndClosure.tsx

import React, { useState, useEffect } from 'react';
import { Box, Button, Heading, useToast } from '@chakra-ui/react';
import YearClosureWizard from '../components/YearClosureWizard';
import ClosedYearsTable from '../components/ClosedYearsTable';

const YearEndClosure: React.FC = () => {
  const [availableYears, setAvailableYears] = useState<number[]>([]);
  const [closedYears, setClosedYears] = useState<any[]>([]);
  const [showWizard, setShowWizard] = useState(false);
  const toast = useToast();

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [yearsRes, closedRes] = await Promise.all([
        fetch('/api/year-end/available-years'),
        fetch('/api/year-end/closed-years')
      ]);

      const years = await yearsRes.json();
      const closed = await closedRes.json();

      setAvailableYears(years.map((y: any) => y.year));
      setClosedYears(closed);
    } catch (error) {
      toast({
        title: 'Error loading data',
        description: error.message,
        status: 'error'
      });
    }
  };

  return (
    <Box p={6}>
      <Heading mb={6}>Year-End Closure</Heading>

      {availableYears.length > 0 && (
        <Button
          colorScheme="blue"
          onClick={() => setShowWizard(true)}
          mb={6}
        >
          Close Fiscal Year
        </Button>
      )}

      {showWizard && (
        <YearClosureWizard
          availableYears={availableYears}
          onClose={() => {
            setShowWizard(false);
            loadData();
          }}
        />
      )}

      <ClosedYearsTable years={closedYears} />
    </Box>
  );
};

export default YearEndClosure;
```

### Year Closure Wizard

```typescript
// frontend/src/components/YearClosureWizard.tsx

import React, { useState } from 'react';
import {
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Select,
  Alert,
  AlertIcon,
  Text,
  VStack,
  HStack,
  Spinner,
  useToast
} from '@chakra-ui/react';

interface Props {
  availableYears: number[];
  onClose: () => void;
}

const YearClosureWizard: React.FC<Props> = ({ availableYears, onClose }) => {
  const [step, setStep] = useState(1);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [validation, setValidation] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [notes, setNotes] = useState('');
  const toast = useToast();

  const handleValidate = async () => {
    if (!selectedYear) return;

    setLoading(true);
    try {
      const response = await fetch('/api/year-end/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year: selectedYear })
      });

      const result = await response.json();
      setValidation(result);
      setStep(2);
    } catch (error) {
      toast({
        title: 'Validation failed',
        description: error.message,
        status: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = async () => {
    if (!selectedYear) return;

    setLoading(true);
    try {
      const response = await fetch('/api/year-end/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year: selectedYear, notes })
      });

      const result = await response.json();

      if (result.success) {
        toast({
          title: 'Year closed successfully',
          description: `Year ${selectedYear} has been closed`,
          status: 'success'
        });
        onClose();
      } else {
        throw new Error(result.message);
      }
    } catch (error) {
      toast({
        title: 'Failed to close year',
        description: error.message,
        status: 'error'
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} size="xl">
      <ModalOverlay />
      <ModalContent>
        <ModalHeader>
          Close Fiscal Year - Step {step} of 2
        </ModalHeader>

        <ModalBody>
          {step === 1 && (
            <VStack spacing={4} align="stretch">
              <Text>Select the year you want to close:</Text>
              <Select
                placeholder="Select year"
                value={selectedYear || ''}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
              >
                {availableYears.map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </Select>
            </VStack>
          )}

          {step === 2 && validation && (
            <VStack spacing={4} align="stretch">
              {validation.errors.length > 0 && (
                <Alert status="error">
                  <AlertIcon />
                  <VStack align="start" spacing={1}>
                    {validation.errors.map((error: string, i: number) => (
                      <Text key={i}>{error}</Text>
                    ))}
                  </VStack>
                </Alert>
              )}

              {validation.warnings.length > 0 && (
                <Alert status="warning">
                  <AlertIcon />
                  <VStack align="start" spacing={1}>
                    {validation.warnings.map((warning: string, i: number) => (
                      <Text key={i}>{warning}</Text>
                    ))}
                  </VStack>
                </Alert>
              )}

              {validation.can_close && (
                <>
                  <Alert status="success">
                    <AlertIcon />
                    Year {selectedYear} is ready to be closed
                  </Alert>

                  <VStack align="start" spacing={2}>
                    <Text fontWeight="bold">Summary:</Text>
                    <Text>Net P&L Result: {validation.info.net_result_formatted}</Text>
                    <Text>Balance Sheet Accounts: {validation.info.balance_sheet_accounts}</Text>
                  </VStack>

                  <Text fontSize="sm" color="gray.600">
                    Optional notes (e.g., reason for closing, special circumstances):
                  </Text>
                  <textarea
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    rows={3}
                    style={{ width: '100%', padding: '8px', border: '1px solid #ccc' }}
                  />
                </>
              )}
            </VStack>
          )}

          {loading && (
            <HStack justify="center" py={4}>
              <Spinner />
              <Text>Processing...</Text>
            </HStack>
          )}
        </ModalBody>

        <ModalFooter>
          <Button variant="ghost" onClick={onClose} mr={3}>
            Cancel
          </Button>

          {step === 1 && (
            <Button
              colorScheme="blue"
              onClick={handleValidate}
              isDisabled={!selectedYear || loading}
            >
              Next
            </Button>
          )}

          {step === 2 && validation?.can_close && (
            <Button
              colorScheme="red"
              onClick={handleClose}
              isDisabled={loading}
            >
              Close Year {selectedYear}
            </Button>
          )}
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default YearClosureWizard;
```

### Closed Years Table

```typescript
// frontend/src/components/ClosedYearsTable.tsx

import React from 'react';
import {
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Box,
  Heading,
  Badge
} from '@chakra-ui/react';

interface Props {
  years: any[];
}

const ClosedYearsTable: React.FC<Props> = ({ years }) => {
  if (years.length === 0) {
    return (
      <Box>
        <Heading size="md" mb={4}>Closed Years</Heading>
        <Box p={4} bg="gray.50" borderRadius="md">
          No years have been closed yet
        </Box>
      </Box>
    );
  }

  return (
    <Box>
      <Heading size="md" mb={4}>Closed Years</Heading>
      <Table variant="simple">
        <Thead>
          <Tr>
            <Th>Year</Th>
            <Th>Closed Date</Th>
            <Th>Closed By</Th>
            <Th>Notes</Th>
            <Th>Status</Th>
          </Tr>
        </Thead>
        <Tbody>
          {years.map((year) => (
            <Tr key={year.year}>
              <Td fontWeight="bold">{year.year}</Td>
              <Td>{new Date(year.closed_date).toLocaleDateString()}</Td>
              <Td>{year.closed_by}</Td>
              <Td>{year.notes || '-'}</Td>
              <Td>
                <Badge colorScheme="green">Closed</Badge>
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </Box>
  );
};

export default ClosedYearsTable;
```

## Testing Strategy

### Unit Tests

```python
# backend/tests/unit/test_year_end_closure.py

import pytest
from year_end_closure import YearEndClosureService

def test_calculate_net_pl_result():
    """Test net P&L calculation"""
    service = YearEndClosureService(test_mode=True)
    # Setup test data with known P&L transactions
    # Assert correct net result

def test_validate_year_closure_success():
    """Test validation passes for valid year"""
    service = YearEndClosureService(test_mode=True)
    # Setup valid year
    validation = service.validate_year_closure('test_tenant', 2024)
    assert validation['can_close'] == True

def test_validate_year_closure_already_closed():
    """Test validation fails for already closed year"""
    service = YearEndClosureService(test_mode=True)
    # Setup closed year
    validation = service.validate_year_closure('test_tenant', 2024)
    assert validation['can_close'] == False
    assert 'already closed' in validation['errors'][0]

def test_validate_year_closure_previous_not_closed():
    """Test validation fails if previous year not closed"""
    service = YearEndClosureService(test_mode=True)
    # Setup year 2024 without 2023 closed
    validation = service.validate_year_closure('test_tenant', 2024)
    assert validation['can_close'] == False
    assert 'Previous year' in validation['errors'][0]

def test_create_closure_transaction_profit():
    """Test closure transaction for profit"""
    service = YearEndClosureService(test_mode=True)
    # Setup profit scenario
    # Create closure transaction
    # Assert correct debit/credit

def test_create_closure_transaction_loss():
    """Test closure transaction for loss"""
    service = YearEndClosureService(test_mode=True)
    # Setup loss scenario
    # Create closure transaction
    # Assert correct debit/credit

def test_create_opening_balances():
    """Test opening balance creation"""
    service = YearEndClosureService(test_mode=True)
    # Setup ending balances
    # Create opening balances
    # Assert correct transactions created
```

### Integration Tests

```python
# backend/tests/integration/test_year_end_closure_integration.py

def test_full_year_closure():
    """Test complete year closure process"""
    service = YearEndClosureService(test_mode=True)
    # Setup complete year with transactions
    # Close year
    # Verify closure transaction created
    # Verify opening balances created
    # Verify status recorded

def test_year_closure_rollback_on_error():
    """Test rollback if closure fails"""
    service = YearEndClosureService(test_mode=True)
    # Setup scenario that will fail
    # Attempt to close year
    # Verify no transactions created
    # Verify status not recorded
```

### API Tests

```python
# backend/tests/api/test_year_end_routes.py

def test_get_available_years():
    """Test GET /api/year-end/available-years"""
    response = client.get('/api/year-end/available-years')
    assert response.status_code == 200

def test_validate_year():
    """Test POST /api/year-end/validate"""
    response = client.post('/api/year-end/validate', json={'year': 2024})
    assert response.status_code == 200
    assert 'can_close' in response.json

def test_close_year():
    """Test POST /api/year-end/close"""
    response = client.post('/api/year-end/close', json={'year': 2024})
    assert response.status_code == 200
    assert response.json['success'] == True

def test_close_year_unauthorized():
    """Test close year without permission"""
    # Remove finance_write permission
    response = client.post('/api/year-end/close', json={'year': 2024})
    assert response.status_code == 403
```

## Error Handling

### Backend Errors

```python
class YearEndClosureError(Exception):
    """Base exception for year-end closure errors"""
    pass

class YearAlreadyClosedError(YearEndClosureError):
    """Year is already closed"""
    pass

class PreviousYearNotClosedError(YearEndClosureError):
    """Previous year must be closed first"""
    pass

class ConfigurationError(YearEndClosureError):
    """Required configuration is missing"""
    pass
```

### Frontend Error Handling

- Display validation errors clearly
- Show user-friendly error messages
- Provide guidance on how to fix issues
- Log errors for debugging

## Performance Considerations

### Optimization Strategies

1. **Database Indexes**:
   - Index on `year_closure_status(administration, year)`
   - Index on `vw_mutaties(administration, jaar, VW)`
   - Index on `rekeningschema(administration, parameters)`

2. **Query Optimization**:
   - Use prepared statements
   - Minimize database round trips
   - Use transactions efficiently

3. **Caching**:
   - Cache account role lookups
   - Cache validation results (short TTL)

### Expected Performance

- Validation: < 2 seconds
- Year closure: < 5 seconds
- UI response: < 1 second

## Security Considerations

### Authentication & Authorization

- Require `finance_write` permission for closing years (Finance_CRUD role)
- Require `finance_read` permission for viewing and validation
- Validate tenant access
- Log all closure actions

### Data Integrity

- Use database transactions
- Validate all inputs
- Prevent SQL injection
- Ensure double-entry balance

### Audit Trail

- Log who closed the year
- Log when year was closed
- Log any notes provided
- Immutable audit records

## Related Files

- `requirements.md` - Overall requirements
- `design-migration.md` - Historical data migration design
- `backend/src/routes/year_end_routes.py` - API endpoints
- `backend/src/year_end_closure.py` - Business logic
- `frontend/src/pages/YearEndClosure.tsx` - Main UI
- `backend/tests/unit/test_year_end_closure.py` - Unit tests

## Code Organization Guidelines

### File Size Limits

**Target: 500 lines | Maximum: 1000 lines**

To maintain code quality and readability:

- **Target 500 lines**: Aim for this in new code
- **Maximum 1000 lines**: Absolute limit - files exceeding this require refactoring
- **500-1000 lines**: Acceptable for complex logic, but consider splitting

### Suggested File Structure

Split year-end closure logic across multiple focused files:

```
backend/src/
├── routes/
│   └── year_end_routes.py (~150 lines)
│       - API endpoint definitions
│       - Request/response handling
│
├── services/
│   ├── year_end_service.py (~400 lines)
│   │   - Core business logic
│   │   - Transaction creation
│   │   - Validation orchestration
│   │
│   └── year_end_validator.py (~300 lines)
│       - Validation rules
│       - Pre-closure checks
│       - Configuration validation
│
└── models/
    └── year_closure_status.py (~100 lines)
        - Database model
        - Query helpers
```

**Frontend structure**:

```
frontend/src/
├── pages/
│   └── YearEndClosure.tsx (~200 lines)
│       - Main page component
│       - Data loading
│
└── components/
    ├── YearClosureWizard.tsx (~300 lines)
    │   - Step-by-step wizard
    │   - Validation display
    │
    └── ClosedYearsTable.tsx (~150 lines)
        - Display closed years
        - Status indicators
```

### Benefits of This Structure

- **Maintainability**: Each file has a single, clear purpose
- **Testability**: Easier to write focused unit tests
- **Readability**: Developers can quickly find relevant code
- **Collaboration**: Multiple developers can work on different files
- **Reusability**: Services can be used by multiple routes

### When to Split Files

Split when:

- File approaches 500 lines
- Multiple distinct responsibilities exist
- Code becomes hard to navigate
- Testing becomes complex

Keep together when:

- Logic is tightly coupled
- Splitting would create circular dependencies
- File is under 500 lines and cohesive
