import React, { useState } from 'react';
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
  useDisclosure
} from '@chakra-ui/react';

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
  const [searchResults, setSearchResults] = useState<Booking[]>([]);
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);
  const [language, setLanguage] = useState('nl');
  const [invoiceHtml, setInvoiceHtml] = useState('');
  const [loading, setLoading] = useState(false);
  const [customBilling, setCustomBilling] = useState({ name: '', address: '', city: '' });
  const [showBillingForm, setShowBillingForm] = useState(false);
  const toast = useToast();
  const { isOpen, onOpen, onClose } = useDisclosure();

  const searchBookings = async () => {
    if (!searchQuery.trim()) {
      toast({
        title: 'Error',
        description: 'Please enter a guest name or reservation code',
        status: 'error',
        duration: 3000,
        isClosable: true,
      });
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/str-invoice/search-booking?query=${encodeURIComponent(searchQuery)}`);
      const data = await response.json();

      if (data.success) {
        setSearchResults(data.bookings);
        if (data.bookings.length === 0) {
          toast({
            title: 'No Results',
            description: 'No bookings found matching your search',
            status: 'info',
            duration: 3000,
            isClosable: true,
          });
        }
      } else {
        throw new Error(data.error);
      }
    } catch (error) {
      toast({
        title: 'Search Error',
        description: error instanceof Error ? error.message : 'Failed to search bookings',
        status: 'error',
        duration: 5000,
        isClosable: true,
      });
    } finally {
      setLoading(false);
    }
  };

  const generateInvoice = async (booking: Booking) => {
    setLoading(true);
    try {
      const billingData = showBillingForm && (customBilling.name || customBilling.address || customBilling.city) 
        ? customBilling 
        : {};
      
      const response = await fetch('/api/str-invoice/generate-invoice', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          reservationCode: booking.reservationCode,
          language: language,
          customBilling: billingData
        }),
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
        
        <Alert status="warning" bg="orange.500" color="white">
          <AlertIcon />
          Search for bookings by guest name or reservation code to generate invoices
        </Alert>

        {/* Search Section */}
        <Box borderWidth={1} borderRadius="md" p={4}>
          <VStack spacing={4} align="stretch">
            <Text fontSize="lg" fontWeight="semibold">Search Bookings</Text>
            
            <HStack>
              <Input
                placeholder="Enter guest name or reservation code"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && searchBookings()}
              />
              <Select value={language} onChange={(e) => setLanguage(e.target.value)} width="150px">
                <option value="nl">Nederlands</option>
                <option value="en">English</option>
              </Select>
              <Button 
                colorScheme="blue" 
                onClick={searchBookings}
                isLoading={loading}
                loadingText="Searching..."
              >
                Search
              </Button>
            </HStack>
          </VStack>
        </Box>

        {/* Search Results */}
        {searchResults.length > 0 && (
          <Box borderWidth={1} borderRadius="md" p={4}>
            <Text fontSize="lg" fontWeight="semibold" mb={4}>
              Search Results ({searchResults.length} found)
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