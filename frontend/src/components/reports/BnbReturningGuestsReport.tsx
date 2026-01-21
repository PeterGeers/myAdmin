/**
 * BNB Returning Guests Report Component
 * 
 * Displays analysis of returning guests (guests with more than 1 booking):
 * - List of returning guests with booking count
 * - Expandable view to see individual guest bookings
 * - Booking details including dates, channel, listing, amounts
 * - Summary statistics per guest
 * 
 * Extracted from myAdminReports.tsx (lines 3298-3419)
 */

import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Heading,
  HStack,
  Table,
  TableContainer,
  Tbody,
  Td,
  Text,
  Th,
  Thead,
  Tr,
  VStack,
} from '@chakra-ui/react';
import { buildApiUrl } from '../../config';

interface ReturningGuest {
  guestName: string;
  aantal: number;
}

interface GuestBooking {
  checkinDate: string;
  checkoutDate: string;
  channel: string;
  listing: string;
  nights: number;
  amountGross: number;
  amountNett: number;
  reservationCode: string;
}

/**
 * Main BNB Returning Guests Report Component
 */
const BnbReturningGuestsReport: React.FC = () => {
  const [returningGuests, setReturningGuests] = useState<ReturningGuest[]>([]);
  const [selectedGuestBookings, setSelectedGuestBookings] = useState<GuestBooking[]>([]);
  const [selectedGuestName, setSelectedGuestName] = useState<string>('');
  const [returningGuestsLoading, setReturningGuestsLoading] = useState(false);

  /**
   * Fetch returning guests data from API
   */
  const fetchReturningGuests = async () => {
    setReturningGuestsLoading(true);
    try {
      const response = await fetch(buildApiUrl('/api/bnb/bnb-returning-guests'));
      const data = await response.json();
      
      if (data.success) {
        setReturningGuests(data.data);
      }
    } catch (err) {
      console.error('Error fetching returning guests:', err);
    } finally {
      setReturningGuestsLoading(false);
    }
  };

  /**
   * Fetch bookings for a specific guest
   */
  const fetchGuestBookings = async (guestName: string) => {
    try {
      const params = new URLSearchParams({ guestName });
      const response = await fetch(buildApiUrl('/api/bnb/bnb-guest-bookings', params));
      const data = await response.json();
      
      if (data.success) {
        setSelectedGuestBookings(data.data);
        setSelectedGuestName(guestName);
      }
    } catch (err) {
      console.error('Error fetching guest bookings:', err);
    }
  };

  /**
   * Handle guest row click to expand/collapse bookings
   */
  const handleGuestClick = (guestName: string) => {
    if (selectedGuestName === guestName) {
      setSelectedGuestName('');
      setSelectedGuestBookings([]);
    } else {
      fetchGuestBookings(guestName);
    }
  };

  // Initialize data on mount
  useEffect(() => {
    fetchReturningGuests();
  }, []);

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardHeader>
          <HStack justify="space-between">
            <Heading size="md" color="white">Returning Guests (Aantal &gt; 1)</Heading>
            <Text color="orange.300" fontSize="sm" fontWeight="bold">
              {returningGuests.length} guests found
            </Text>
          </HStack>
        </CardHeader>
        <CardBody>
          <Button 
            colorScheme="orange" 
            onClick={fetchReturningGuests} 
            isLoading={returningGuestsLoading}
            size="sm"
            mb={4}
          >
            Refresh Data
          </Button>
          
          <TableContainer>
            <Table size="sm" variant="simple">
              <Thead>
                <Tr>
                  <Th color="white" w="50px"></Th>
                  <Th color="white" w="80px">Aantal</Th>
                  <Th color="white">Guest Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                {returningGuests.map((guest, index) => (
                  <React.Fragment key={index}>
                    <Tr 
                      cursor="pointer"
                      _hover={{ bg: "gray.600" }}
                      bg={selectedGuestName === guest.guestName ? "gray.600" : "transparent"}
                      onClick={() => handleGuestClick(guest.guestName)}
                    >
                      <Td color="white" fontSize="sm" w="50px">
                        <Button size="xs" variant="ghost" color="white">
                          {selectedGuestName === guest.guestName ? '−' : '+'}
                        </Button>
                      </Td>
                      <Td color="white" fontSize="sm">{guest.aantal}</Td>
                      <Td color="white" fontSize="sm">{guest.guestName}</Td>
                    </Tr>
                    {selectedGuestName === guest.guestName && selectedGuestBookings.length > 0 && (
                      <Tr>
                        <Td colSpan={3} p={0}>
                          <Box bg="gray.800" p={4}>
                            <Text color="white" fontWeight="bold" mb={3}>
                              Bookings for {selectedGuestName}
                            </Text>
                            <Table size="sm" variant="simple">
                              <Thead>
                                <Tr>
                                  <Th color="white" fontSize="xs">Check-in</Th>
                                  <Th color="white" fontSize="xs">Check-out</Th>
                                  <Th color="white" fontSize="xs">Channel</Th>
                                  <Th color="white" fontSize="xs">Listing</Th>
                                  <Th color="white" fontSize="xs">Nights</Th>
                                  <Th color="white" fontSize="xs" isNumeric>Gross</Th>
                                  <Th color="white" fontSize="xs" isNumeric>Net</Th>
                                  <Th color="white" fontSize="xs">Reservation</Th>
                                </Tr>
                              </Thead>
                              <Tbody>
                                {selectedGuestBookings.map((booking, bookingIndex) => (
                                  <Tr key={bookingIndex}>
                                    <Td color="white" fontSize="xs">
                                      {new Date(booking.checkinDate).toLocaleDateString('nl-NL')}
                                    </Td>
                                    <Td color="white" fontSize="xs">
                                      {new Date(booking.checkoutDate).toLocaleDateString('nl-NL')}
                                    </Td>
                                    <Td color="white" fontSize="xs">{booking.channel}</Td>
                                    <Td color="white" fontSize="xs">{booking.listing}</Td>
                                    <Td color="white" fontSize="xs">{booking.nights}</Td>
                                    <Td color="white" fontSize="xs" isNumeric>
                                      €{Number(booking.amountGross || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                                    </Td>
                                    <Td color="white" fontSize="xs" isNumeric>
                                      €{Number(booking.amountNett || 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                                    </Td>
                                    <Td color="white" fontSize="xs">{booking.reservationCode}</Td>
                                  </Tr>
                                ))}
                              </Tbody>
                            </Table>
                            <Box mt={3} p={2} bg="gray.700" borderRadius="md">
                              <Text color="white" fontSize="sm" fontWeight="bold">
                                Total: {selectedGuestBookings.length} bookings | 
                                {selectedGuestBookings.reduce((sum, b) => sum + (Number(b.nights) || 0), 0)} nights | 
                                €{selectedGuestBookings.reduce((sum, b) => sum + (Number(b.amountGross) || 0), 0).toLocaleString('nl-NL', {minimumFractionDigits: 2})}
                              </Text>
                            </Box>
                          </Box>
                        </Td>
                      </Tr>
                    )}
                  </React.Fragment>
                ))}
              </Tbody>
            </Table>
          </TableContainer>
        </CardBody>
      </Card>

      {/* Instructions */}
      {returningGuests.length === 0 && !returningGuestsLoading && (
        <Card bg="gray.700">
          <CardBody>
            <VStack spacing={3} align="start">
              <Heading size="md" color="white">Returning Guests Instructions</Heading>
              <Text color="white" fontSize="sm">
                1. Click "Refresh Data" to load the latest returning guests data
              </Text>
              <Text color="white" fontSize="sm">
                2. The table shows guests who have made more than one booking
              </Text>
              <Text color="white" fontSize="sm">
                3. Click on any guest row to expand and view their individual bookings
              </Text>
              <Text color="white" fontSize="sm">
                4. The expanded view shows detailed booking information including dates, channels, listings, and amounts
              </Text>
              <Text color="gray.400" fontSize="xs">
                This report helps identify loyal customers and analyze their booking patterns.
              </Text>
            </VStack>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default BnbReturningGuestsReport;
