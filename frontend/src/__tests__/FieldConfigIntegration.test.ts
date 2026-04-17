/**
 * Tests for field config integration patterns.
 * Verifies the isVisible/isRequired logic across all three field levels
 * and the pattern of filtering table columns by visibility.
 */
import { FieldLevel, FieldConfig } from '../types/zzp';

// Extracted from useFieldConfig.ts — the core logic used in forms and tables
function isVisible(config: FieldConfig, field: string): boolean {
  return config[field] !== 'hidden';
}

function isRequired(config: FieldConfig, field: string): boolean {
  return config[field] === 'required';
}

// Pattern used in table components: filter columns by visibility
interface TableColumn {
  key: string;
  label: string;
}

function filterVisibleColumns(columns: TableColumn[], config: FieldConfig): TableColumn[] {
  return columns.filter(col => isVisible(config, col.key));
}

describe('Field config integration', () => {
  const sampleConfig: FieldConfig = {
    client_id: 'required',
    company_name: 'required',
    vat_number: 'hidden',
    phone: 'optional',
    contact_person: 'optional',
    kvk_number: 'hidden',
    iban: 'optional',
  };

  describe('isVisible', () => {
    it('returns true for required fields', () => {
      expect(isVisible(sampleConfig, 'client_id')).toBe(true);
    });

    it('returns true for optional fields', () => {
      expect(isVisible(sampleConfig, 'phone')).toBe(true);
    });

    it('returns false for hidden fields', () => {
      expect(isVisible(sampleConfig, 'vat_number')).toBe(false);
    });

    it('returns true for fields not in config (default visible)', () => {
      expect(isVisible(sampleConfig, 'unknown_field')).toBe(true);
    });
  });

  describe('isRequired', () => {
    it('returns true for required fields', () => {
      expect(isRequired(sampleConfig, 'client_id')).toBe(true);
    });

    it('returns false for optional fields', () => {
      expect(isRequired(sampleConfig, 'phone')).toBe(false);
    });

    it('returns false for hidden fields', () => {
      expect(isRequired(sampleConfig, 'vat_number')).toBe(false);
    });

    it('returns false for fields not in config', () => {
      expect(isRequired(sampleConfig, 'unknown_field')).toBe(false);
    });
  });

  describe('all three field levels', () => {
    const levels: FieldLevel[] = ['required', 'optional', 'hidden'];

    it('required: visible and required', () => {
      const cfg: FieldConfig = { test_field: 'required' };
      expect(isVisible(cfg, 'test_field')).toBe(true);
      expect(isRequired(cfg, 'test_field')).toBe(true);
    });

    it('optional: visible but not required', () => {
      const cfg: FieldConfig = { test_field: 'optional' };
      expect(isVisible(cfg, 'test_field')).toBe(true);
      expect(isRequired(cfg, 'test_field')).toBe(false);
    });

    it('hidden: not visible and not required', () => {
      const cfg: FieldConfig = { test_field: 'hidden' };
      expect(isVisible(cfg, 'test_field')).toBe(false);
      expect(isRequired(cfg, 'test_field')).toBe(false);
    });

    it('covers all FieldLevel values', () => {
      expect(levels).toHaveLength(3);
      expect(levels).toContain('required');
      expect(levels).toContain('optional');
      expect(levels).toContain('hidden');
    });
  });

  describe('table column filtering by visibility', () => {
    const allColumns: TableColumn[] = [
      { key: 'client_id', label: 'Client ID' },
      { key: 'company_name', label: 'Company' },
      { key: 'vat_number', label: 'VAT Number' },
      { key: 'phone', label: 'Phone' },
      { key: 'contact_person', label: 'Contact Person' },
      { key: 'kvk_number', label: 'KvK Number' },
      { key: 'iban', label: 'IBAN' },
    ];

    it('filters out hidden columns', () => {
      const visible = filterVisibleColumns(allColumns, sampleConfig);
      const keys = visible.map(c => c.key);
      expect(keys).not.toContain('vat_number');
      expect(keys).not.toContain('kvk_number');
    });

    it('keeps required and optional columns', () => {
      const visible = filterVisibleColumns(allColumns, sampleConfig);
      const keys = visible.map(c => c.key);
      expect(keys).toContain('client_id');
      expect(keys).toContain('company_name');
      expect(keys).toContain('phone');
      expect(keys).toContain('contact_person');
      expect(keys).toContain('iban');
    });

    it('returns correct count after filtering', () => {
      const visible = filterVisibleColumns(allColumns, sampleConfig);
      // 7 total - 2 hidden = 5 visible
      expect(visible).toHaveLength(5);
    });

    it('returns all columns when config is empty', () => {
      const visible = filterVisibleColumns(allColumns, {});
      expect(visible).toHaveLength(allColumns.length);
    });

    it('returns no columns when all are hidden', () => {
      const allHidden: FieldConfig = {};
      allColumns.forEach(c => { allHidden[c.key] = 'hidden'; });
      const visible = filterVisibleColumns(allColumns, allHidden);
      expect(visible).toHaveLength(0);
    });
  });
});
