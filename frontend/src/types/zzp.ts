// ZZP Module TypeScript Types
// Reference: .kiro/specs/zzp-module/design.md §6.5

export type ContactType = 'client' | 'supplier' | 'both' | 'other';
export type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'overdue' | 'cancelled' | 'credited';
export type InvoiceType = 'invoice' | 'credit_note';
export type EmailType = 'general' | 'invoice' | 'other';
export type FieldLevel = 'required' | 'optional' | 'hidden';
export type FieldConfig = Record<string, FieldLevel>;

export interface ContactEmail {
  id?: number;
  email: string;
  email_type: EmailType;
  is_primary: boolean;
}

export interface Contact {
  id: number;
  client_id: string;
  contact_type: ContactType;
  company_name: string;
  contact_person?: string;
  street_address?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  vat_number?: string;
  kvk_number?: string;
  phone?: string;
  iban?: string;
  emails: ContactEmail[];
  is_active: boolean;
}

export interface Product {
  id: number;
  product_code: string;
  external_reference?: string;
  name: string;
  description?: string;
  product_type: string;
  unit_price: number;
  vat_code: string;
  unit_of_measure: string;
  is_active: boolean;
}

export interface InvoiceLine {
  id?: number;
  product_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  vat_code: string;
  vat_rate: number;
  vat_amount: number;
  line_total: number;
  sort_order?: number;
}

/** Line item shape for create/update requests — server calculates vat_rate, vat_amount, line_total */
export interface InvoiceLineInput {
  product_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  vat_code: string;
  sort_order?: number;
}

/** Invoice create/update request payload */
export interface InvoiceInput {
  contact_id: number;
  invoice_date: string;
  payment_terms_days: number;
  currency?: string;
  exchange_rate?: number;
  notes?: string;
  lines: InvoiceLineInput[];
}

export interface VatSummaryLine {
  vat_code: string;
  vat_rate: number;
  base_amount: number;
  vat_amount: number;
}

export interface Invoice {
  id: number;
  invoice_number: string;
  invoice_type: InvoiceType;
  contact: Pick<Contact, 'id' | 'client_id' | 'company_name'>;
  invoice_date: string;
  due_date: string;
  payment_terms_days: number;
  currency: string;
  exchange_rate: number;
  status: InvoiceStatus;
  lines: InvoiceLine[];
  subtotal: number;
  vat_summary: VatSummaryLine[];
  vat_total: number;
  grand_total: number;
  notes?: string;
  original_invoice_id?: number;
  copied_from_invoice_id?: number;
  sent_at?: string;
}

export interface TimeEntry {
  id: number;
  contact_id: number;
  contact?: Pick<Contact, 'id' | 'client_id' | 'company_name'>;
  product_id?: number;
  project_name?: string;
  entry_date: string;
  hours: number;
  hourly_rate: number;
  description?: string;
  is_billable: boolean;
  is_billed: boolean;
  invoice_id?: number;
}

export interface TimeSummary {
  contact_id?: number;
  project_name?: string;
  period?: string;
  total_hours: number;
  total_amount: number;
}

export interface AgingBuckets {
  current: number;
  '1_30_days': number;
  '31_60_days': number;
  '61_90_days': number;
  '90_plus_days': number;
}

export interface AgingContact {
  contact: Pick<Contact, 'id' | 'client_id' | 'company_name'>;
  total: number;
  invoices: {
    invoice_number: string;
    grand_total: number;
    due_date: string;
    days_overdue: number;
    bucket: string;
  }[];
}

export interface AgingData {
  total_outstanding: number;
  buckets: AgingBuckets;
  by_contact: AgingContact[];
}

export interface InvoiceFilters {
  status?: InvoiceStatus;
  contact_id?: number;
  invoice_type?: InvoiceType;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}

export interface TimeEntryFilters {
  contact_id?: number;
  project_name?: string;
  date_from?: string;
  date_to?: string;
  is_billable?: boolean;
  is_billed?: boolean;
  limit?: number;
  offset?: number;
}
