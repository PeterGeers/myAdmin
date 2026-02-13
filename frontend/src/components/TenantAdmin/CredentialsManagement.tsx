import React, { useState, useEffect } from 'react';
import {
  Box, VStack, HStack, Button, Text, useToast, Spinner,
  Table, Thead, Tbody, Tr, Th, Td, Badge, Alert, AlertIcon,
  Input, FormControl, FormLabel, Select, Modal, ModalOverlay,
  ModalContent, ModalHeader, ModalBody, ModalFooter, ModalCloseButton,
  useDisclosure
} from '@chakra-ui/react';
import { 
  CheckCircleIcon, 
  RepeatIcon, 
  ExternalLinkIcon
} from '@chakra-ui/icons';
import { fetchAuthSession } from 'aws-amplify/auth';

interface CredentialInfo {
  type: string;
  created_at: string | null;
  updated_at: string | null;
}

interface CredentialsManagementProps {
  tenant: string;
}

export function CredentialsManagement({ tenant }: CredentialsManagementProps) {
  const [credentials, setCredentials] = useState<CredentialInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [credentialType, setCredentialType] = useState('google_drive');
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  useEffect(() => {
    loadCredentials();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant]);

  const loadCredentials = async () => {
    setLoading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/tenant-admin/credentials`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant
        }
      });

      if (!response.ok) {
        throw new Error('Failed to load credentials');
      }

      const data = await response.json();
      setCredentials(data.credentials || []);
    } catch (error) {
      toast({
        title: 'Error loading credentials',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      // Validate file type
      if (!file.name.endsWith('.json')) {
        toast({
          title: 'Invalid file type',
          description: 'Please select a JSON file',
          status: 'error',
          duration: 3000,
        });
        return;
      }
      setSelectedFile(file);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      toast({
        title: 'No file selected',
        description: 'Please select a JSON file to upload',
        status: 'warning',
        duration: 3000,
      });
      return;
    }

    setUploading(true);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('credential_type', credentialType);

      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/tenant-admin/credentials`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant
        },
        body: formData
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to upload credentials');
      }

      const data = await response.json();

      toast({
        title: 'Credentials uploaded',
        description: data.message,
        status: 'success',
        duration: 5000,
      });

      // Show test result if available
      if (data.test_result) {
        toast({
          title: data.test_result.success ? 'Connection test passed' : 'Connection test failed',
          description: data.test_result.message,
          status: data.test_result.success ? 'success' : 'warning',
          duration: 5000,
        });
      }

      // Reset form and reload
      setSelectedFile(null);
      setCredentialType('google_drive');
      onClose();
      loadCredentials();
    } catch (error) {
      toast({
        title: 'Upload failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setUploading(false);
    }
  };

  const handleTestCredential = async (type: string) => {
    setTesting(type);
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/tenant-admin/credentials/test`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ credential_type: type })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Test failed');
      }

      const data = await response.json();
      const testResult = data.test_result;

      toast({
        title: testResult.success ? 'Connection successful' : 'Connection failed',
        description: testResult.message,
        status: testResult.success ? 'success' : 'error',
        duration: 5000,
      });
    } catch (error) {
      toast({
        title: 'Test failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setTesting(null);
    }
  };

  const handleStartOAuth = async () => {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.idToken?.toString();

      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/tenant-admin/credentials/oauth/start`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'X-Tenant': tenant,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ service: 'google_drive' })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to start OAuth flow');
      }

      const data = await response.json();

      // Listen for OAuth callback message
      const messageHandler = async (event: MessageEvent) => {
        if (event.data.type === 'oauth_success') {
          // Remove listener
          window.removeEventListener('message', messageHandler);
          
          // Call complete endpoint to store tokens
          try {
            const completeResponse = await fetch(`${process.env.REACT_APP_API_URL}/api/tenant-admin/credentials/oauth/complete`, {
              method: 'POST',
              headers: {
                'Authorization': `Bearer ${token}`,
                'X-Tenant': tenant,
                'Content-Type': 'application/json'
              },
              body: JSON.stringify({
                code: event.data.code,
                state: event.data.state,
                service: 'google_drive'
              })
            });

            if (!completeResponse.ok) {
              const errorData = await completeResponse.json();
              throw new Error(errorData.error || 'Failed to complete OAuth flow');
            }

            toast({
              title: 'Google Drive connected',
              description: 'OAuth tokens stored successfully',
              status: 'success',
              duration: 5000,
            });

            // Reload credentials
            loadCredentials();
          } catch (error) {
            toast({
              title: 'OAuth completion failed',
              description: error instanceof Error ? error.message : 'Unknown error',
              status: 'error',
              duration: 5000,
            });
          }
        } else if (event.data.type === 'oauth_error') {
          // Remove listener
          window.removeEventListener('message', messageHandler);
          
          toast({
            title: 'OAuth failed',
            description: event.data.error || 'Authorization failed',
            status: 'error',
            duration: 5000,
          });
        }
      };

      // Add message listener
      window.addEventListener('message', messageHandler);

      // Open OAuth URL in new window
      const popup = window.open(data.oauth_url, '_blank', 'width=600,height=700');
      
      if (!popup) {
        window.removeEventListener('message', messageHandler);
        toast({
          title: 'Popup blocked',
          description: 'Please allow popups for this site',
          status: 'warning',
          duration: 5000,
        });
        return;
      }

      toast({
        title: 'OAuth flow started',
        description: 'Please complete the authorization in the new window',
        status: 'info',
        duration: 5000,
      });
    } catch (error) {
      toast({
        title: 'OAuth failed',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minH="200px">
        <Spinner size="xl" color="orange.400" />
      </Box>
    );
  }

  return (
    <VStack spacing={6} align="stretch">
      {/* Header */}
      <HStack justify="space-between">
        <Text fontSize="2xl" fontWeight="bold" color="gray.100">
          Credentials Management
        </Text>
        <HStack>
          <Button
            leftIcon={<RepeatIcon />}
            onClick={loadCredentials}
            variant="outline"
            colorScheme="orange"
            size="sm"
          >
            Refresh
          </Button>
          <Button
            leftIcon={<ExternalLinkIcon />}
            onClick={onOpen}
            colorScheme="orange"
            size="sm"
          >
            Upload Credentials
          </Button>
        </HStack>
      </HStack>

      {/* Info Alert */}
      <Alert status="info" bg="blue.900" borderRadius="md">
        <AlertIcon />
        <Text color="gray.100" fontSize="sm">
          Manage encrypted credentials for {tenant}. Credentials are stored securely and never displayed in plain text.
        </Text>
      </Alert>

      {/* Credentials Table */}
      {credentials.length === 0 ? (
        <Alert status="warning" bg="yellow.900" borderRadius="md">
          <AlertIcon />
          <Text color="gray.100">
            No credentials configured for this tenant. Upload credentials to get started.
          </Text>
        </Alert>
      ) : (
        <VStack spacing={4} align="stretch">
          <Box bg="gray.800" borderRadius="lg" overflow="hidden">
            <Table variant="simple">
              <Thead bg="gray.700">
                <Tr>
                  <Th color="gray.300">Credential Type</Th>
                  <Th color="gray.300">Created</Th>
                  <Th color="gray.300">Last Updated</Th>
                  <Th color="gray.300">Status</Th>
                </Tr>
              </Thead>
              <Tbody>
                {credentials.map((cred) => (
                  <Tr key={cred.type}>
                    <Td color="gray.100">
                      <Badge colorScheme="blue">{cred.type}</Badge>
                    </Td>
                    <Td color="gray.300" fontSize="sm">
                      {formatDate(cred.created_at)}
                    </Td>
                    <Td color="gray.300" fontSize="sm">
                      {formatDate(cred.updated_at)}
                    </Td>
                    <Td>
                      <Badge colorScheme="green" display="flex" alignItems="center" gap={1} w="fit-content">
                        <CheckCircleIcon />
                        Configured
                      </Badge>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>

          {/* Test All Google Drive Credentials Button */}
          {credentials.some(c => c.type.startsWith('google_drive')) && (
            <HStack justify="flex-end">
              <Button
                size="sm"
                variant="outline"
                colorScheme="orange"
                onClick={() => handleTestCredential(credentials.find(c => c.type.startsWith('google_drive'))?.type || 'google_drive_credentials')}
                isLoading={testing !== null}
                loadingText="Testing..."
              >
                Test Google Drive Connection
              </Button>
            </HStack>
          )}
        </VStack>
      )}

      {/* OAuth Section */}
      <Box bg="gray.800" p={6} borderRadius="lg">
        <VStack align="stretch" spacing={4}>
          <Text fontSize="lg" fontWeight="bold" color="gray.100">
            OAuth Authentication
          </Text>
          <Text color="gray.400" fontSize="sm">
            Use OAuth for Google Drive access instead of service account credentials.
          </Text>
          <Button
            leftIcon={<ExternalLinkIcon />}
            onClick={handleStartOAuth}
            colorScheme="blue"
            size="sm"
            w="fit-content"
          >
            Start Google Drive OAuth
          </Button>
        </VStack>
      </Box>

      {/* Upload Modal */}
      <Modal isOpen={isOpen} onClose={onClose} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800">
          <ModalHeader color="gray.100">Upload Credentials</ModalHeader>
          <ModalCloseButton color="gray.400" />
          <ModalBody>
            <VStack spacing={4} align="stretch">
              <FormControl>
                <FormLabel color="gray.300">Credential Type</FormLabel>
                <Select
                  value={credentialType}
                  onChange={(e) => setCredentialType(e.target.value)}
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                >
                  <option value="google_drive">Google Drive (Service Account)</option>
                  <option value="s3">AWS S3</option>
                  <option value="azure_blob">Azure Blob Storage</option>
                </Select>
              </FormControl>

              <FormControl>
                <FormLabel color="gray.300">JSON Credentials File</FormLabel>
                <Input
                  type="file"
                  accept=".json"
                  onChange={handleFileSelect}
                  bg="gray.700"
                  color="gray.100"
                  borderColor="gray.600"
                  p={1}
                />
                {selectedFile && (
                  <Text color="gray.400" fontSize="sm" mt={2}>
                    Selected: {selectedFile.name}
                  </Text>
                )}
              </FormControl>

              <Alert status="info" bg="blue.900" borderRadius="md">
                <AlertIcon />
                <Text color="gray.100" fontSize="sm">
                  Credentials will be encrypted before storage. Only JSON files are accepted.
                </Text>
              </Alert>
            </VStack>
          </ModalBody>

          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={onClose} color="gray.300">
              Cancel
            </Button>
            <Button
              colorScheme="orange"
              onClick={handleUpload}
              isLoading={uploading}
              loadingText="Uploading..."
              isDisabled={!selectedFile}
            >
              Upload
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </VStack>
  );
}

export default CredentialsManagement;
