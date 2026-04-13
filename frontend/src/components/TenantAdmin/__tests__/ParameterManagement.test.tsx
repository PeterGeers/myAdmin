/**
 * ParameterManagement Component - Unit Tests
 */
import React from 'react';
import { render, screen, waitFor, fireEvent } from '../../../test-utils';
import ParameterManagement from '../ParameterManagement';

jest.mock('../../../services/parameterService', () => ({
  getParameters: jest.fn(),
  createParameter: jest.fn(),
  updateParameter: jest.fn(),
  deleteParameter: jest.fn(),
}));

jest.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en', changeLanguage: jest.fn() }
  })
}));

const { getParameters, createParameter, updateParameter, deleteParameter } =
  require('../../../services/parameterService');

const mockParams = {
  success: true, tenant: 'T1',
  parameters: {
    storage: [
      { id: 1, namespace: 'storage', key: 'provider', value: 'google_drive', value_type: 'string', scope_origin: 'tenant', is_secret: false },
      { id: null, namespace: 'storage', key: 'bucket', value: 'default', value_type: 'string', scope_origin: 'system', is_secret: false },
    ],
    fin: [
      { id: 2, namespace: 'fin', key: 'currency', value: 'EUR', value_type: 'string', scope_origin: 'tenant', is_secret: false },
    ],
  },
};

describe('ParameterManagement', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    getParameters.mockResolvedValue(mockParams);
  });

  describe('Rendering', () => {
    test('shows loading spinner initially', () => {
      getParameters.mockReturnValue(new Promise(() => {}));
      render(<ParameterManagement tenant="T1" />);
      expect(document.querySelector('.chakra-spinner')).toBeInTheDocument();
    });

    test('renders parameter table after loading', async () => {
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.getByText('provider')).toBeInTheDocument();
        expect(screen.getByText('google_drive')).toBeInTheDocument();
      });
    });

    test('renders all parameters from all namespaces', async () => {
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.getByText('provider')).toBeInTheDocument();
        expect(screen.getByText('bucket')).toBeInTheDocument();
        expect(screen.getByText('currency')).toBeInTheDocument();
      });
    });

    test('shows scope badges', async () => {
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => {
        expect(screen.getAllByText('tenant').length).toBeGreaterThan(0);
        expect(screen.getAllByText('system').length).toBeGreaterThan(0);
      });
    });

    test('shows secret values as masked', async () => {
      getParameters.mockResolvedValue({
        success: true, tenant: 'T1',
        parameters: { ns: [{ id: 3, namespace: 'ns', key: 'api_key', value: '********', value_type: 'string', scope_origin: 'tenant', is_secret: true }] },
      });
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('********')).toBeInTheDocument());
    });

    test('shows empty state when no parameters', async () => {
      getParameters.mockResolvedValue({ success: true, tenant: 'T1', parameters: {} });
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('tenantAdmin.parameters.noParameters')).toBeInTheDocument());
    });
  });

  describe('Row Click', () => {
    test('clicking tenant row opens edit modal', async () => {
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('provider')).toBeInTheDocument());
      fireEvent.click(screen.getByText('provider'));
      await waitFor(() => expect(screen.getByText(/tenantAdmin.parameters.editParameter/)).toBeInTheDocument());
    });

    test('clicking system row does not open modal', async () => {
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('bucket')).toBeInTheDocument());
      fireEvent.click(screen.getByText('bucket'));
      expect(screen.queryByText(/tenantAdmin.parameters.editParameter/)).not.toBeInTheDocument();
    });
  });

  describe('Add Parameter', () => {
    test('add button is visible', async () => {
      render(<ParameterManagement tenant="T1" />);
      await waitFor(() => expect(screen.getByText('tenantAdmin.parameters.addParameter')).toBeInTheDocument());
    });
  });
});
