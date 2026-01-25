import {
    Alert, AlertIcon,
    Box, Button,
    Card, CardBody,
    FormControl, FormLabel,
    Heading,
    Select,
    Table,
    Tbody,
    Td,
    Text,
    Th,
    Thead,
    Tr,
    VStack
} from '@chakra-ui/react';
import React, { useEffect, useState } from 'react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';

interface Provider {
  code: string;
  name: string;
  country_code: string;
}

interface Connection {
  id: string;
  provider_name: string;
  status: string;
  last_success_at: string;
}

interface Account {
  id: string;
  name: string;
  nature: string;
  balance: number;
  currency_code: string;
  iban: string;
}

const BankConnect: React.FC = () => {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [connections, setConnections] = useState<Connection[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [bankAccounts, setBankAccounts] = useState<Array<{rekeningNummer: string, Account: string, administration: string}>>([]);

  useEffect(() => {
    fetchProviders();
    fetchBankAccounts();
    const savedCustomerId = localStorage.getItem('saltedge_customer_id');
    if (savedCustomerId) {
      setCustomerId(savedCustomerId);
      fetchConnections(savedCustomerId);
    }
  }, []);

  const fetchBankAccounts = async () => {
    try {
      const response = await authenticatedGet('/api/banking/lookups');
      const data = await response.json();
      if (data.success && data.bank_accounts) {
        setBankAccounts(data.bank_accounts);
      }
    } catch (error) {
      console.error('Error fetching bank accounts:', error);
    }
  };

  const fetchProviders = async () => {
    try {
      const response = await authenticatedGet('/api/saltedge/providers?country=NL');
      const data = await response.json();
      if (data.data) {
        setProviders(data.data);
      }
    } catch (error) {
      setMessage(`Error fetching providers: ${error}`);
    }
  };

  const createCustomer = async () => {
    try {
      setLoading(true);
      const identifier = `user_${Date.now()}`;
      const response = await authenticatedPost('/api/saltedge/customer/create', { identifier });
      const data = await response.json();
      if (data.data?.id) {
        setCustomerId(data.data.id);
        localStorage.setItem('saltedge_customer_id', data.data.id);
        setMessage('Customer created successfully!');
      }
    } catch (error) {
      setMessage(`Error creating customer: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const connectBank = async () => {
    if (!customerId || !selectedProvider) {
      setMessage('Please create customer and select a bank');
      return;
    }

    try {
      setLoading(true);
      const response = await authenticatedPost('/api/saltedge/connect/start', {
        customer_id: customerId,
        provider_code: selectedProvider,
        return_url: window.location.origin + '/banking/callback'
      });
      const data = await response.json();
      if (data.data?.connect_url) {
        window.open(data.data.connect_url, '_blank');
        setMessage('Opening bank authorization page...');
      }
    } catch (error) {
      setMessage(`Error connecting bank: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchConnections = async (custId: string) => {
    try {
      const response = await authenticatedGet(`/api/saltedge/connections?customer_id=${custId}`);
      const data = await response.json();
      if (data.data) {
        setConnections(data.data);
      }
    } catch (error) {
      console.error('Error fetching connections:', error);
    }
  };

  const fetchAccounts = async (connectionId: string) => {
    try {
      setLoading(true);
      const response = await authenticatedGet(`/api/saltedge/accounts/${connectionId}`);
      const data = await response.json();
      if (data.data) {
        setAccounts(data.data);
      }
    } catch (error) {
      setMessage(`Error fetching accounts: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  const importTransactions = async (accountId: string, iban: string) => {
    const bankAccount = bankAccounts.find(ba => ba.rekeningNummer === iban);
    if (!bankAccount) {
      setMessage('Bank account mapping not found');
      return;
    }

    try {
      setLoading(true);
      const response = await authenticatedPost('/api/saltedge/import/transactions', {
        account_id: accountId,
        iban: iban,
        account_code: bankAccount.Account,
        administration: bankAccount.administration,
        from_date: new Date(Date.now() - 90 * 24 * 60 * 60 * 1000).toISOString().split('T')[0]
      });
      const data = await response.json();
      if (data.success) {
        setMessage(`Imported ${data.transactions.length} transactions`);
      }
    } catch (error) {
      setMessage(`Error importing transactions: ${error}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box w="100%" p={4}>
      <Heading size="lg" mb={6}>Bank Connection (Salt Edge)</Heading>

      {message && (
        <Alert status={message.includes('Error') ? 'error' : 'success'} mb={4}>
          <AlertIcon />
          {message}
        </Alert>
      )}

      <VStack align="stretch" spacing={6}>
        <Card>
          <CardBody>
            <Heading size="sm" mb={4}>Step 1: Customer Setup</Heading>
            {!customerId ? (
              <Button onClick={createCustomer} isLoading={loading} colorScheme="blue">
                Create Customer
              </Button>
            ) : (
              <Text color="green.500">Customer ID: {customerId}</Text>
            )}
          </CardBody>
        </Card>

        {customerId && (
          <Card>
            <CardBody>
              <Heading size="sm" mb={4}>Step 2: Connect Bank</Heading>
              <FormControl mb={4}>
                <FormLabel>Select Bank</FormLabel>
                <Select
                  value={selectedProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  placeholder="Choose your bank..."
                >
                  {providers.map(provider => (
                    <option key={provider.code} value={provider.code}>
                      {provider.name}
                    </option>
                  ))}
                </Select>
              </FormControl>
              <Button
                onClick={connectBank}
                isLoading={loading}
                colorScheme="green"
                isDisabled={!selectedProvider}
              >
                Connect Bank
              </Button>
            </CardBody>
          </Card>
        )}

        {connections.length > 0 && (
          <Card>
            <CardBody>
              <Heading size="sm" mb={4}>Step 3: Your Connections</Heading>
              <Table size="sm">
                <Thead>
                  <Tr>
                    <Th>Bank</Th>
                    <Th>Status</Th>
                    <Th>Last Success</Th>
                    <Th>Actions</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {connections.map(conn => (
                    <Tr key={conn.id}>
                      <Td>{conn.provider_name}</Td>
                      <Td>{conn.status}</Td>
                      <Td>{conn.last_success_at ? new Date(conn.last_success_at).toLocaleDateString() : 'N/A'}</Td>
                      <Td>
                        <Button size="xs" onClick={() => fetchAccounts(conn.id)}>
                          View Accounts
                        </Button>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </CardBody>
          </Card>
        )}

        {accounts.length > 0 && (
          <Card>
            <CardBody>
              <Heading size="sm" mb={4}>Step 4: Import Transactions</Heading>
              <Table size="sm">
                <Thead>
                  <Tr>
                    <Th>Account</Th>
                    <Th>IBAN</Th>
                    <Th>Balance</Th>
                    <Th>Actions</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {accounts.map(account => (
                    <Tr key={account.id}>
                      <Td>{account.name}</Td>
                      <Td>{account.iban}</Td>
                      <Td>€{account.balance.toFixed(2)}</Td>
                      <Td>
                        <Button
                          size="xs"
                          colorScheme="orange"
                          onClick={() => importTransactions(account.id, account.iban)}
                        >
                          Import
                        </Button>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            </CardBody>
          </Card>
        )}
      </VStack>
    </Box>
  );
};

export default BankConnect;
