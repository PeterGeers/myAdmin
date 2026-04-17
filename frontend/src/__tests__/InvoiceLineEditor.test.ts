/**
 * Tests for InvoiceLineEditor logic.
 * Tests the line calculation and product auto-fill behavior
 * by simulating the updateLine logic extracted from the component.
 */

import { Product, InvoiceLine } from '../types/zzp';

// Extract the core logic from InvoiceLineEditor for testing
function updateLine(
  lines: Partial<InvoiceLine>[],
  products: Product[],
  idx: number,
  field: string,
  value: any,
): Partial<InvoiceLine>[] {
  const updated = [...lines];
  updated[idx] = { ...updated[idx], [field]: value };

  if (field === 'product_id' && value) {
    const product = products.find(p => p.id === Number(value));
    if (product) {
      updated[idx].description = product.name;
      updated[idx].unit_price = product.unit_price;
      updated[idx].vat_code = product.vat_code;
    }
  }

  const qty = Number(updated[idx].quantity) || 0;
  const price = Number(updated[idx].unit_price) || 0;
  updated[idx].line_total = Math.round(qty * price * 100) / 100;

  return updated;
}

const mockProducts: Product[] = [
  { id: 1, product_code: 'DEV', name: 'Development', description: '', product_type: 'service', unit_price: 95, vat_code: 'high', unit_of_measure: 'uur', is_active: true, external_reference: '' },
  { id: 2, product_code: 'HOST', name: 'Hosting', description: '', product_type: 'subscription', unit_price: 50, vat_code: 'high', unit_of_measure: 'maand', is_active: true, external_reference: '' },
];

describe('InvoiceLineEditor logic', () => {
  it('calculates line_total from quantity * unit_price', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 10, unit_price: 95, vat_code: 'high', line_total: 0 }];
    const result = updateLine(lines, mockProducts, 0, 'quantity', 10);
    expect(result[0].line_total).toBe(950);
  });

  it('recalculates on price change', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 8, unit_price: 100, vat_code: 'high', line_total: 800 }];
    const result = updateLine(lines, mockProducts, 0, 'unit_price', 120);
    expect(result[0].line_total).toBe(960);
  });

  it('auto-fills from product selection', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 160, unit_price: 0, vat_code: 'high', line_total: 0 }];
    const result = updateLine(lines, mockProducts, 0, 'product_id', 1);
    expect(result[0].description).toBe('Development');
    expect(result[0].unit_price).toBe(95);
    expect(result[0].vat_code).toBe('high');
    expect(result[0].line_total).toBe(15200);
  });

  it('handles zero quantity', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 0, unit_price: 95, vat_code: 'high', line_total: 0 }];
    const result = updateLine(lines, mockProducts, 0, 'quantity', 0);
    expect(result[0].line_total).toBe(0);
  });

  it('handles decimal quantities', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 7.5, unit_price: 95, vat_code: 'high', line_total: 0 }];
    const result = updateLine(lines, mockProducts, 0, 'quantity', 7.5);
    expect(result[0].line_total).toBe(712.5);
  });

  it('rounds to 2 decimal places', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 1, unit_price: 33.33, vat_code: 'high', line_total: 0 }];
    const result = updateLine(lines, mockProducts, 0, 'quantity', 3);
    expect(result[0].line_total).toBe(99.99);
  });

  it('does not auto-fill for unknown product', () => {
    const lines: Partial<InvoiceLine>[] = [{ quantity: 1, unit_price: 50, description: 'Custom', vat_code: 'low', line_total: 50 }];
    const result = updateLine(lines, mockProducts, 0, 'product_id', 999);
    expect(result[0].description).toBe('Custom');
    expect(result[0].unit_price).toBe(50);
  });
});
