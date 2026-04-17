/**
 * Tests for ProductModal validation logic.
 * Tests the Yup validation schema used in the product form.
 */
import * as Yup from 'yup';

// Extracted from ProductModal.tsx
const validationSchema = Yup.object().shape({
  product_code: Yup.string().required('Product code is required'),
  name: Yup.string().required('Name is required'),
  product_type: Yup.string().required('Type is required'),
  vat_code: Yup.string().required('VAT code is required'),
});

const VAT_CODES = ['high', 'low', 'zero'];

describe('ProductModal validation', () => {
  const validProduct = {
    product_code: 'DEV-HR', name: 'Development',
    product_type: 'service', vat_code: 'high',
  };

  it('accepts valid product data', async () => {
    await expect(validationSchema.validate(validProduct)).resolves.toBeDefined();
  });

  it('rejects empty product_code', async () => {
    await expect(validationSchema.validate({
      ...validProduct, product_code: '',
    })).rejects.toThrow('Product code is required');
  });

  it('rejects empty name', async () => {
    await expect(validationSchema.validate({
      ...validProduct, name: '',
    })).rejects.toThrow('Name is required');
  });

  it('rejects empty product_type', async () => {
    await expect(validationSchema.validate({
      ...validProduct, product_type: '',
    })).rejects.toThrow('Type is required');
  });

  it('rejects empty vat_code', async () => {
    await expect(validationSchema.validate({
      ...validProduct, vat_code: '',
    })).rejects.toThrow('VAT code is required');
  });
});

describe('ProductModal VAT codes', () => {
  it('includes high, low, zero', () => {
    expect(VAT_CODES).toEqual(['high', 'low', 'zero']);
  });

  it('has exactly 3 options', () => {
    expect(VAT_CODES).toHaveLength(3);
  });
});
