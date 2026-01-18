import React, { useState, useEffect } from 'react';
import {
  Box, Button, Text, VStack, HStack, Alert, AlertIcon,
  Card, CardBody, CardHeader, Heading, Badge, Grid, GridItem,
  Input, Select, FormControl, FormLabel, Table, Thead, Tbody,
  Tr, Th, Td, TableContainer, Tabs, TabList, TabPanels, Tab, TabPanel, Link
} from '@chakra-ui/react';

interface STRBooking {
  sourceFile: string;
  channel: string;
  listing: string;
  checkinDate: string;
  checkoutDate?: string;
  nights: number;
  guests?: number;
  amountGross: number;
  amountChannelFee?: number;
  amountNett?: number;
  guestName: string;
  reservationCode: string;
  status: string;
}

interface STRSummary {
  total_bookings: number;
  total_nights: number;
  total_gross: number;
  channels: { [key: string]: number };
}

const STRProcessor: React.FC = () => {
  // Removed files state - no longer scanning download folder
  const [loading, setLoading] = useState(false);
  const [realisedBookings, setRealisedBookings] = useState<STRBooking[]>([]);
  const [plannedBookings, setPlannedBookings] = useState<STRBooking[]>([]);
  const [alreadyLoadedBookings, setAlreadyLoadedBookings] = useState<STRBooking[]>([]);
  const [summary, setSummary] = useState<STRSummary | null>(null);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedPlatform, setSelectedPlatform] = useState<string>('airbnb');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [showImportPopup, setShowImportPopup] = useState<boolean>(false);
  const [payoutResult, setPayoutResult] = useState<any>(null);

  useEffect(() => {
    const now = new Date();
    const oneMonthAgo = new Date(now);
    oneMonthAgo.setMonth(now.getMonth() - 1);
    const twelveMonthsFuture = new Date(now);
    twelveMonthsFuture.setMonth(now.getMonth() + 12);
    
    setDateFrom(oneMonthAgo.toISOString().split('T')[0]);
    setDateTo(twelveMonthsFuture.toISOString().split('T')[0]);
  }, []);

  const generateBookingUrl = (hotelId: string) => {
    const baseUrl = "https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/search_reservations.html";
    const params = new URLSearchParams({
      upcoming_reservations: '1',
      source: 'nav',
      hotel_id: hotelId,
      lang: 'en',
      ses: '3e915e852e81630c46774e403f6c181e',
      date_from: dateFrom,
      date_to: dateTo,
      date_type: 'arrival'
    });
    return `${baseUrl}?${params.toString()}`;
  };

  const accommodations = [
    { id: '5615303', name: 'Red Studio', color: 'red' },
    { id: '5620035', name: 'Green Studio', color: 'green' },
    { id: '4392906', name: 'Child Friendly', color: 'blue' }
  ];

  // Removed scanFiles and processFiles functions - using single file upload only

  const saveBookings = async () => {
    setLoading(true);
    setError('');
    
    try {
      const response = await fetch('http://localhost:5000/api/str/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          realised: realisedBookings,
          planned: plannedBookings
        })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setMessage(data.message);
        setRealisedBookings([]);
        setPlannedBookings([]);
        setAlreadyLoadedBookings([]);
        setSummary(null);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError('Failed to save bookings');
    } finally {
      setLoading(false);
    }
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      // Validate Payout CSV filename if payout platform is selected
      if (selectedPlatform === 'payout') {
        if (!file.name.toLowerCase().startsWith('payout_from') || !file.name.toLowerCase().endsWith('.csv')) {
          setError('Invalid Payout file format. Expected: Payout_from_YYYY-MM-DD_until_YYYY-MM-DD.csv');
          return;
        }
      }
      setSelectedFile(file);
      setError('');
    }
  };

  const uploadAndProcess = async () => {
    if (!selectedFile) return;
    
    setLoading(true);
    setError('');
    setPayoutResult(null);
    
    try {
      // Handle Payout CSV separately
      if (selectedPlatform === 'payout') {
        console.log('Uploading Payout CSV to backend...');
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        const response = await fetch('http://localhost:5000/api/str/import-payout', {
          method: 'POST',
          body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
          setPayoutResult(data);
          setMessage(`✅ Payout import successful! Updated ${data.summary.total_updated} bookings. ${data.summary.total_not_found > 0 ? `⚠️ ${data.summary.total_not_found} reservations not found in database.` : ''}`);
          setSelectedFile(null);
        } else {
          setError(data.error || 'Failed to import Payout CSV');
        }
      } else {
        // Handle regular booking files
        console.log('Starting upload to backend...');
        const formData = new FormData();
        formData.append('file', selectedFile);
        formData.append('platform', selectedPlatform);
        
        console.log('Calling:', 'http://localhost:5000/api/str/upload');
        const response = await fetch('http://localhost:5000/api/str/upload', {
          method: 'POST',
          body: formData
        });
        
        console.log('Response status:', response.status);
        
        const data = await response.json();
        
        if (data.success) {
          setRealisedBookings(data.realised);
          setPlannedBookings(data.planned);
          setAlreadyLoadedBookings(data.already_loaded || []);
          setSummary(data.summary);
          setMessage(`Processed ${data.realised.length} realised, ${data.planned.length} planned, ${data.already_loaded?.length || 0} already loaded bookings from ${selectedFile.name}`);
          setSelectedFile(null);
        } else {
          setError(data.error);
        }
      }
    } catch (err) {
      setError('Failed to upload and process file');
    } finally {
      setLoading(false);
    }
  };

  const writeFutureData = async () => {
    setLoading(true);
    setError('');
    
    try {
      const response = await fetch('http://localhost:5000/api/str/write-future', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      const data = await response.json();
      
      if (data.success) {
        setMessage(`${data.message}. Summary: ${data.summary.map((s: any) => `${s.channel}/${s.listing}: €${s.amount} (${s.items} items)`).join(', ')}`);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError('Failed to write BNB future data');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box p={4} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">

        {error && (
          <Alert status="error">
            <AlertIcon />
            {error}
          </Alert>
        )}
        
        {message && (
          <Alert status="success">
            <AlertIcon />
            <Text color="black">{message}</Text>
          </Alert>
        )}

        <Card bg="gray.700">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">File Processing</Heading>
              <HStack spacing={2}>
                <Button
                  colorScheme="green"
                  size="sm"
                  onClick={() => setShowImportPopup(true)}
                >
                  Import Links
                </Button>
                <Button
                  colorScheme="blue"
                  onClick={writeFutureData}
                  isLoading={loading}
                  loadingText="Writing..."
                  size="sm"
                >
                  Write BNB Future
                </Button>
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <FormControl>
              <FormLabel color="gray.300">Upload Booking File</FormLabel>
              <HStack spacing={3}>
                <Select 
                  value={selectedPlatform} 
                  onChange={(e) => {
                    setSelectedPlatform(e.target.value);
                    setSelectedFile(null); // Clear file when platform changes
                    setError('');
                  }}
                  bg="gray.600"
                  color="white"
                  maxW="220px"
                >
                  <option value="airbnb">Airbnb</option>
                  <option value="booking">Booking.com Excel</option>
                  <option value="direct">Direct</option>
                  <option value="payout">Booking.com Payout</option>
                </Select>
                <Input
                  type="file"
                  accept={selectedPlatform === 'payout' ? '.csv' : '.csv,.xlsx,.xls'}
                  onChange={handleFileUpload}
                  bg="gray.600"
                  color="white"
                  key={selectedPlatform} // Force re-render when platform changes
                />
                <Button
                  colorScheme={selectedPlatform === 'payout' ? 'purple' : 'orange'}
                  onClick={uploadAndProcess}
                  isDisabled={!selectedFile || loading}
                  isLoading={loading}
                  loadingText="Processing..."
                  minW="150px"
                >
                  {selectedPlatform === 'payout' ? 'Import Payout' : 'Process File'}
                </Button>
              </HStack>
              {selectedFile && (
                <Text color="green.300" fontSize="sm" mt={2}>
                  ✓ Selected: {selectedFile.name}
                </Text>
              )}
              {selectedPlatform === 'payout' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md">
                  <AlertIcon />
                  <Box color="white" fontSize="xs">
                    <Text fontWeight="bold">Payout CSV Import:</Text>
                    <Text>Upload monthly Payout CSV to update bookings with actual financial figures</Text>
                    <Text mt={1}>Expected format: Payout_from_YYYY-MM-DD_until_YYYY-MM-DD.csv</Text>
                  </Box>
                </Alert>
              )}
            </FormControl>
          </CardBody>
        </Card>

        {/* Show Payout Results if available */}
        {payoutResult && (
          <Card bg="gray.600" borderColor="purple.500" borderWidth="2px">
            <CardHeader>
              <Heading size="sm" color="white">Payout Import Results</Heading>
            </CardHeader>
            <CardBody>
              <Grid templateColumns="repeat(3, 1fr)" gap={4} mb={4}>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Total Rows</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {payoutResult.processing.total_rows}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Reservations</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {payoutResult.processing.reservation_rows}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Updates Prepared</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {payoutResult.processing.updates_prepared}
                  </Text>
                </GridItem>
              </Grid>

              <Grid templateColumns="repeat(3, 1fr)" gap={4}>
                <GridItem>
                  <Badge colorScheme="green" fontSize="md" p={2}>
                    ✓ Updated: {payoutResult.summary.total_updated}
                  </Badge>
                </GridItem>
                <GridItem>
                  <Badge colorScheme="orange" fontSize="md" p={2}>
                    ⚠ Not Found: {payoutResult.summary.total_not_found}
                  </Badge>
                </GridItem>
                <GridItem>
                  <Badge colorScheme="red" fontSize="md" p={2}>
                    ✗ Errors: {payoutResult.summary.total_errors}
                  </Badge>
                </GridItem>
              </Grid>

              {payoutResult.database.not_found && payoutResult.database.not_found.length > 0 && (
                <Box mt={4}>
                  <Text color="gray.300" fontSize="sm" fontWeight="bold" mb={2}>
                    Reservations Not Found in Database:
                  </Text>
                  <Box 
                    bg="gray.700" 
                    p={3} 
                    borderRadius="md" 
                    maxH="150px" 
                    overflowY="auto"
                  >
                    {payoutResult.database.not_found.slice(0, 10).map((code: string, idx: number) => (
                      <Text key={idx} color="orange.300" fontSize="xs">
                        • {code}
                      </Text>
                    ))}
                    {payoutResult.database.not_found.length > 10 && (
                      <Text color="gray.400" fontSize="xs" mt={2}>
                        ... and {payoutResult.database.not_found.length - 10} more
                      </Text>
                    )}
                  </Box>
                  <Text color="gray.400" fontSize="xs" mt={2}>
                    These reservations may be cancelled bookings, test bookings, or from other properties.
                  </Text>
                </Box>
              )}

              {payoutResult.database.errors && payoutResult.database.errors.length > 0 && (
                <Box mt={4}>
                  <Text color="red.300" fontSize="sm" fontWeight="bold" mb={2}>
                    Errors:
                  </Text>
                  <Box bg="red.900" p={3} borderRadius="md">
                    {payoutResult.database.errors.map((error: string, idx: number) => (
                      <Text key={idx} color="red.200" fontSize="xs">
                        • {error}
                      </Text>
                    ))}
                  </Box>
                </Box>
              )}
            </CardBody>
          </Card>
        )}

        {showImportPopup && (
          <Box
            position="fixed"
            top={0}
            left={0}
            width="100%"
            height="100%"
            bg="rgba(0,0,0,0.4)"
            zIndex={1000}
            onClick={() => setShowImportPopup(false)}
          >
            <Box
              bg="gray.700"
              margin="15% auto"
              padding={5}
              border="1px solid #888"
              width="50%"
              borderRadius="8px"
              color="white"
              onClick={(e) => e.stopPropagation()}
            >
              <HStack justify="space-between" mb={4}>
                <Box>
                  <Heading size="md">Import Data Links</Heading>
                  <Text color="gray.300" fontSize="sm">
                    Period: {dateFrom} to {dateTo}
                  </Text>
                </Box>
                <Button
                  size="sm"
                  variant="ghost"
                  color="gray.400"
                  onClick={() => setShowImportPopup(false)}
                  fontSize="20px"
                >
                  ×
                </Button>
              </HStack>
              
              <VStack spacing={4} align="stretch">
                <Box>
                  <Text fontWeight="bold" mb={2}>Booking.com Studios:</Text>
                  <VStack spacing={2}>
                    {accommodations.map((acc) => (
                      <Link
                        key={acc.id}
                        href={generateBookingUrl(acc.id)}
                        isExternal
                        w="full"
                        p={2}
                        bg="gray.600"
                        borderRadius="md"
                        textDecoration="none"
                        _hover={{ bg: 'gray.500' }}
                      >
                        {acc.name}
                      </Link>
                    ))}
                  </VStack>
                </Box>
                
                <Box>
                  <Text fontWeight="bold" mb={2}>Booking.com Payout:</Text>
                  <Link
                    href="https://admin.booking.com/hotel/hoteladmin/groups/finance/financial-reports.html?lang=en&ses=09e4df8beca29c56616bb0d50937218e"
                    isExternal
                    w="full"
                    p={2}
                    bg="purple.600"
                    borderRadius="md"
                    textDecoration="none"
                    _hover={{ bg: 'purple.500' }}
                    display="block"
                  >
                    Financial Reports (Download monthly Payout CSV)
                  </Link>
                </Box>
                
                <Box>
                  <Text fontWeight="bold" mb={2}>Airbnb:</Text>
                  <Link
                    href="https://www.airbnb.nl/hosting/reservations/all"
                    isExternal
                    w="full"
                    p={2}
                    bg="gray.600"
                    borderRadius="md"
                    textDecoration="none"
                    _hover={{ bg: 'gray.500' }}
                    display="block"
                  >
                    Alles (Select period & download BTW factuur)
                  </Link>
                </Box>
                
                <Box>
                  <Text fontWeight="bold" mb={2}>JaBaKi Direct:</Text>
                  <Box p={2} bg="blue.600" borderRadius="md">
                    File already at: C:\Users\peter\OneDrive\R\AirBnB\data
                  </Box>
                </Box>
              </VStack>
            </Box>
          </Box>
        )}

        {summary && (
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">Summary</Heading>
            </CardHeader>
            <CardBody>
              <Grid templateColumns="repeat(4, 1fr)" gap={4}>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Total Bookings</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {summary.total_bookings}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Total Nights</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {summary.total_nights}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Total Gross</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    €{summary.total_gross ? summary.total_gross.toFixed(2) : '0.00'}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Channels</Text>
                  <HStack wrap="wrap">
                    {summary.channels && Object.entries(summary.channels).map(([channel, count]) => (
                      <Badge key={channel} colorScheme="green">
                        {channel}: {count}
                      </Badge>
                    ))}
                  </HStack>
                </GridItem>
              </Grid>
            </CardBody>
          </Card>
        )}

        {(realisedBookings.length > 0 || plannedBookings.length > 0 || alreadyLoadedBookings.length > 0) && (
          <Card bg="gray.700">
            <CardHeader>
              <HStack justify="space-between">
                <Heading size="md" color="white">Review Bookings</Heading>
                <HStack>
                  <Button
                    colorScheme="blue"
                    onClick={writeFutureData}
                    isLoading={loading}
                    loadingText="Writing..."
                    isDisabled={plannedBookings.length === 0}
                  >
                    Write BNB Future
                  </Button>
                  <Button
                    colorScheme="orange"
                    onClick={saveBookings}
                    isLoading={loading}
                    loadingText="Saving..."
                  >
                    Approve & Save to Database
                  </Button>
                </HStack>
              </HStack>
            </CardHeader>
            <CardBody>
              <Tabs variant="enclosed" colorScheme="orange">
                <TabList>
                  <Tab color="white">Realised ({realisedBookings.length})</Tab>
                  <Tab color="white">Planned ({plannedBookings.length})</Tab>
                  <Tab color="white">Already Loaded ({alreadyLoadedBookings.length})</Tab>
                </TabList>
                <TabPanels>
                  <TabPanel p={0} pt={4}>
                    {realisedBookings.length > 0 && (
                      <TableContainer>
                        <Table size="sm" variant="simple">
                          <Thead>
                            <Tr>
                              <Th color="gray.300">Channel</Th>
                              <Th color="gray.300">Guest</Th>
                              <Th color="gray.300">Listing</Th>
                              <Th color="gray.300">Check-in</Th>
                              <Th color="gray.300">Check-out</Th>
                              <Th color="gray.300">Nights</Th>
                              <Th color="gray.300">Guests</Th>
                              <Th color="gray.300">Gross</Th>
                              <Th color="gray.300">Fee</Th>
                              <Th color="gray.300">Net</Th>
                              <Th color="gray.300">Status</Th>
                              <Th color="gray.300">Code</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {realisedBookings.map((booking, index) => (
                              <Tr key={index}>
                                <Td color="white">{booking.channel}</Td>
                                <Td color="white">{booking.guestName}</Td>
                                <Td color="white">{booking.listing}</Td>
                                <Td color="white">{booking.checkinDate}</Td>
                                <Td color="white">{booking.checkoutDate}</Td>
                                <Td color="white">{booking.nights}</Td>
                                <Td color="white">{booking.guests || 0}</Td>
                                <Td color="white">€{booking.amountGross ? booking.amountGross.toFixed(2) : '0.00'}</Td>
                                <Td color="white">€{booking.amountChannelFee ? booking.amountChannelFee.toFixed(2) : '0.00'}</Td>
                                <Td color="white">€{booking.amountNett ? booking.amountNett.toFixed(2) : '0.00'}</Td>
                                <Td color="white">{booking.status}</Td>
                                <Td color="white">{booking.reservationCode}</Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      </TableContainer>
                    )}
                  </TabPanel>
                  <TabPanel p={0} pt={4}>
                    {plannedBookings.length > 0 && (
                      <TableContainer>
                        <Table size="sm" variant="simple">
                          <Thead>
                            <Tr>
                              <Th color="gray.300">Channel</Th>
                              <Th color="gray.300">Guest</Th>
                              <Th color="gray.300">Listing</Th>
                              <Th color="gray.300">Check-in</Th>
                              <Th color="gray.300">Check-out</Th>
                              <Th color="gray.300">Nights</Th>
                              <Th color="gray.300">Guests</Th>
                              <Th color="gray.300">Gross</Th>
                              <Th color="gray.300">Fee</Th>
                              <Th color="gray.300">Net</Th>
                              <Th color="gray.300">Status</Th>
                              <Th color="gray.300">Code</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {plannedBookings.map((booking, index) => (
                              <Tr key={index}>
                                <Td color="white">{booking.channel}</Td>
                                <Td color="white">{booking.guestName}</Td>
                                <Td color="white">{booking.listing}</Td>
                                <Td color="white">{booking.checkinDate}</Td>
                                <Td color="white">{booking.checkoutDate}</Td>
                                <Td color="white">{booking.nights}</Td>
                                <Td color="white">{booking.guests || 0}</Td>
                                <Td color="white">€{booking.amountGross ? booking.amountGross.toFixed(2) : '0.00'}</Td>
                                <Td color="white">€{booking.amountChannelFee ? booking.amountChannelFee.toFixed(2) : '0.00'}</Td>
                                <Td color="white">€{booking.amountNett ? booking.amountNett.toFixed(2) : '0.00'}</Td>
                                <Td color="white">{booking.status}</Td>
                                <Td color="white">{booking.reservationCode}</Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      </TableContainer>
                    )}
                  </TabPanel>
                  <TabPanel p={0} pt={4}>
                    {alreadyLoadedBookings.length > 0 && (
                      <TableContainer>
                        <Table size="sm" variant="simple">
                          <Thead>
                            <Tr>
                              <Th color="gray.300">Channel</Th>
                              <Th color="gray.300">Guest</Th>
                              <Th color="gray.300">Listing</Th>
                              <Th color="gray.300">Check-in</Th>
                              <Th color="gray.300">Check-out</Th>
                              <Th color="gray.300">Nights</Th>
                              <Th color="gray.300">Guests</Th>
                              <Th color="gray.300">Gross</Th>
                              <Th color="gray.300">Fee</Th>
                              <Th color="gray.300">Net</Th>
                              <Th color="gray.300">Status</Th>
                              <Th color="gray.300">Code</Th>
                            </Tr>
                          </Thead>
                          <Tbody>
                            {alreadyLoadedBookings.map((booking, index) => (
                              <Tr key={index}>
                                <Td color="white">{booking.channel}</Td>
                                <Td color="white">{booking.guestName}</Td>
                                <Td color="white">{booking.listing}</Td>
                                <Td color="white">{booking.checkinDate}</Td>
                                <Td color="white">{booking.checkoutDate}</Td>
                                <Td color="white">{booking.nights}</Td>
                                <Td color="white">{booking.guests || 0}</Td>
                                <Td color="white">€{booking.amountGross ? booking.amountGross.toFixed(2) : '0.00'}</Td>
                                <Td color="white">€{booking.amountChannelFee ? booking.amountChannelFee.toFixed(2) : '0.00'}</Td>
                                <Td color="white">€{booking.amountNett ? booking.amountNett.toFixed(2) : '0.00'}</Td>
                                <Td color="white">{booking.status}</Td>
                                <Td color="white">{booking.reservationCode}</Td>
                              </Tr>
                            ))}
                          </Tbody>
                        </Table>
                      </TableContainer>
                    )}
                  </TabPanel>
                </TabPanels>
              </Tabs>
            </CardBody>
          </Card>
        )}
      </VStack>
    </Box>
  );
};

export default STRProcessor;