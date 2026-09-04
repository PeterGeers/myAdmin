/**
 * Render tests for InvoiceLineEditor.
 *
 * Verifies the scrollable line-items region (added so a long list of invoice
 * lines scrolls within a bounded height instead of overflowing the modal /
 * window) and that the "Add line" control stays reachable below the scroll box.
 *
 * Note: the centralized chakra-ui-react mock strips style props (maxH,
 * overflowX, overflowY) before rendering to the DOM, so this test asserts the
 * scroll container via its data-testid rather than via computed style.
 */

import React from 'react';
import { render, screen, cleanup } from '@testing-library/react';
import { describe, it, expect, afterEach } from 'vitest';
import { InvoiceLineEditor } from '../components/zzp/InvoiceLineEditor';
import { InvoiceLine, Product } from '../types/zzp';

const mockProducts: Product[] = [
  { id: 1, product_code: 'DEV', name: 'Development', description: '', product_type: 'service', unit_price: 95, vat_code: 'high', unit_of_measure: 'uur', is_active: true, external_reference: '' },
];

function makeLines(count: number): Partial<InvoiceLine>[] {
  return Array.from({ length: count }, (_, i) => ({
    description: `Line ${i + 1}`,
    quantity: 1,
    unit_price: 10,
    vat_code: 'high',
    line_total: 10,
  }));
}

afterEach(cleanup);

describe('InvoiceLineEditor render', () => {
  it('wraps the table in a dedicated scroll container', () => {
    render(
      <InvoiceLineEditor
        lines={makeLines(3)}
        products={mockProducts}
        onChange={() => {}}
      />,
    );
    expect(screen.getByTestId('invoice-lines-scroll')).toBeTruthy();
  });

  it('renders every line inside the scroll container even when the list is long', () => {
    render(
      <InvoiceLineEditor
        lines={makeLines(30)}
        products={mockProducts}
        onChange={() => {}}
      />,
    );
    const scrollBox = screen.getByTestId('invoice-lines-scroll');
    // 30 body rows + 1 header row = 31 rows, all within the scroll container.
    expect(scrollBox.querySelectorAll('tr').length).toBe(31);
  });

  it('keeps the Add line button reachable outside the scroll container (editable mode)', () => {
    render(
      <InvoiceLineEditor
        lines={makeLines(30)}
        products={mockProducts}
        onChange={() => {}}
      />,
    );
    const addButton = screen.getByLabelText('Add line');
    expect(addButton).toBeTruthy();
    // The add-line control must NOT be inside the scrollable region, so it
    // stays visible/reachable when the lines list scrolls.
    const scrollBox = screen.getByTestId('invoice-lines-scroll');
    expect(scrollBox.contains(addButton)).toBe(false);
  });

  it('does not render the Add line button in read-only mode', () => {
    render(
      <InvoiceLineEditor
        lines={makeLines(3)}
        products={mockProducts}
        readOnly
        onChange={() => {}}
      />,
    );
    expect(screen.queryByLabelText('Add line')).toBeNull();
  });
});
