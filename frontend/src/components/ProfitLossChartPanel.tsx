/**
 * ProfitLossChartPanel Component
 *
 * Pie chart and grouped P&L statement table for the Profit/Loss tab.
 */

import React from 'react';
import {
  Box, HStack, Text, Heading, Tr, Td, Th,
  Card, CardBody, CardHeader, Table, Thead, Tbody, TableContainer,
} from '@chakra-ui/react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface BalanceRecord {
  Parent: string;
  ledger: string;
  total_amount: number;
}

interface ProfitLossChartPanelProps {
  balanceData: BalanceRecord[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const ProfitLossChartPanel: React.FC<ProfitLossChartPanelProps> = ({ balanceData }) => {
  // Group data by Parent for the statement table
  const groupedData: Record<string, BalanceRecord[]> = {};
  balanceData.forEach(row => {
    const parent = row.Parent || 'N/A';
    if (!groupedData[parent]) groupedData[parent] = [];
    groupedData[parent].push(row);
  });

  const grandTotal = balanceData.reduce((sum, row) => sum + Number(row.total_amount || 0), 0);

  const tableRows: React.ReactElement[] = [];
  Object.entries(groupedData).forEach(([parent, rows]) => {
    const subtotal = rows.reduce((sum, row) => sum + Number(row.total_amount || 0), 0);

    tableRows.push(
      <Tr key={`parent-${parent}`} bg="gray.500" fontWeight="bold">
        <Td color="white" fontWeight="bold">{parent}</Td>
        <Td color="white" fontWeight="bold" textAlign="right">
          {subtotal.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
        </Td>
      </Tr>
    );

    rows.forEach((row, index) => {
      tableRows.push(
        <Tr key={`detail-${parent}-${index}`} bg={index % 2 === 0 ? 'gray.600' : 'gray.700'}>
          <Td color="white" pl={8}>&nbsp;&nbsp;{row.ledger || 'N/A'}</Td>
          <Td color="white" textAlign="right">
            {Number(row.total_amount || 0).toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
          </Td>
        </Tr>
      );
    });
  });

  tableRows.push(
    <Tr key="grand-total" bg="gray.500" fontWeight="bold" borderTop="2px" borderColor="gray.300">
      <Td color="white" fontWeight="bold">TOTAL</Td>
      <Td color="white" fontWeight="bold" textAlign="right">
        {grandTotal.toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €
      </Td>
    </Tr>
  );

  return (
    <HStack spacing={4} align="start">
      {/* Pie Chart */}
      <Card bg="gray.700">
        <CardBody>
          <ResponsiveContainer width={500} height={400}>
            <PieChart>
              <Pie
                data={balanceData.map(row => ({
                  name: row.ledger || 'N/A',
                  value: Math.abs(Number(row.total_amount || 0)),
                }))}
                cx="50%"
                cy="50%"
                innerRadius={80}
                outerRadius={160}
                paddingAngle={2}
                dataKey="value"
              >
                {balanceData.map((_entry, index) => (
                  <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number }> }) => {
                  if (active && payload && payload.length) {
                    return (
                      <Box bg="gray.700" p={2} border="1px solid" borderColor="gray.500" borderRadius="md">
                        <Text color="white" fontSize="sm">{payload[0].name}</Text>
                        <Text color="white" fontSize="sm">
                          €{Number(payload[0].value).toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                        </Text>
                      </Box>
                    );
                  }
                  return null;
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      {/* Statement Table */}
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">Profit/Loss Statement</Heading>
        </CardHeader>
        <CardBody>
          <Box maxW="400px">
            <TableContainer maxH="500px" overflowY="auto">
              <Table size="sm" variant="simple">
                <Thead position="sticky" top={0} bg="gray.600">
                  <Tr>
                    <Th color="white">Parent</Th>
                    <Th color="white" textAlign="right">Amount</Th>
                  </Tr>
                </Thead>
                <Tbody>{tableRows}</Tbody>
              </Table>
            </TableContainer>
          </Box>
        </CardBody>
      </Card>
    </HStack>
  );
};
