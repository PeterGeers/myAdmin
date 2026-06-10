/**
 * ZZP Invoice Detail — full invoice view with InvoiceLineEditor, VAT summary, totals.
 * Editable when draft, read-only when sent/paid/overdue/credited/cancelled.
 * Reference: .kiro/specs/zzp-module/design.md §6.2, §4.3
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Flex, VStack, HStack, Text, Button, Input, Select, Textarea,
  Spinner, useToast, Divider, Table, Thead, Tbody, Tr, Th, Td,
  FormControl, FormLabel,
} from '@chakra-ui/react';
import { ViewIcon } from '@chakra-ui/icons';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { useFieldConfig } from '../hooks/useFieldConfig';
import { Invoice, InvoiceLine, InvoiceInput, VatSummaryLine, Product, Contact } from '../types/zzp';
import {
  getInvoice, createInvoice, updateInvoice, sendInvoice, createCreditNote,
  getInvoiceLedgerAccounts, getEmailPreview, getInvoicePreview,
} from '../services/zzpInvoiceService';
import { sendReminder } from '../services/debtorService';
import { getProducts } from '../services/productService';
import { getContacts } from '../services/contactService';
import { InvoiceLineEditor } from '../components/zzp/InvoiceLineEditor';
import { InvoiceStatusBadge } from '../components/zzp/InvoiceStatusBadge';
import { EmailPreviewPanel } from '../components/zzp/EmailPreviewPanel';
import { InvoicePreviewModal } from '../components/zzp/InvoicePreviewModal';

interface ZZPInvoiceDetailProps {
  invoiceId?: number | null;
  onClose: () => void;
  onSaved?: () => void;
}

const ZZPInvoiceDetail: React.FC<ZZPInvoiceDetailProps> = ({
  invoiceId, onClose, onSaved,
}) => {
  const { t } = useTypedTranslation('zzp');
  const toast = useToast();
  const { isVisible, isRequired, loading: configLoading } = useFieldConfig('invoices');

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sending, setSending] = useState(false);
  const [crediting, setCrediting] = useState(false);
  const [reminding, setReminding] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [ledgerAccounts, setLedgerAccounts] = useState<{ account_code: string; account_name: string }[]>([]);

  // Editable form state (draft mode)
  const [contactId, setContactId] = useState<number | string>('');
  const [invoiceDate, setInvoiceDate] = useState(new Date().toISOString().slice(0, 10));
  const [paymentTermsDays, setPaymentTermsDays] = useState(30);
  const [currency, setCurrency] = useState('EUR');
  const [exchangeRate, setExchangeRate] = useState(1);
  const [notes, setNotes] = useState('');
  const [revenueAccount, setRevenueAccount] = useState('');
  const [lines, setLines] = useState<Partial<InvoiceLine>[]>([]);

  // Email preview state
  const [emailPreview, setEmailPreview] = useState<{
    subject: string;
    html_body: string;
    recipient: string;
    bcc: string;
    attachment_filename: string;
  } | null>(null);
  const [emailPreviewOpen, setEmailPreviewOpen] = useState(false);
  const [loadingEmailPreview, setLoadingEmailPreview] = useState(false);

  // PDF preview state
  const [previewing, setPreviewing] = useState(false);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const previewAbortRef = useRef<AbortController | null>(null);
  const previewBlobUrlRef = useRef<string | null>(null);

  const isNew = !invoiceId;
  const isDraft = !invoice || invoice.status === 'draft';
  const isEditable = isNew || isDraft;

  const formatCurrency = (amount: number, cur = 'EUR') => {
    const code = (cur || 'EUR').trim().toUpperCase();
    // Only use typed code if it's a valid 3-letter ISO currency; otherwise fall back to EUR
    const safeCur = /^[A-Z]{3}$/.test(code) ? code : 'EUR';
    return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: safeCur }).format(amount);
  };

  const loadReferenceData = useCallback(async () => {
    try {
      const [prodResp, contResp, ledgerResp] = await Promise.all([
        getProducts(), getContacts(), getInvoiceLedgerAccounts(),
      ]);
      if (prodResp.success) setProducts(prodResp.data);
      if (contResp.success) setContacts(contResp.data);
      if (ledgerResp.success) {
        setLedgerAccounts(ledgerResp.data);
        // Default to first account for new invoices
        if (!invoiceId && ledgerResp.data.length > 0) {
          setRevenueAccount(ledgerResp.data[0].account_code);
        }
      }
    } catch {
      toast({ title: t('common.errorLoading', 'Error loading data'), status: 'error' });
    }
  }, [toast, t, invoiceId]);

  const loadInvoice = useCallback(async () => {
    if (!invoiceId) return;
    try {
      setLoading(true);
      const resp = await getInvoice(invoiceId);
      if (resp.success) {
        const inv: Invoice = resp.data;
        setInvoice(inv);
        setContactId(inv.contact?.id || '');
        setInvoiceDate(inv.invoice_date);
        setPaymentTermsDays(inv.payment_terms_days);
        setCurrency(inv.currency || 'EUR');
        setExchangeRate(inv.exchange_rate);
        setNotes(inv.notes || '');
        setRevenueAccount(inv.revenue_account || '');
        setLines(inv.lines || []);
      } else {
        toast({ title: resp.error || 'Error loading invoice', status: 'error' });
      }
    } catch {
      toast({ title: 'Error loading invoice', status: 'error' });
    } finally {
      setLoading(false);
    }
  }, [invoiceId, toast]);

  useEffect(() => { loadReferenceData(); }, [loadReferenceData]);
  useEffect(() => { loadInvoice(); }, [loadInvoice]);

  // Initialize a blank line for new invoices
  useEffect(() => {
    if (isNew && lines.length === 0) {
      setLines([{ description: '', quantity: 1, unit_price: 0, vat_code: 'high', line_total: 0 }]);
    }
  }, [isNew, lines.length]);

  // ── Live totals calculation ──────────────────────────────
  // Estimate VAT rates client-side for live preview.
  // Server recalculates exact rates on save using TaxRateService.
  const VAT_RATE_ESTIMATE: Record<string, number> = { high: 21, low: 9, zero: 0 };

  const liveLines = lines.map(l => {
    const qty = Number(l.quantity) || 0;
    const price = Number(l.unit_price) || 0;
    const lineTotal = Math.round(qty * price * 100) / 100;
    const rate = VAT_RATE_ESTIMATE[l.vat_code || 'high'] ?? 21;
    const vatAmount = Math.round(lineTotal * rate / 100 * 100) / 100;
    return { ...l, line_total: lineTotal, vat_amount: vatAmount, vat_rate: rate };
  });

  const liveSubtotal = liveLines.reduce((s, l) => s + (l.line_total || 0), 0);
  const liveVatTotal = liveLines.reduce((s, l) => s + (l.vat_amount || 0), 0);
  const liveGrandTotal = Math.round((liveSubtotal + liveVatTotal) * 100) / 100;

  // Use server values when available (saved invoice), live values when editing
  const displaySubtotal = isEditable ? liveSubtotal : (invoice?.subtotal ?? 0);
  const displayVatTotal = isEditable ? liveVatTotal : (invoice?.vat_total ?? 0);
  const displayGrandTotal = isEditable ? liveGrandTotal : (invoice?.grand_total ?? 0);
  const displayVatSummary: VatSummaryLine[] = isEditable
    ? Object.values(
        liveLines.reduce((acc, l) => {
          const code = l.vat_code || 'high';
          if (!acc[code]) acc[code] = { vat_code: code, vat_rate: l.vat_rate || 0, base_amount: 0, vat_amount: 0 };
          acc[code].base_amount += l.line_total || 0;
          acc[code].vat_amount += l.vat_amount || 0;
          return acc;
        }, {} as Record<string, VatSummaryLine>)
      )
    : (invoice?.vat_summary || []);

  const handleSave = async () => {
    if (!contactId) {
      toast({ title: t('invoices.contactRequired', 'Contact is required'), status: 'warning' });
      return;
    }
    if (lines.length === 0 || lines.every(l => !l.description)) {
      toast({ title: t('invoices.linesRequired', 'At least one line item is required'), status: 'warning' });
      return;
    }

    try {
      setSaving(true);
      const payload: InvoiceInput = {
        contact_id: Number(contactId),
        invoice_date: invoiceDate,
        payment_terms_days: paymentTermsDays,
        currency,
        exchange_rate: exchangeRate,
        revenue_account: revenueAccount || undefined,
        notes: notes || undefined,
        lines: lines.map((l, idx) => ({
          product_id: l.product_id || undefined,
          description: l.description || '',
          quantity: Number(l.quantity) || 0,
          unit_price: Number(l.unit_price) || 0,
          vat_code: l.vat_code || 'high',
          sort_order: idx,
        })),
      };

      const resp = isNew
        ? await createInvoice(payload)
        : await updateInvoice(invoiceId!, payload);

      if (resp.success) {
        toast({ title: isNew ? t('invoices.created', 'Invoice created') : t('invoices.updated', 'Invoice updated'), status: 'success' });
        onSaved?.();
        onClose();
      } else {
        toast({ title: resp.error || 'Error saving invoice', status: 'error' });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error saving invoice';
      toast({ title: message || 'Error saving invoice', status: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleSend = async () => {
    setEmailPreviewOpen(false);
    if (!invoice?.id) return;
    try {
      setSending(true);
      const resp = await sendInvoice(invoice.id, { send_email: true });
      if (resp.success) {
        toast({ title: t('invoices.sent', 'Invoice sent'), status: 'success' });
        if (resp.warning) {
          toast({ title: resp.warning, status: 'warning', duration: 9000, isClosable: true });
        }
        onSaved?.();
        await loadInvoice();
      } else {
        toast({ title: resp.error || 'Error sending invoice', status: 'error' });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error sending invoice';
      toast({ title: message || 'Error sending invoice', status: 'error' });
    } finally {
      setSending(false);
    }
  };

  const handleSendInvoice = async () => {
    if (!invoice?.id) return;
    try {
      setLoadingEmailPreview(true);
      const resp = await getEmailPreview(invoice.id);
      if (resp.success && resp.data) {
        setEmailPreview(resp.data);
        setEmailPreviewOpen(true);
      } else {
        const errorMsg = resp.error || t('invoices.email.sendError', 'Failed to send invoice');
        // Check for missing email error
        if (errorMsg.toLowerCase().includes('email') && errorMsg.toLowerCase().includes('missing')) {
          toast({ title: t('invoices.email.missingEmail', 'Contact has no email address'), status: 'warning' });
        } else {
          toast({ title: errorMsg, status: 'error' });
        }
      }
    } catch (err: unknown) {
      const errorMsg = (err instanceof Error ? err.message : null) || t('invoices.email.sendError', 'Failed to send invoice');
      if (errorMsg.toLowerCase().includes('email') && errorMsg.toLowerCase().includes('missing')) {
        toast({ title: t('invoices.email.missingEmail', 'Contact has no email address'), status: 'warning' });
      } else {
        toast({ title: errorMsg, status: 'error' });
      }
    } finally {
      setLoadingEmailPreview(false);
    }
  };

  const handleCreditNote = async () => {
    if (!invoice?.id) return;
    try {
      setCrediting(true);
      const resp = await createCreditNote(invoice.id);
      if (resp.success) {
        toast({ title: t('invoices.creditNoteCreated', 'Credit note created'), status: 'success' });
        onSaved?.();
        onClose();
      } else {
        toast({ title: resp.error || 'Error creating credit note', status: 'error' });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error creating credit note';
      toast({ title: message || 'Error creating credit note', status: 'error' });
    } finally {
      setCrediting(false);
    }
  };

  const handleSendReminder = async () => {
    if (!invoice?.id) return;
    try {
      setReminding(true);
      const resp = await sendReminder(invoice.id);
      if (resp.success) {
        toast({ title: t('debtors.reminderSent', 'Reminder sent'), status: 'success' });
        onSaved?.();
        await loadInvoice();
      } else {
        toast({ title: resp.error || 'Error sending reminder', status: 'error' });
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error sending reminder';
      toast({ title: message || 'Error sending reminder', status: 'error' });
    } finally {
      setReminding(false);
    }
  };

  // ── PDF Preview logic ──────────────────────────────
  // Determine if form has unsaved changes by comparing current state to loaded invoice
  const isDirty = (() => {
    if (isNew) return true; // New invoices are always "dirty"
    if (!invoice) return false;
    if (String(contactId) !== String(invoice.contact?.id || '')) return true;
    if (invoiceDate !== invoice.invoice_date) return true;
    if (paymentTermsDays !== invoice.payment_terms_days) return true;
    if (currency !== invoice.currency) return true;
    if (notes !== (invoice.notes || '')) return true;
    if (revenueAccount !== (invoice.revenue_account || '')) return true;
    // Simple line count check — detailed line comparison is expensive
    if (lines.length !== (invoice.lines || []).length) return true;
    return false;
  })();

  /** Save the invoice without closing the form. Returns true on success. */
  const saveForPreview = async (): Promise<boolean> => {
    if (!contactId) {
      toast({ title: t('invoices.contactRequired', 'Contact is required'), status: 'warning' });
      return false;
    }
    if (lines.length === 0 || lines.every(l => !l.description)) {
      toast({ title: t('invoices.linesRequired', 'At least one line item is required'), status: 'warning' });
      return false;
    }

    try {
      setSaving(true);
      const payload: InvoiceInput = {
        contact_id: Number(contactId),
        invoice_date: invoiceDate,
        payment_terms_days: paymentTermsDays,
        currency,
        exchange_rate: exchangeRate,
        revenue_account: revenueAccount || undefined,
        notes: notes || undefined,
        lines: lines.map((l, idx) => ({
          product_id: l.product_id || undefined,
          description: l.description || '',
          quantity: Number(l.quantity) || 0,
          unit_price: Number(l.unit_price) || 0,
          vat_code: l.vat_code || 'high',
          sort_order: idx,
        })),
      };

      const resp = isNew
        ? await createInvoice(payload)
        : await updateInvoice(invoiceId!, payload);

      if (resp.success) {
        // Reload invoice to sync state without closing
        if (resp.data) {
          const inv: Invoice = resp.data;
          setInvoice(inv);
          setContactId(inv.contact?.id || '');
          setInvoiceDate(inv.invoice_date);
          setPaymentTermsDays(inv.payment_terms_days);
          setCurrency(inv.currency || 'EUR');
          setExchangeRate(inv.exchange_rate);
          setNotes(inv.notes || '');
          setRevenueAccount(inv.revenue_account || '');
          setLines(inv.lines || []);
        }
        onSaved?.();
        return true;
      } else {
        toast({ title: resp.error || 'Error saving invoice', status: 'error' });
        return false;
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Error saving invoice';
      toast({ title: message || 'Error saving invoice', status: 'error' });
      return false;
    } finally {
      setSaving(false);
    }
  };

  const handlePreview = async () => {
    if (!invoice?.id && !isNew) return;

    // If form has unsaved changes, save first
    if (isDirty) {
      const saved = await saveForPreview();
      if (!saved) return;
    }

    const currentInvoiceId = invoice?.id || invoiceId;
    if (!currentInvoiceId) return;

    // Set up AbortController with 30s timeout
    const controller = new AbortController();
    previewAbortRef.current = controller;
    const timeoutId = setTimeout(() => {
      controller.abort();
    }, 30_000);

    try {
      setPreviewing(true);
      const blob = await getInvoicePreview(currentInvoiceId, { signal: controller.signal });

      // Create blob URL and open modal
      const url = URL.createObjectURL(blob);
      previewBlobUrlRef.current = url;
      setPreviewBlobUrl(url);
      setPreviewModalOpen(true);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        toast({
          title: t('invoices.preview.timeout', 'Preview request timed out'),
          status: 'error',
        });
      } else {
        const message = err instanceof Error ? err.message : t('invoices.preview.error', 'Preview could not be generated');
        toast({
          title: message || t('invoices.preview.error', 'Preview could not be generated'),
          status: 'error',
        });
      }
    } finally {
      clearTimeout(timeoutId);
      setPreviewing(false);
      previewAbortRef.current = null;
    }
  };

  const handlePreviewClose = () => {
    setPreviewModalOpen(false);
    // Revoke blob URL on modal close
    if (previewBlobUrlRef.current) {
      URL.revokeObjectURL(previewBlobUrlRef.current);
      previewBlobUrlRef.current = null;
      setPreviewBlobUrl(null);
    }
  };

  // Cleanup on unmount: abort pending request and revoke blob URL
  useEffect(() => {
    return () => {
      if (previewAbortRef.current) {
        previewAbortRef.current.abort();
        previewAbortRef.current = null;
      }
      if (previewBlobUrlRef.current) {
        URL.revokeObjectURL(previewBlobUrlRef.current);
        previewBlobUrlRef.current = null;
      }
    };
  }, []);

  if (loading || configLoading) {
    return (
      <Box p={6} textAlign="center">
        <Spinner color="white" size="lg" />
      </Box>
    );
  }

  return (
    <Box p={4}>
      {/* Header: invoice number + status + actions */}
      <Flex wrap="wrap" justify="space-between" align="center" mb={4} gap={2}>
        <HStack spacing={3}>
          <Text fontSize="lg" fontWeight="bold" color="white">
            {invoice ? invoice.invoice_number : t('invoices.newInvoice', 'New Invoice')}
          </Text>
          {invoice && <InvoiceStatusBadge status={invoice.status} />}
          {invoice?.invoice_type === 'credit_note' && (
            <Text fontSize="sm" color="purple.300">({t('invoices.creditNote', 'Credit Note')})</Text>
          )}
        </HStack>
        <HStack spacing={2}>
          {isEditable && (
            <Button colorScheme="orange" size="sm" onClick={handleSave}
              isLoading={saving}>
              {t('common.save', 'Save')}
            </Button>
          )}
          {invoice && isDraft && (
            <Button colorScheme="blue" size="sm" onClick={handleSendInvoice}
              isLoading={sending || loadingEmailPreview} isDisabled={saving}>
              {t('invoices.send', 'Send')}
            </Button>
          )}
          {invoice && invoice.status === 'draft' && (
            <Button
              leftIcon={<ViewIcon />}
              size="sm"
              variant="outline"
              colorScheme="teal"
              onClick={handlePreview}
              isLoading={previewing}
              loadingText={t('invoices.preview.loading', 'Generating preview...')}
              isDisabled={previewing || saving}
            >
              {t('invoices.preview.button', 'Preview PDF')}
            </Button>
          )}
          {invoice && invoice.status === 'sent' && invoice.invoice_type !== 'credit_note' && (
            <Button colorScheme="purple" size="sm" variant="outline"
              onClick={handleCreditNote} isLoading={crediting}>
              {t('invoices.createCreditNote', 'Credit Note')}
            </Button>
          )}
          {invoice && (invoice.status === 'sent' || invoice.status === 'overdue') && (
            <Button colorScheme="red" size="sm" variant="outline"
              onClick={handleSendReminder} isLoading={reminding}>
              {t('debtors.sendReminder', 'Send Reminder')}
            </Button>
          )}
          <Button variant="ghost" size="sm" color="gray.400" onClick={onClose}>
            {t('common.cancel', 'Cancel')}
          </Button>
        </HStack>
      </Flex>

      <Divider borderColor="gray.600" mb={4} />

      {/* Invoice header fields */}
      <Flex wrap="wrap" gap={4} mb={4}>
        {/* Contact */}
        <FormControl w={{ base: '100%', md: '280px' }} isRequired>
          <FormLabel color="gray.300" fontSize="sm">{t('invoices.contact', 'Contact')}</FormLabel>
          {isEditable ? (
            <Select size="sm" bg="gray.700" color="white" borderColor="gray.600"
              value={contactId} onChange={e => setContactId(e.target.value)}
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
              value={invoiceDate} onChange={e => setInvoiceDate(e.target.value)} />
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
                value={paymentTermsDays} onChange={e => setPaymentTermsDays(Number(e.target.value))} />
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
                value={currency} onChange={e => setCurrency(e.target.value)} />
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
                onChange={e => setExchangeRate(parseFloat(e.target.value))} />
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
                onChange={e => setRevenueAccount(e.target.value)}
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
              rows={2} value={notes} onChange={e => setNotes(e.target.value)} />
          ) : (
            invoice?.notes && <Text color="gray.300" fontSize="sm">{invoice.notes}</Text>
          )}
        </FormControl>
      )}

      <Divider borderColor="gray.600" mb={4} />

      {/* Line items */}
      <Text fontSize="sm" fontWeight="bold" color="gray.300" mb={2}>
        {t('invoices.lineItems', 'Line Items')}
      </Text>
      <Box overflowX="auto" mb={4}>
        <InvoiceLineEditor
          lines={lines}
          products={products}
          readOnly={!isEditable}
          onChange={setLines}
        />
      </Box>

      <Divider borderColor="gray.600" mb={4} />

      {/* VAT summary + totals */}
      <Flex wrap="wrap" gap={6} justify="flex-end">
        {/* VAT breakdown */}
        {(displayVatSummary.length > 0 || !isNew) && (
          <Box minW="280px">
            <Text fontSize="sm" fontWeight="bold" color="gray.300" mb={2}>
              {t('invoices.vatSummary', 'VAT Summary')}
            </Text>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="gray.400">{t('invoices.vatCode', 'VAT Code')}</Th>
                  <Th color="gray.400" isNumeric>{t('invoices.vatRate', 'Rate')}</Th>
                  <Th color="gray.400" isNumeric>{t('invoices.baseAmount', 'Base')}</Th>
                  <Th color="gray.400" isNumeric>{t('invoices.vatAmount', 'VAT')}</Th>
                </Tr>
              </Thead>
              <Tbody>
                {displayVatSummary.map((vs, idx) => (
                  <Tr key={idx}>
                    <Td color="white" fontSize="sm">{vs.vat_code}</Td>
                    <Td color="white" fontSize="sm" isNumeric>{vs.vat_rate}%</Td>
                    <Td color="white" fontSize="sm" isNumeric>{formatCurrency(vs.base_amount, currency)}</Td>
                    <Td color="white" fontSize="sm" isNumeric>{formatCurrency(vs.vat_amount, currency)}</Td>
                  </Tr>
                ))}
                {displayVatSummary.length === 0 && (
                  <Tr><Td colSpan={4}><Text color="gray.500" fontSize="sm">—</Text></Td></Tr>
                )}
              </Tbody>
            </Table>
          </Box>
        )}

        {/* Totals */}
        <VStack align="flex-end" spacing={1} minW="200px">
          <HStack justify="space-between" w="full">
            <Text color="gray.400" fontSize="sm">{t('invoices.subtotal', 'Subtotal')}</Text>
            <Text color="white" fontSize="sm" fontWeight="medium">
              {formatCurrency(displaySubtotal, currency)}
            </Text>
          </HStack>
          <HStack justify="space-between" w="full">
            <Text color="gray.400" fontSize="sm">{t('invoices.vatTotal', 'VAT')}</Text>
            <Text color="white" fontSize="sm" fontWeight="medium">
              {formatCurrency(displayVatTotal, currency)}
            </Text>
          </HStack>
          <Divider borderColor="gray.500" />
          <HStack justify="space-between" w="full">
            <Text color="gray.300" fontSize="md" fontWeight="bold">{t('invoices.grandTotal', 'Total')}</Text>
            <Text color="orange.300" fontSize="md" fontWeight="bold">
              {formatCurrency(displayGrandTotal, currency)}
            </Text>
          </HStack>
        </VStack>
      </Flex>

      {/* Sent info */}
      {invoice?.sent_at && (
        <Text color="gray.500" fontSize="xs" mt={4}>
          {t('invoices.sentAt', 'Sent')}: {new Date(invoice.sent_at).toLocaleString('nl-NL')}
        </Text>
      )}

      {/* Email preview panel (replaces old send confirmation dialog) */}
      <EmailPreviewPanel
        isOpen={emailPreviewOpen}
        onClose={() => setEmailPreviewOpen(false)}
        onConfirmSend={handleSend}
        emailPreview={emailPreview}
        isSending={sending}
      />

      {/* PDF Preview modal */}
      <InvoicePreviewModal
        isOpen={previewModalOpen}
        onClose={handlePreviewClose}
        pdfBlobUrl={previewBlobUrl}
        invoiceNumber={invoice?.invoice_number || ''}
      />
    </Box>
  );
};

export default ZZPInvoiceDetail;
