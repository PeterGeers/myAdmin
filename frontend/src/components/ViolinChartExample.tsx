/**
 * Example usage of the Plotly Violin Chart
 * This file demonstrates how to use the ViolinChart component with sample data
 */

import React from 'react';
import Plot from 'react-plotly.js';
import { Box, VStack, Text } from '@chakra-ui/react';

// Sample data structure that matches what the API returns
const sampleData = [
  { listing: 'Apartment A', channel: 'Airbnb', value: 85.50 },
  { listing: 'Apartment A', channel: 'Airbnb', value: 92.00 },
  { listing: 'Apartment A', channel: 'Airbnb', value: 88.75 },
  { listing: 'Apartment B', channel: 'Booking.com', value: 120.00 },
  { listing: 'Apartment B', channel: 'Booking.com', value: 115.50 },
  { listing: 'Apartment B', channel: 'Airbnb', value: 110.00 },
];

export const ViolinChartExample: React.FC = () => {
  // Group data by listing
  const grouped = sampleData.reduce((acc, item) => {
    if (!acc[item.listing]) acc[item.listing] = [];
    acc[item.listing].push(item.value);
    return acc;
  }, {} as Record<string, number[]>);

  // Create Plotly traces
  const plotData = Object.entries(grouped).map(([name, values]) => ({
    type: 'violin' as const,
    y: values,
    name: name,
    box: { visible: true },
    meanline: { visible: true },
  }));

  return (
    <VStack spacing={4}>
      <Text fontSize="xl" fontWeight="bold">
        Violin Chart Example
      </Text>
      <Box w="100%" bg="white" p={4} borderRadius="md">
        <Plot
          data={plotData as any}
          layout={{
            title: 'Price Distribution by Listing',
            yaxis: { title: { text: 'Price (€)' } },
            xaxis: { title: { text: 'Listing' } },
            showlegend: false,
            height: 400,
          } as any}
          config={{
            responsive: true,
            displayModeBar: true,
            displaylogo: false,
          }}
          style={{ width: '100%' }}
        />
      </Box>
    </VStack>
  );
};
