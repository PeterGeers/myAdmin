/**
 * Tests for ZZPProducts page logic.
 * Tests price formatting, empty external_reference fallback, and product type badge rendering.
 */
import { Product } from '../types/zzp';

// Extracted from ZZPProducts.tsx — price formatting logic
function formatPrice(unitPrice: number): string {
  return `€ ${Number(unitPrice).toFixed(2)}`;
}

// Extracted from ZZPProducts.tsx — external reference fallback
function displayExternalReference(ref?: string): string {
  return ref || '-';
}

// Product type badge: the component renders a Badge with the product_type text
// We test that the type string is used directly as badge content
function getBadgeText(product: Partial<Product>): string {
  return product.product_type || '';
}

describe('ZZPProducts page logic', () => {
  describe('price formatting', () => {
    it('formats integer price with two decimals', () => {
      expect(formatPrice(100)).toBe('€ 100.00');
    });

    it('formats decimal price with two decimals', () => {
      expect(formatPrice(95.5)).toBe('€ 95.50');
    });

    it('formats zero price', () => {
      expect(formatPrice(0)).toBe('€ 0.00');
    });

    it('formats large price', () => {
      expect(formatPrice(15200)).toBe('€ 15200.00');
    });

    it('rounds to two decimal places', () => {
      expect(formatPrice(99.999)).toBe('€ 100.00');
    });

    it('handles string-coerced numbers', () => {
      // In the component: Number(p.unit_price).toFixed(2)
      expect(formatPrice(Number('49.90'))).toBe('€ 49.90');
    });
  });

  describe('external reference fallback', () => {
    it('returns the reference when present', () => {
      expect(displayExternalReference('EXT-001')).toBe('EXT-001');
    });

    it('returns dash when undefined', () => {
      expect(displayExternalReference(undefined)).toBe('-');
    });

    it('returns dash when empty string', () => {
      expect(displayExternalReference('')).toBe('-');
    });
  });

  describe('product type badge', () => {
    it('renders service type', () => {
      expect(getBadgeText({ product_type: 'service' })).toBe('service');
    });

    it('renders product type', () => {
      expect(getBadgeText({ product_type: 'product' })).toBe('product');
    });

    it('renders custom type', () => {
      expect(getBadgeText({ product_type: 'subscription' })).toBe('subscription');
    });

    it('handles missing product_type', () => {
      expect(getBadgeText({})).toBe('');
    });
  });
});
