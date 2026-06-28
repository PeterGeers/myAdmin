/**
 * InvoiceHeaderFields — form fields for invoice metadata (contact, date, terms, currency, etc.)
 * Extracted from ZZPInvoiceDetail to reduce file size.
 */

import React from 'react';
import {
  Flex, Text, Input, Select, Textarea,
  FormControl, FormLabel,
} from '@chakra-ui/react';
import { Invoice, Contact } from '../../types/zzp';

export interface InvoiceHeaderFieldsProps {
  // Form state
  contactId: number | string;
  invoiceDate: string;
  paymentTermsDays: number;
  currency: string;
  exchangeRate: number;
  notes: string;
  revenueAccount: string;
  // Reference data
  contacts: Contact[];
  ledgerAccounts: { account_code: string; account_name: string }[];
  // Display state
  invoice: Invoice | null;
  isEditable: boolean;
  isDraft: boolean;
  // Field config
  isVisible: (field: string) => boolean;
  isRequired: (field: string) => boolean;
  // Handlers
  onContactIdChange: (value: string) => void;
  onInvoiceDateChange: (value: string) => void;
  onPaymentTermsDaysChange: (value: number) => void;
  onCurrencyChange: (value: string) => void;
  onExchangeRateChange: (value: number) => void;
  onNotesChange: (value: string) => void;
  onRevenueAccountChange: (value: string) => void;
  // i18n
  t: (key: string, fallback?: string) => string;
}

export const InvoiceHeaderFields: React.FC<InvoiceHeaderFieldsProps> = ({
  contactId, invoiceDate, paymentTermsDays, currency, exchangeRate, notes, revenueAccount,
  contacts, ledgerAccounts, invoice, isEditable, isDraft,
  isVisible, isRequired,
  onContactIdChange, onInvoiceDateChange, onPaymentTermsDaysChange,
  onCurrencyChange, onExchangeRateChange, onNotesChange, onRevenueAccountChange,
  t,
}) => {
  return (
    <>
      <Flex wrap="wrap" gap={4} mb={4}>
        {/* Contact */}
        <FormControl w={{ base: '100%', md: '280px' }} isRequired>
          <FormLabel color="gray.300" fontSize="sm">{t('invoices.contact', 'Contact')}</FormLabel>
          {isEditable ? (
            <Select size="sm" bg="gray.700" color="white" borderColor="gray.600"
              value={contactId} onChange={e => onContactIdChange(e.target.value)}
              placeholder="—">
              {contacts.map(c => (
                <option key={c.id} value={c.id}>{c.company_name} ({c.client_id})</option>
              ))}
            </Select>
          ) : (
            <Text color="white" fontSize="sm">
              {invoice?.contact?.company_name} ({invoice?.contact?.client_id})
            </Text>
          )}
        </FormControl>

        {/* Invoice date */}
        <FormControl w={{ base: '100%', md: '180px' }} isRequired>
          <FormLabel color="gray.300" fontSize="sm">{t('invoices.invoiceDate', 'Invoice Date')}</FormLabel>
          {isEditable ? (
            <Input type="date" size="sm" bg="gray.700" color="white" borderColor="gray.600"
              value={invoiceDate} onChange={e => onInvoiceDateChange(e.target.value)} />
          ) : (
            <Text color="white" fontSize="sm">{invoice?.invoice_date}</Text>
          )}
        </FormControl>

        {/* Payment terms */}
        {isVisible('payment_terms_days') && (
          <FormControl w={{ base: '100%', md: '140px' }} isRequired={isRequired('payment_terms_days')}>
            <FormLabel color="gray.300" fontSize="sm">{t('invoices.paymentTerms', 'Payment Terms')}</FormLabel>
            {isEditable ? (
              <Input type="number" size="sm" bg="gray.700" color="white" borderColor="gray.600"
                value={paymentTermsDays} onChange={e => onPaymentTermsDaysChange(Number(e.target.value))} />
            ) : (
              <Text color="white" fontSize="sm">{invoice?.payment_terms_days} {t('invoices.days', 'days')}</Text>
            )}
          </FormControl>
        )}

        {/* Due date (read-only, calculated) */}
        {invoice?.due_date && (
          <FormControl w={{ base: '100%', md: '180px' }}>
            <FormLabel color="gray.300" fontSize="sm">{t('invoices.dueDate', 'Due Date')}</FormLabel>
            <Text color="white" fontSize="sm">{invoice.due_date}</Text>
          </FormControl>
        )}

        {/* Currency */}
        {isVisible('currency') && (
          <FormControl w={{ base: '100%', md: '120px' }}>
            <FormLabel color="gray.300" fontSize="sm">{t('invoices.currency', 'Currency')}</FormLabel>
            {isEditable ? (
              <Input size="sm" bg="gray.700" color="white" borderColor="gray.600"
                value={currency} onChange={e => onCurrencyChange(e.target.value)} />
            ) : (
              <Text color="white" fontSize="sm">{invoice?.currency}</Text>
            )}
          </FormControl>
        )}

        {/* Exchange rate — only shown for non-EUR */}
        {isVisible('exchange_rate') && currency !== 'EUR' && (
          <FormControl w={{ base: '100%', md: '140px' }}>
            <FormLabel color="gray.300" fontSize="sm">{t('invoices.exchangeRate', 'Exchange Rate')}</FormLabel>
            {isEditable ? (
              <Input type="number" step="0.000001" size="sm" bg="gray.700" color="white"
                borderColor="gray.600" value={exchangeRate}
                onChange={e => onExchangeRateChange(parseFloat(e.target.value))} />
            ) : (
              <Text color="white" fontSize="sm">{invoice?.exchange_rate}</Text>
            )}
          </FormControl>
        )}

        {/* Revenue account */}
        {ledgerAccounts.length > 0 && (
          <FormControl w={{ base: '100%', md: '280px' }}>
            <FormLabel color="gray.300" fontSize="sm">{t('invoices.revenueAccount', 'Revenue Account')}</FormLabel>
            {isEditable ? (
              <Select size="sm" bg="gray.700" color="white" borderColor="gray.600"
                value={revenueAccount}
                onChange={e => onRevenueAccountChange(e.target.value)}
                isDisabled={!isDraft}>
                {ledgerAccounts.map(a => (
                  <option key={a.account_code} value={a.account_code}>
                    {a.account_code} - {a.account_name}
                  </option>
                ))}
              </Select>
            ) : (
              <Text color="white" fontSize="sm">
                {revenueAccount ? `${revenueAccount} - ${ledgerAccounts.find(a => a.account_code === revenueAccount)?.account_name || ''}` : '—'}
              </Text>
            )}
          </FormControl>
        )}
      </Flex>

      {/* Notes */}
      {isVisible('notes') && (
        <FormControl mb={4}>
          <FormLabel color="gray.300" fontSize="sm">{t('invoices.notes', 'Notes')}</FormLabel>
          {isEditable ? (
            <Textarea size="sm" bg="gray.700" color="white" borderColor="gray.600"
              rows={2} value={notes} onChange={e => onNotesChange(e.target.value)} />
          ) : (
            invoice?.notes && <Text color="gray.300" fontSize="sm">{invoice.notes}</Text>
          )}
        </FormControl>
      )}
    </>
  );
};
