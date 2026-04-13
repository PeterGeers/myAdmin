/**
 * Tax rate administration type definitions.
 */

export interface TaxRate {
  id: number;
  tax_type: string;
  tax_code: string;
  rate: number;
  ledger_account: string | null;
  effective_from: string;
  effective_to: string | null;
  source: 'system' | 'tenant';
  description: string | null;
  calc_method: string;
}

export interface TaxRateCreateRequest {
  tax_type: string;
  tax_code: string;
  rate: number;
  effective_from: string;
  effective_to?: string;
  ledger_account?: string;
  description?: string;
  calc_method?: string;
  administration?: string;
}

export interface TaxRateUpdateRequest {
  rate?: number;
  description?: string;
  ledger_account?: string;
  effective_from?: string;
  effective_to?: string;
  calc_method?: string;
}

export interface TaxRatesResponse {
  success: boolean;
  tenant: string;
  tax_rates: TaxRate[];
}
