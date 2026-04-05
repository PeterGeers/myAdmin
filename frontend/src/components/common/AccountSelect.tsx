/**
 * Reusable account selector with searchable datalist.
 *
 * Renders an <Input> backed by a <datalist> of all accounts from rekeningschema.
 * User can type to filter by account number or name. Compact enough for table cells.
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
import { Input, InputProps } from '@chakra-ui/react';
import { AccountOption } from '../../hooks/useAccountLookup';

interface AccountSelectProps extends Omit<InputProps, 'onChange'> {
  /** Current account number */
  value: string;
  /** Called with the new account number string */
  onChange: (value: string) => void;
  /** Account list from useAccountLookup() */
  accounts: AccountOption[];
  /** Unique id for the datalist (auto-generated if not provided) */
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
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        list={id}
        autoComplete="off"
        {...inputProps}
      />
      <datalist id={id}>{options}</datalist>
    </>
  );
};

export default AccountSelect;
