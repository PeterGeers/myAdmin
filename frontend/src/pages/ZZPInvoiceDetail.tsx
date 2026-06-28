/**
 * ZZP Invoice Detail — full invoice view with InvoiceLineEditor, VAT summary, totals.
 * Editable when draft, read-only when sent/paid/overdue/credited/cancelled.
 * Reference: .kiro/specs/zzp-module/design.md §6.2, §4.3
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Box, Text, Spinner, useToast, Divider,
} from '@chakra-ui/react';
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
import { EmailPreviewPanel } from '../components/zzp/EmailPreviewPanel';
import { InvoicePreviewModal } from '../components/zzp/InvoicePreviewModal';
import { InvoiceActionBar } from '../components/zzp/InvoiceActionBar';
import { InvoiceHeaderFields } from '../components/zzp/InvoiceHeaderFields';
import { InvoiceVatTotals } from '../components/zzp/InvoiceVatTotals';

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

  // ── Build invoice payload (shared by save + saveForPreview) ──
  const buildPayload = (): InvoiceInput => ({
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
  });

  const validateForm = (): boolean => {
    if (!contactId) {
      toast({ title: t('invoices.contactRequired', 'Contact is required'), status: 'warning' });
      return false;
    }
    if (lines.length === 0 || lines.every(l => !l.description)) {
      toast({ title: t('invoices.linesRequired', 'At least one line item is required'), status: 'warning' });
      return false;
    }
    return true;
  };

  const handleSave = async () => {
    if (!validateForm()) return;
    try {
      setSaving(true);
      const resp = isNew
        ? await createInvoice(buildPayload())
        : await updateInvoice(invoiceId!, buildPayload());

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
  const isDirty = (() => {
    if (isNew) return true;
    if (!invoice) return false;
    if (String(contactId) !== String(invoice.contact?.id || '')) return true;
    if (invoiceDate !== invoice.invoice_date) return true;
    if (paymentTermsDays !== invoice.payment_terms_days) return true;
    if (currency !== invoice.currency) return true;
    if (notes !== (invoice.notes || '')) return true;
    if (revenueAccount !== (invoice.revenue_account || '')) return true;
    if (lines.length !== (invoice.lines || []).length) return true;
    return false;
  })();

  const saveForPreview = async (): Promise<boolean> => {
    if (!validateForm()) return false;
    try {
      setSaving(true);
      const resp = isNew
        ? await createInvoice(buildPayload())
        : await updateInvoice(invoiceId!, buildPayload());

      if (resp.success) {
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
    if (isDirty) {
      const saved = await saveForPreview();
      if (!saved) return;
    }

    const currentInvoiceId = invoice?.id || invoiceId;
    if (!currentInvoiceId) return;

    const controller = new AbortController();
    previewAbortRef.current = controller;
    const timeoutId = setTimeout(() => { controller.abort(); }, 30_000);

    try {
      setPreviewing(true);
      const blob = await getInvoicePreview(currentInvoiceId, { signal: controller.signal });
      const url = URL.createObjectURL(blob);
      previewBlobUrlRef.current = url;
      setPreviewBlobUrl(url);
      setPreviewModalOpen(true);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        toast({ title: t('invoices.preview.timeout', 'Preview request timed out'), status: 'error' });
      } else {
        const message = err instanceof Error ? err.message : t('invoices.preview.error', 'Preview could not be generated');
        toast({ title: message || t('invoices.preview.error', 'Preview could not be generated'), status: 'error' });
      }
    } finally {
      clearTimeout(timeoutId);
      setPreviewing(false);
      previewAbortRef.current = null;
    }
  };

  const handlePreviewClose = () => {
    setPreviewModalOpen(false);
    if (previewBlobUrlRef.current) {
      URL.revokeObjectURL(previewBlobUrlRef.current);
      previewBlobUrlRef.current = null;
      setPreviewBlobUrl(null);
    }
  };

  // Cleanup on unmount
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
      <InvoiceActionBar
        invoice={invoice}
        isEditable={isEditable}
        isDraft={isDraft}
        saving={saving}
        sending={sending}
        loadingEmailPreview={loadingEmailPreview}
        previewing={previewing}
        crediting={crediting}
        reminding={reminding}
        onSave={handleSave}
        onSendInvoice={handleSendInvoice}
        onPreview={handlePreview}
        onCreditNote={handleCreditNote}
        onSendReminder={handleSendReminder}
        onClose={onClose}
        t={t}
      />

      <Divider borderColor="gray.600" mb={4} />

      {/* Invoice header fields */}
      <InvoiceHeaderFields
        contactId={contactId}
        invoiceDate={invoiceDate}
        paymentTermsDays={paymentTermsDays}
        currency={currency}
        exchangeRate={exchangeRate}
        notes={notes}
        revenueAccount={revenueAccount}
        contacts={contacts}
        ledgerAccounts={ledgerAccounts}
        invoice={invoice}
        isEditable={isEditable}
        isDraft={isDraft}
        isVisible={isVisible}
        isRequired={isRequired}
        onContactIdChange={v => setContactId(v)}
        onInvoiceDateChange={setInvoiceDate}
        onPaymentTermsDaysChange={setPaymentTermsDays}
        onCurrencyChange={setCurrency}
        onExchangeRateChange={setExchangeRate}
        onNotesChange={setNotes}
        onRevenueAccountChange={setRevenueAccount}
        t={t}
      />

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
      <InvoiceVatTotals
        displayVatSummary={displayVatSummary}
        displaySubtotal={displaySubtotal}
        displayVatTotal={displayVatTotal}
        displayGrandTotal={displayGrandTotal}
        currency={currency}
        isNew={isNew}
        formatCurrency={formatCurrency}
        t={t}
      />

      {/* Sent info */}
      {invoice?.sent_at && (
        <Text color="gray.500" fontSize="xs" mt={4}>
          {t('invoices.sentAt', 'Sent')}: {new Date(invoice.sent_at).toLocaleString('nl-NL')}
        </Text>
      )}

      {/* Email preview panel */}
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
