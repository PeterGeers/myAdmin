import React, { useState, useEffect, useCallback } from 'react';
import {
  Box, VStack, HStack, Button, Text, Badge, useToast,
  Table, Thead, Tbody, Tr, Th, Td, Spinner, Icon,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalCloseButton, Switch, FormControl, FormLabel, Select,
  Alert, AlertIcon, AlertDescription, Code
} from '@chakra-ui/react';
import { CheckCircleIcon, WarningIcon, InfoIcon } from '@chakra-ui/icons';
import { getSystemHealth, SystemHealth, HealthStatus } from '../../services/sysadminService';

export function HealthCheck() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [refreshInterval, setRefreshInterval] = useState(30); // seconds
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [selectedService, setSelectedService] = useState<HealthStatus | null>(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  const toast = useToast();

  const loadHealth = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getSystemHealth();
      setHealth(data);
      setLastChecked(new Date());
    } catch (error) {
      console.error('Health check error:', error);
      toast({
        title: 'Error loading health status',
        description: error instanceof Error ? error.message : 'Unknown error',
        status: 'error',
        duration: 5000,
      });
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    loadHealth();
  }, [loadHealth]);

  useEffect(() => {
    if (autoRefresh && refreshInterval > 0) {
      const interval = setInterval(() => {
        loadHealth();
      }, refreshInterval * 1000);

      return () => clearInterval(interval);
    }
  }, [autoRefresh, refreshInterval, loadHealth]);

  const handleRefresh = () => {
    loadHealth();
  };

  const handleViewDetails = (service: HealthStatus) => {
    setSelectedService(service);
    setIsDetailsOpen(true);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'green';
      case 'degraded':
        return 'yellow';
      case 'unhealthy':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return CheckCircleIcon;
      case 'degraded':
        return WarningIcon;
      case 'unhealthy':
        return WarningIcon;
      default:
        return InfoIcon;
    }
  };

  const getResponseTimeColor = (responseTime: number) => {
    if (responseTime < 500) return 'green.400';
    if (responseTime < 1000) return 'yellow.400';
    return 'red.400';
  };

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString();
  };

  const getTimeSinceLastCheck = () => {
    if (!lastChecked) return '';
    const seconds = Math.floor((Date.now() - lastChecked.getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
  };

  return (
    <Box>
      <VStack spacing={6} align="stretch">
        {/* Header Controls */}
        <HStack justify="space-between" wrap="wrap" spacing={4}>
          <VStack align="start" spacing={1}>
            <Text fontSize="2xl" fontWeight="bold" color="orange.400">
              System Health Check
            </Text>
            {lastChecked && (
              <Text fontSize="sm" color="gray.400">
                Last checked: {getTimeSinceLastCheck()}
              </Text>
            )}
          </VStack>

          <HStack spacing={4}>
            <FormControl display="flex" alignItems="center" width="auto">
              <FormLabel htmlFor="auto-refresh" mb="0" mr={2} color="gray.300" fontSize="sm">
                Auto-refresh
              </FormLabel>
              <Switch
                id="auto-refresh"
                colorScheme="orange"
                isChecked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
            </FormControl>

            {autoRefresh && (
              <Select
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(Number(e.target.value))}
                width="120px"
                size="sm"
                bg="gray.700"
                color="white"
                borderColor="gray.600"
              >
                <option value={30}>30s</option>
                <option value={60}>1m</option>
                <option value={300}>5m</option>
              </Select>
            )}

            <Button
              colorScheme="orange"
              onClick={handleRefresh}
              isLoading={loading}
              size="sm"
            >
              Refresh Now
            </Button>
          </HStack>
        </HStack>

        {/* Overall Status */}
        {health && (
          <Box
            p={6}
            bg="gray.700"
            borderRadius="lg"
            borderWidth="2px"
            borderColor={`${getStatusColor(health.overall)}.500`}
          >
            <HStack spacing={4}>
              <Icon
                as={getStatusIcon(health.overall)}
                boxSize={8}
                color={`${getStatusColor(health.overall)}.400`}
              />
              <VStack align="start" spacing={1}>
                <Text fontSize="lg" fontWeight="bold" color="white">
                  Overall Status
                </Text>
                <Badge
                  colorScheme={getStatusColor(health.overall)}
                  fontSize="md"
                  px={3}
                  py={1}
                  borderRadius="md"
                >
                  {health.overall.toUpperCase()}
                </Badge>
              </VStack>
            </HStack>
          </Box>
        )}

        {/* Service Status Table */}
        {loading && !health ? (
          <Box display="flex" justifyContent="center" p={8}>
            <VStack spacing={4}>
              <Spinner size="xl" color="orange.400" />
              <Text color="gray.400">Checking system health...</Text>
            </VStack>
          </Box>
        ) : health ? (
          <Box
            bg="gray.700"
            borderRadius="lg"
            borderWidth="1px"
            borderColor="gray.600"
            overflow="hidden"
          >
            <Table variant="simple">
              <Thead bg="gray.800">
                <Tr>
                  <Th color="gray.400">Service</Th>
                  <Th color="gray.400">Status</Th>
                  <Th color="gray.400" isNumeric>Response Time</Th>
                  <Th color="gray.400">Message</Th>
                  <Th color="gray.400">Actions</Th>
                </Tr>
              </Thead>
              <Tbody>
                {health.services.map((service) => (
                  <Tr key={service.service} _hover={{ bg: 'gray.600' }}>
                    <Td color="white" fontWeight="medium">
                      {service.service.replace('_', ' ').toUpperCase()}
                    </Td>
                    <Td>
                      <HStack spacing={2}>
                        <Icon
                          as={getStatusIcon(service.status)}
                          color={`${getStatusColor(service.status)}.400`}
                        />
                        <Badge colorScheme={getStatusColor(service.status)}>
                          {service.status}
                        </Badge>
                      </HStack>
                    </Td>
                    <Td isNumeric>
                      <Text color={getResponseTimeColor(service.responseTime)}>
                        {service.responseTime}ms
                      </Text>
                    </Td>
                    <Td color="gray.300" fontSize="sm">
                      {service.message || '-'}
                    </Td>
                    <Td>
                      <Button
                        size="sm"
                        variant="ghost"
                        colorScheme="orange"
                        onClick={() => handleViewDetails(service)}
                      >
                        View Details
                      </Button>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        ) : (
          <Alert status="error" bg="red.900" borderRadius="md">
            <AlertIcon />
            <AlertDescription color="gray.200">
              Failed to load health status. Please try refreshing.
            </AlertDescription>
          </Alert>
        )}
      </VStack>

      {/* Service Details Modal */}
      <Modal isOpen={isDetailsOpen} onClose={() => setIsDetailsOpen(false)} size="lg">
        <ModalOverlay />
        <ModalContent bg="gray.800" color="white">
          <ModalHeader color="orange.400">
            Service Details: {selectedService?.service.replace('_', ' ').toUpperCase()}
          </ModalHeader>
          <ModalCloseButton />
          <ModalBody pb={6}>
            {selectedService && (
              <VStack spacing={4} align="stretch">
                <Box>
                  <Text fontSize="sm" color="gray.400" mb={1}>Status</Text>
                  <Badge colorScheme={getStatusColor(selectedService.status)} fontSize="md">
                    {selectedService.status.toUpperCase()}
                  </Badge>
                </Box>

                <Box>
                  <Text fontSize="sm" color="gray.400" mb={1}>Response Time</Text>
                  <Text color={getResponseTimeColor(selectedService.responseTime)}>
                    {selectedService.responseTime}ms
                  </Text>
                </Box>

                <Box>
                  <Text fontSize="sm" color="gray.400" mb={1}>Message</Text>
                  <Text color="white">{selectedService.message || 'No message'}</Text>
                </Box>

                <Box>
                  <Text fontSize="sm" color="gray.400" mb={1}>Last Checked</Text>
                  <Text color="white">{formatTimestamp(selectedService.lastChecked)}</Text>
                </Box>

                {selectedService.details && Object.keys(selectedService.details).length > 0 && (
                  <Box>
                    <Text fontSize="sm" color="gray.400" mb={2}>Additional Details</Text>
                    <Box
                      bg="gray.900"
                      p={3}
                      borderRadius="md"
                      borderWidth="1px"
                      borderColor="gray.700"
                    >
                      <Code
                        display="block"
                        whiteSpace="pre"
                        bg="transparent"
                        color="green.300"
                        fontSize="sm"
                      >
                        {JSON.stringify(selectedService.details, null, 2)}
                      </Code>
                    </Box>
                  </Box>
                )}
              </VStack>
            )}
          </ModalBody>
        </ModalContent>
      </Modal>
    </Box>
  );
}

export default HealthCheck;
