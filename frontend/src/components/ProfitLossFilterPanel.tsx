/**
 * ProfitLossFilterPanel Component
 *
 * Reusable filter panels for the P&L page tabs (Mutaties, BNB, Balance).
 */

import React from 'react';
import {
  HStack, VStack, Button, Text, Badge, Input, Select,
  Card, CardBody, CardHeader, Heading, Grid, GridItem,
} from '@chakra-ui/react';

// ---------------------------------------------------------------------------
// Mutaties Filter Panel
// ---------------------------------------------------------------------------

interface MutatiesFilterPanelProps {
  filters: { dateFrom: string; dateTo: string; administration: string; profitLoss: string };
  setFilters: React.Dispatch<React.SetStateAction<{ dateFrom: string; dateTo: string; administration: string; profitLoss: string }>>;
  onFetch: () => void;
  onExport: () => void;
  loading: boolean;
  filteredCount: number;
  totalCount: number;
}

export const MutatiesFilterPanel: React.FC<MutatiesFilterPanelProps> = ({
  filters, setFilters, onFetch, onExport, loading, filteredCount, totalCount,
}) => (
  <Card bg="gray.700">
    <CardHeader>
      <Heading size="md" color="white">Mutaties Filters</Heading>
    </CardHeader>
    <CardBody>
      <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
        <GridItem>
          <Text color="white" mb={2}>From Date</Text>
          <Input type="date" value={filters.dateFrom} onChange={(e) => setFilters(prev => ({ ...prev, dateFrom: e.target.value }))} bg="gray.600" color="white" />
        </GridItem>
        <GridItem>
          <Text color="white" mb={2}>To Date</Text>
          <Input type="date" value={filters.dateTo} onChange={(e) => setFilters(prev => ({ ...prev, dateTo: e.target.value }))} bg="gray.600" color="white" />
        </GridItem>
        <GridItem>
          <Text color="white" mb={2}>Administration</Text>
          <Select value={filters.administration} onChange={(e) => setFilters(prev => ({ ...prev, administration: e.target.value }))} bg="gray.600" color="white">
            <option value="all">All</option>
            <option value="GoodwinSolutions">GoodwinSolutions</option>
            <option value="PeterPrive">PeterPrive</option>
          </Select>
        </GridItem>
        <GridItem>
          <Text color="white" mb={2}>Profit/Loss</Text>
          <Select value={filters.profitLoss} onChange={(e) => setFilters(prev => ({ ...prev, profitLoss: e.target.value }))} bg="gray.600" color="white">
            <option value="all">All</option>
            <option value="Y">Y</option>
            <option value="N">N</option>
          </Select>
        </GridItem>
      </Grid>
      <HStack mt={4}>
        <Button colorScheme="orange" onClick={onFetch} isLoading={loading}>Update Mutaties</Button>
        <Button variant="outline" onClick={onExport}>Export CSV</Button>
        <Badge colorScheme="blue">{filteredCount} / {totalCount} records</Badge>
      </HStack>
    </CardBody>
  </Card>
);

// ---------------------------------------------------------------------------
// BNB Filter Panel
// ---------------------------------------------------------------------------

interface BnbFilterPanelProps {
  filters: { dateFrom: string; dateTo: string; channel: string; listing: string };
  setFilters: React.Dispatch<React.SetStateAction<{ dateFrom: string; dateTo: string; channel: string; listing: string }>>;
  onFetch: () => void;
  onExport: () => void;
  loading: boolean;
  filteredCount: number;
  totalCount: number;
}

export const BnbFilterPanel: React.FC<BnbFilterPanelProps> = ({
  filters, setFilters, onFetch, onExport, loading, filteredCount, totalCount,
}) => (
  <Card bg="gray.700">
    <CardHeader>
      <Heading size="md" color="white">BNB Filters</Heading>
    </CardHeader>
    <CardBody>
      <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
        <GridItem>
          <Text color="white" mb={2}>From Date</Text>
          <Input type="date" value={filters.dateFrom} onChange={(e) => setFilters(prev => ({ ...prev, dateFrom: e.target.value }))} bg="gray.600" color="white" />
        </GridItem>
        <GridItem>
          <Text color="white" mb={2}>To Date</Text>
          <Input type="date" value={filters.dateTo} onChange={(e) => setFilters(prev => ({ ...prev, dateTo: e.target.value }))} bg="gray.600" color="white" />
        </GridItem>
        <GridItem>
          <Text color="white" mb={2}>Channel</Text>
          <Select value={filters.channel} onChange={(e) => setFilters(prev => ({ ...prev, channel: e.target.value }))} bg="gray.600" color="white">
            <option value="all">All Channels</option>
            <option value="airbnb">Airbnb</option>
            <option value="booking.com">Booking.com</option>
            <option value="dfDirect">Direct</option>
            <option value="VRBO">VRBO</option>
          </Select>
        </GridItem>
        <GridItem>
          <Text color="white" mb={2}>Listing</Text>
          <Select value={filters.listing} onChange={(e) => setFilters(prev => ({ ...prev, listing: e.target.value }))} bg="gray.600" color="white">
            <option value="all">All Listings</option>
            <option value="Red Studio">Red Studio</option>
            <option value="Green Studio">Green Studio</option>
            <option value="Child Friendly">Child Friendly</option>
          </Select>
        </GridItem>
      </Grid>
      <HStack mt={4}>
        <Button colorScheme="orange" onClick={onFetch} isLoading={loading}>Update BNB Data</Button>
        <Button variant="outline" onClick={onExport}>Export CSV</Button>
        <Badge colorScheme="green">{filteredCount} / {totalCount} bookings</Badge>
      </HStack>
    </CardBody>
  </Card>
);

// ---------------------------------------------------------------------------
// Balance Filter Panel
// ---------------------------------------------------------------------------

interface BalanceFilterPanelProps {
  filters: { dateFrom: string; dateTo: string; administration: string; profitLoss: string };
  setFilters: React.Dispatch<React.SetStateAction<{ dateFrom: string; dateTo: string; administration: string; profitLoss: string }>>;
  onFetch: () => void;
  loading: boolean;
  recordCount: number;
}

export const BalanceFilterPanel: React.FC<BalanceFilterPanelProps> = ({
  filters, setFilters, onFetch, loading, recordCount,
}) => (
  <Card bg="gray.700">
    <CardBody>
      <HStack spacing={4} wrap="wrap">
        <VStack spacing={1}>
          <Text color="white" fontSize="sm">Date From</Text>
          <Input type="date" value={filters.dateFrom} onChange={(e) => setFilters(prev => ({ ...prev, dateFrom: e.target.value }))} bg="gray.600" color="white" size="sm" w="150px" />
        </VStack>
        <VStack spacing={1}>
          <Text color="white" fontSize="sm">Date To</Text>
          <Input type="date" value={filters.dateTo} onChange={(e) => setFilters(prev => ({ ...prev, dateTo: e.target.value }))} bg="gray.600" color="white" size="sm" w="150px" />
        </VStack>
        <VStack spacing={1}>
          <Text color="white" fontSize="sm">Administration</Text>
          <Select value={filters.administration} onChange={(e) => setFilters(prev => ({ ...prev, administration: e.target.value }))} bg="gray.600" color="white" size="sm" w="150px">
            <option value="all">All</option>
            <option value="GoodwinSolutions">GoodwinSolutions</option>
            <option value="PeterPrive">PeterPrive</option>
          </Select>
        </VStack>
        <VStack spacing={1}>
          <Text color="white" fontSize="sm">Profit/Loss</Text>
          <Select value={filters.profitLoss} onChange={(e) => setFilters(prev => ({ ...prev, profitLoss: e.target.value }))} bg="gray.600" color="white" size="sm" w="100px">
            <option value="all">All</option>
            <option value="Y">Y</option>
            <option value="N">N</option>
          </Select>
        </VStack>
        <Button colorScheme="orange" onClick={onFetch} isLoading={loading} size="sm" alignSelf="flex-end">Update Profit/Loss</Button>
        <Badge colorScheme="purple" alignSelf="flex-end">{recordCount} records</Badge>
      </HStack>
    </CardBody>
  </Card>
);
