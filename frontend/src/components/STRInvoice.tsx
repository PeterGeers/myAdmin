import React, { useState, useEffect, useCallback } from 'react';
import {
  Box,
  VStack,
  HStack,
  Input,
  Button,
  Text,
  Table,
  Thead,
  Tbody,
  Tr,
  Th,
  Td,
  Select,
  Alert,
  AlertIcon,
  useToast,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalBody,
  ModalCloseButton,
  useDisclosure,
  FormControl,
  FormLabel
} from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '../services/apiService';

interface Booking {
  reservationCode: string;
  guestName: string;
  channel: string;
  listing: string;
  checkinDate: string;
  checkoutDate: string;
  nights: number;
  guests: number;
  amountGross: number;
}

const STRInvoice: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [allBookings, setAllBookings] = useState<Booking[]>([]);
  const [searchResults, setSearchResults] = useState<Booking[]>([]);
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);
  const [language, setLanguage] = useState('nl');
  const [invoiceHtml, setInvoiceHtml] = useState('');
  const [loading, setLoading] = useState(false);
  const [customBilling, setCustomBilling] = useState({ name: '', address: '', city: '' });
  const [showBillingForm, setShowBillingForm] = useState(false);
  const [startDate, setStartDate] = useState(() => {
    // Default to 90 days ago
    const date = new Date();
    date.setDate(date.getDate() - 90);
    return date.toISOString().split('T')[0];
  });
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const loadAllBookings = useCallback(async () => {
    setLoading(true);
    try {
      // Use "2" to match most bookings with limit=all and startDate filter
      const response = await authenticatedGet(`/api/str-invoice/search-booking?query=2&limit=all&startDate=${startDate}`);
      const data = await response.json();

      if (data.success) {
        setAllBookings(data.bookings || []);
        setSearchResults(data.bookings || []);
        console.log(`Loaded ${data.bookings?.length || 0} bookings`);
        
        if (data.bookings && data.bookings.length > 0) {
          toast({
            title: 'Bookings Loaded',
            description: `${data.bookings.length} bookings loaded successfully`,
            status: 'success',
            duration: 2000,
            isClosable: true,
          });
        }
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      console.error('Loading error:', error);
      toast({
        title: 'Loading Error',
        description: error instanceof Error ? error.message : 'Failed to load bookings',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
      // Set empty arrays to prevent undefined errors
      setAllBookings([]);
      setSearchResults([]);
    } finally {
      setLoading(false);
    }
  }, [toast, startDate]);

  // Load all bookings on component mount and when startDate changes
  useEffect(() => {
    loadAllBookings();
  }, [loadAllBookings]);

  const searchBookings = () => {
    if (!searchQuery.trim()) {
      // If search is empty, show all bookings
      setSearchResults(allBookings);
      return;
    }

    // Filter locally from all bookings
    const query = searchQuery.toLowerCase();
    const filtered = allBookings.filter(booking => 
      booking.guestName?.toLowerCase().includes(query) ||
      booking.reservationCode?.toLowerCase().includes(query) ||
      booking.channel?.toLowerCase().includes(query) ||
      booking.listing?.toLowerCase().includes(query)
    );

    setSearchResults(filtered);

    if (filtered.length === 0) {
      toast({
        title: 'No Results',
        description: 'No bookings found matching your search',
        status: 'info',
        duration: 3000,
        isClosable: true,
      });
    }
  };

  const generateInvoice = async (booking: Booking) => {
    setLoading(true);
    try {
      const billingData = showBillingForm && (customBilling.name || customBilling.address || customBilling.city) 
        ? customBilling 
        : {};
      
      const response = await authenticatedPost('/api/str-invoice/generate-invoice', {
        reservationCode: booking.reservationCode,
        language: language,
        customBilling: billingData
      });

      const data = await response.json();

      if (data.success) {
        setInvoiceHtml(data.html);
        setSelectedBooking(booking);
        onOpen();
        toast({
          title: 'Success',
          description: 'Invoice generated successfully',
          status: 'success',
          duration: 3000,
          isClosable: true,
        });
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      toast({
        title: 'Generation Error',
        description: error instanceof Error ? error.message : 'Failed to generate invoice',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };

  const printInvoice = () => {
    const printWindow = window.open('', '_blank');
    if (printWindow) {
      printWindow.document.write(invoiceHtml);
      printWindow.document.close();
      printWindow.print();
    }
  };

  return (
    <Box p={6}>
      <VStack spacing={6} align="stretch">
        <Text fontSize="2xl" fontWeight="bold">STR Invoice Generator</Text>
        
        <Alert status="info" bg="blue.500" color="white">
          <AlertIcon />
          {loading ? 'Loading bookings...' : `${allBookings.length} bookings loaded. Use search to filter results.`}
        </Alert>

        {/* Search Section */}
        <Box borderWidth={1} borderRadius="md" p={4}>
          <VStack spacing={4} align="stretch">
            <Text fontSize="lg" fontWeight="semibold">Filter Bookings</Text>
            
            <HStack>
              <FormControl maxW="180px">
                <FormLabel fontSize="sm">Start Date</FormLabel>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  size="md"
                />
              </FormControl>
              <FormControl flex="1">
                <FormLabel fontSize="sm">Search</FormLabel>
                <Input
                  placeholder="Filter by guest name, reservation code, channel, or listing"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    // Auto-filter as user types
                    if (e.target.value.trim()) {
                      const query = e.target.value.toLowerCase();
                      const filtered = allBookings.filter(booking => 
                        booking.guestName?.toLowerCase().includes(query) ||
                        booking.reservationCode?.toLowerCase().includes(query) ||
                        booking.channel?.toLowerCase().includes(query) ||
                        booking.listing?.toLowerCase().includes(query)
                      );
                      setSearchResults(filtered);
                    } else {
                      setSearchResults(allBookings);
                    }
                  }}
                  onKeyPress={(e) => e.key === 'Enter' && searchBookings()}
                />
              </FormControl>
              <FormControl maxW="150px">
                <FormLabel fontSize="sm">Language</FormLabel>
                <Select value={language} onChange={(e) => setLanguage(e.target.value)}>
                  <option value="nl">Nederlands</option>
                  <option value="en">English</option>
                </Select>
              </FormControl>
            </HStack>
            <HStack>
              <Button 
                colorScheme="blue" 
                onClick={searchBookings}
                isLoading={loading}
                loadingText="Filtering..."
                size="sm"
              >
                Filter
              </Button>
              <Button 
                colorScheme="gray" 
                onClick={() => {
                  setSearchQuery('');
                  setSearchResults(allBookings);
                }}
                isDisabled={loading}
                size="sm"
              >
                Clear
              </Button>
              <Button 
                colorScheme="green" 
                onClick={loadAllBookings}
                isLoading={loading}
                loadingText="Reloading..."
                size="sm"
              >
                Reload
              </Button>
            </HStack>
          </VStack>
        </Box>

        {/* Loading State */}
        {loading && (
          <Box borderWidth={1} borderRadius="md" p={8} textAlign="center">
            <Text fontSize="lg" color="gray.600">Loading bookings...</Text>
          </Box>
        )}

        {/* Bookings Table - Show when data is loaded */}
        {!loading && allBookings.length > 0 && (
          <Box borderWidth={1} borderRadius="md" p={4}>
            <Text fontSize="lg" fontWeight="semibold" mb={4}>
              {searchQuery ? `Filtered Results (${searchResults.length} of ${allBookings.length})` : `All Bookings (${searchResults.length})`}
            </Text>
            
            <Table size="sm">
              <Thead>
                <Tr>
                  <Th>Reservation Code</Th>
                  <Th>Guest Name</Th>
                  <Th>Channel</Th>
                  <Th>Listing</Th>
                  <Th>Check-in</Th>
                  <Th>Nights</Th>
                  <Th>Amount</Th>
                  <Th>Action</Th>
                </Tr>
              </Thead>
              <Tbody>
                {searchResults.map((booking, index) => (
                  <Tr key={index}>
                    <Td>{booking.reservationCode}</Td>
                    <Td>{booking.guestName}</Td>
                    <Td>{booking.channel}</Td>
                    <Td>{booking.listing}</Td>
                    <Td>{booking.checkinDate}</Td>
                    <Td>{booking.nights}</Td>
                    <Td>€{booking.amountGross?.toFixed(2)}</Td>
                    <Td>
                      <VStack spacing={2}>
                        <Button
                          size="sm"
                          colorScheme="green"
                          onClick={() => {
                            setSelectedBooking(booking);
                            setShowBillingForm(true);
                          }}
                        >
                          Generate Invoice
                        </Button>
                      </VStack>
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Box>
        )}

        {/* No Data Message */}
        {!loading && allBookings.length === 0 && (
          <Box borderWidth={1} borderRadius="md" p={8} textAlign="center">
            <Text fontSize="lg" color="gray.600">No bookings found in database</Text>
          </Box>
        )}

        {/* No Results After Filter */}
        {!loading && allBookings.length > 0 && searchResults.length === 0 && searchQuery && (
          <Box borderWidth={1} borderRadius="md" p={8} textAlign="center">
            <Text fontSize="lg" color="gray.600">
              No bookings match your filter "{searchQuery}"
            </Text>
            <Button mt={4} onClick={() => {
              setSearchQuery('');
              setSearchResults(allBookings);
            }}>
              Clear Filter
            </Button>
          </Box>
        )}

        {/* Billing Form Modal */}
        <Modal isOpen={showBillingForm} onClose={() => setShowBillingForm(false)} size="md">
          <ModalOverlay />
          <ModalContent>
            <ModalHeader>Billing Address - {selectedBooking?.reservationCode}</ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6}>
              <VStack spacing={4}>
                <Text fontSize="sm" color="gray.600">
                  Leave fields empty to use default values
                </Text>
                <Input
                  placeholder={`Default: ${selectedBooking?.guestName}`}
                  value={customBilling.name}
                  onChange={(e) => setCustomBilling({...customBilling, name: e.target.value})}
                  size="sm"
                />
                <Input
                  placeholder={`Default: Via ${selectedBooking?.channel}`}
                  value={customBilling.address}
                  onChange={(e) => setCustomBilling({...customBilling, address: e.target.value})}
                  size="sm"
                />
                <Input
                  placeholder={`Default: Reservering: ${selectedBooking?.reservationCode}`}
                  value={customBilling.city}
                  onChange={(e) => setCustomBilling({...customBilling, city: e.target.value})}
                  size="sm"
                />
                <HStack spacing={4} w="full">
                  <Button
                    colorScheme="green"
                    onClick={() => {
                      if (selectedBooking) {
                        generateInvoice(selectedBooking);
                        setShowBillingForm(false);
                      }
                    }}
                    isLoading={loading}
                    flex={1}
                  >
                    Generate Invoice
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setShowBillingForm(false)}
                    flex={1}
                  >
                    Cancel
                  </Button>
                </HStack>
              </VStack>
            </ModalBody>
          </ModalContent>
        </Modal>

        {/* Invoice Preview Modal */}
        <Modal isOpen={isOpen} onClose={onClose} size="6xl">
          <ModalOverlay />
          <ModalContent maxW="90vw" maxH="90vh">
            <ModalHeader>
              Invoice Preview - {selectedBooking?.reservationCode}
              <Button
                ml={4}
                size="sm"
                colorScheme="blue"
                onClick={printInvoice}
              >
                Print Invoice
              </Button>
            </ModalHeader>
            <ModalCloseButton />
            <ModalBody pb={6} overflow="auto">
              {invoiceHtml && (
                <Box
                  dangerouslySetInnerHTML={{ __html: invoiceHtml }}
                  border="1px solid #e2e8f0"
                  borderRadius="md"
                  p={4}
                  bg="white"
                />
              )}
            </ModalBody>
          </ModalContent>
        </Modal>
      </VStack>
    </Box>
  );
};

export default STRInvoice;