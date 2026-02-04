import React, { useState } from 'react';
import {
  Button,
  Card,
  CardBody,
  Text,
  VStack,
  Alert,
  AlertIcon,
  AlertTitle,
  AlertDescription,
  Box
} from '@chakra-ui/react';
import { authenticatedGet, buildEndpoint } from '../../services/apiService';

const BnbCountryBookingsReport: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{
    total_bookings: number;
    countries: number;
    regions: number;
  } | null>(null);

  const generateReport = async () => {
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await authenticatedGet(buildEndpoint('/api/bnb/generate-country-report'));
      
      console.log('Response status:', response.status);
      console.log('Response ok:', response.ok);
      
      if (!response.ok) {
        const text = await response.text();
        console.error('Error response:', text);
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const blob = await response.blob();
      console.log('Blob size:', blob.size, 'Type:', blob.type);
      
      // Download the file directly
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'country_bookings_report.html';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);

      setSuccess({
        total_bookings: 0,
        countries: 0,
        regions: 0
      });
      
    } catch (err) {
      console.error('Error generating country report:', err);
      setError('Failed to generate report. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardBody>
          <VStack spacing={4} align="stretch">
            <Box>
              <Text color="white" fontSize="lg" fontWeight="bold" mb={2}>
                🌍 Country Bookings Report
              </Text>
              <Text color="gray.300" fontSize="sm">
                Generate a comprehensive HTML report showing guest origin statistics by country and region.
              </Text>
            </Box>

            <Button
              colorScheme="orange"
              onClick={generateReport}
              isLoading={loading}
              loadingText="Generating Report..."
              size="lg"
              width="full"
            >
              Generate Country Report
            </Button>

            {error && (
              <Alert status="error" bg="red.600" color="white">
                <AlertIcon />
                <AlertTitle>Error!</AlertTitle>
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {success && (
              <Alert status="success" bg="green.600" color="white">
                <AlertIcon />
                <Box>
                  <AlertTitle>Report Downloaded Successfully!</AlertTitle>
                  <AlertDescription>
                    <Text mt={2}>
                      The country bookings report has been downloaded to your computer.
                    </Text>
                    <Text mt={2} fontSize="sm">
                      Open the HTML file in your browser to view the report.
                    </Text>
                  </AlertDescription>
                </Box>
              </Alert>
            )}

            <Box bg="gray.600" p={4} borderRadius="md">
              <Text color="white" fontSize="sm" fontWeight="bold" mb={2}>
                Report Contents:
              </Text>
              <VStack align="start" spacing={1}>
                <Text color="gray.300" fontSize="sm">• Summary statistics (total bookings, countries, regions)</Text>
                <Text color="gray.300" fontSize="sm">• Bookings by region with percentages and visual bars</Text>
                <Text color="gray.300" fontSize="sm">• Detailed country breakdown with rankings</Text>
                <Text color="gray.300" fontSize="sm">• Beautiful HTML styling with gradients and hover effects</Text>
              </VStack>
            </Box>
          </VStack>
        </CardBody>
      </Card>
    </VStack>
  );
};

export default BnbCountryBookingsReport;
