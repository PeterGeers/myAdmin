/**
 * Reusable account selector with searchable datalist and client-side validation.
 *
 * Renders an <Input> backed by a <datalist> of all accounts from rekeningschema.
 * Shows a red border and tooltip when the entered value doesn't match any account.
 *
 * Usage:
 *   <AccountSelect
 *     value={transaction.Debet}
 *     onChange={(val) => updateTransaction(id, 'Debet', val)}
 *     accounts={accounts}          // from useAccountLookup()
 *     size="sm"
 *   />
 */

import React, { useMemo } from 'react';
import { Input, InputProps, Tooltip } from '@chakra-ui/react';
import { AccountOption } from '../../hooks/useAccountLookup';

interface AccountSelectProps extends Omit<InputProps, 'onChange'> {
  value: string;
  onChange: (value: string) => void;
  accounts: AccountOption[];
  listId?: string;
}

const AccountSelect: React.FC<AccountSelectProps> = ({
  value,
  onChange,
  accounts,
  listId,
  ...inputProps
}) => {
  const id = listId || `account-list-${Math.random().toString(36).slice(2, 9)}`;

  const accountSet = useMemo(
    () => new Set(accounts.map((a) => a.Account.trim())),
    [accounts]
  );

  const isInvalid = value !== '' && accounts.length > 0 && !accountSet.has(value.trim());

  const options = useMemo(
    () =>
      accounts.map((a) => (
        <option key={a.Account} value={a.Account}>
          {a.Account} - {a.AccountName}
        </option>
      )),
    [accounts]
  );

  return (
    <>
      <Tooltip
        label={`Account "${value}" does not exist in the chart of accounts`}
        isOpen={isInvalid ? undefined : false}
        hasArrow
        bg="red.600"
        placement="top"
      >
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          list={id}
          autoComplete="off"
          isInvalid={isInvalid}
          borderColor={isInvalid ? 'red.400' : undefined}
          {...inputProps}
        />
      </Tooltip>
      <datalist id={id}>{options}</datalist>
    </>
  );
};

export default AccountSelect;
