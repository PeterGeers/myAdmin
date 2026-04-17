/**
 * Tests for ContactModal validation logic.
 * Tests the Yup validation schema used in the contact form.
 */
import * as Yup from 'yup';

// Extracted from ContactModal.tsx
const validationSchema = Yup.object().shape({
  client_id: Yup.string().required('Client ID is required')
    .matches(/^[A-Za-z0-9_-]{1,20}$/, 'Max 20 alphanumeric chars'),
  company_name: Yup.string().required('Company name is required'),
});

describe('ContactModal validation', () => {
  it('accepts valid client_id and company_name', async () => {
    await expect(validationSchema.validate({
      client_id: 'ACME', company_name: 'Acme Corp',
    })).resolves.toBeDefined();
  });

  it('rejects empty client_id', async () => {
    await expect(validationSchema.validate({
      client_id: '', company_name: 'Acme Corp',
    })).rejects.toThrow('Client ID is required');
  });

  it('rejects empty company_name', async () => {
    await expect(validationSchema.validate({
      client_id: 'ACME', company_name: '',
    })).rejects.toThrow('Company name is required');
  });

  it('rejects client_id with special characters', async () => {
    await expect(validationSchema.validate({
      client_id: 'ACME@#$', company_name: 'Acme Corp',
    })).rejects.toThrow('Max 20 alphanumeric chars');
  });

  it('rejects client_id longer than 20 chars', async () => {
    await expect(validationSchema.validate({
      client_id: 'A'.repeat(21), company_name: 'Acme Corp',
    })).rejects.toThrow('Max 20 alphanumeric chars');
  });

  it('accepts client_id with hyphens and underscores', async () => {
    await expect(validationSchema.validate({
      client_id: 'MY-CLIENT_01', company_name: 'Test',
    })).resolves.toBeDefined();
  });

  it('accepts exactly 20 char client_id', async () => {
    await expect(validationSchema.validate({
      client_id: 'A'.repeat(20), company_name: 'Test',
    })).resolves.toBeDefined();
  });
});
