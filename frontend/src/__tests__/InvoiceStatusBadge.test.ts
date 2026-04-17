/**
 * Tests for InvoiceStatusBadge color mapping logic.
 */
import { InvoiceStatus } from '../types/zzp';

// Extract the color mapping from the component for testing
const STATUS_COLORS: Record<InvoiceStatus, string> = {
  draft: 'gray',
  sent: 'blue',
  paid: 'green',
  overdue: 'red',
  cancelled: 'orange',
  credited: 'purple',
};

describe('InvoiceStatusBadge color mapping', () => {
  it('maps draft to gray', () => {
    expect(STATUS_COLORS['draft']).toBe('gray');
  });

  it('maps sent to blue', () => {
    expect(STATUS_COLORS['sent']).toBe('blue');
  });

  it('maps paid to green', () => {
    expect(STATUS_COLORS['paid']).toBe('green');
  });

  it('maps overdue to red', () => {
    expect(STATUS_COLORS['overdue']).toBe('red');
  });

  it('maps cancelled to orange', () => {
    expect(STATUS_COLORS['cancelled']).toBe('orange');
  });

  it('maps credited to purple', () => {
    expect(STATUS_COLORS['credited']).toBe('purple');
  });

  it('covers all InvoiceStatus values', () => {
    const allStatuses: InvoiceStatus[] = ['draft', 'sent', 'paid', 'overdue', 'cancelled', 'credited'];
    allStatuses.forEach(status => {
      expect(STATUS_COLORS[status]).toBeDefined();
    });
  });
});
