import React, { useState, useEffect } from 'react';
import {
  Box, Button, Text, VStack, HStack, Alert, AlertIcon,
  Card, CardBody, CardHeader, Heading, Badge, Grid, GridItem,
  Input, Select, FormControl, FormLabel, Table, Thead, Tbody,
  Tr, Th, Td, TableContainer, Tabs, TabList, TabPanels, Tab, TabPanel, Link
} from '@chakra-ui/react';
import { authenticatedPost, authenticatedFormData } from '../services/apiService';
import { useTypedTranslation } from '../hooks/useTypedTranslation';

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
  const { t } = useTypedTranslation('str');
  // Removed files state - no longer scanning download folder
  const [loading, setLoading] = useState(false);
  const [realisedBookings, setRealisedBookings] = useState<STRBooking[]>([]);
  const [plannedBookings, setPlannedBookings] = useState<STRBooking[]>([]);
  const [alreadyLoadedBookings, setAlreadyLoadedBookings] = useState<STRBooking[]>([]);
  const [summary, setSummary] = useState<STRSummary | null>(null);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
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
      const response = await authenticatedPost('/api/str/save', {
        realised: realisedBookings,
        planned: plannedBookings
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
    const files = event.target.files;
    if (!files || files.length === 0) return;

    if (selectedPlatform === 'vrbo') {
      // VRBO: accept multiple files
      const fileList = Array.from(files);
      setSelectedFiles(fileList);
      setSelectedFile(fileList[0]); // keep first for compatibility
      setError('');
    } else {
      const file = files[0];
      // Validate Payout CSV filename if payout platform is selected
      if (selectedPlatform === 'payout') {
        if (!file.name.toLowerCase().startsWith('payout_from') || !file.name.toLowerCase().endsWith('.csv')) {
          setError(t('processor.messages.invalidPayoutFormat'));
          return;
        }
      }
      setSelectedFile(file);
      setSelectedFiles([file]);
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
        
        const response = await authenticatedFormData('/api/str/import-payout', formData);
        
        const data = await response.json();
        
        if (data.success) {
          setPayoutResult(data);
          const notFoundMsg = data.summary.total_not_found > 0 ? t('processor.messages.notFoundWarning', { count: data.summary.total_not_found }) : '';
          setMessage(t('processor.messages.payoutImportSuccess', { updated: data.summary.total_updated, notFound: notFoundMsg }));
          setSelectedFile(null);
        } else {
          setError(data.error || t('processor.messages.failedToUpload'));
        }
      } else {
        // Handle regular booking files
        console.log('Starting upload to backend...');
        const formData = new FormData();
        // Support multi-file upload (VRBO needs reservations + payouts)
        for (const f of selectedFiles) {
          formData.append('file', f);
        }
        formData.append('platform', selectedPlatform);
        
        console.log('Calling: /api/str/upload');
        const response = await authenticatedFormData('/api/str/upload', formData);
        
        console.log('Response status:', response.status);
        
        const data = await response.json();
        
        if (data.success) {
          setRealisedBookings(data.realised);
          setPlannedBookings(data.planned);
          setAlreadyLoadedBookings(data.already_loaded || []);
          setSummary(data.summary);
          setMessage(t('processor.messages.processedSuccess', { 
            realised: data.realised.length, 
            planned: data.planned.length, 
            alreadyLoaded: data.already_loaded?.length || 0,
            filename: selectedFile.name 
          }));
          setSelectedFile(null);
        } else {
          setError(data.error);
        }
      }
    } catch (err) {
      setError(t('processor.messages.failedToUpload'));
    } finally {
      setLoading(false);
    }
  };

  const writeFutureData = async () => {
    setLoading(true);
    setError('');
    
    try {
      const response = await authenticatedPost('/api/str/write-future');
      
      const data = await response.json();
      
      if (data.success) {
        setMessage(`${data.message}. Summary: ${data.summary.map((s: any) => `${s.channel}/${s.listing}: €${s.amount} (${s.items} items)`).join(', ')}`);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError(t('processor.messages.failedToWriteFuture'));
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
              <Heading size="md" color="white">{t('processor.fileProcessing')}</Heading>
              <HStack spacing={2}>
                <Button
                  colorScheme="green"
                  size="sm"
                  onClick={() => setShowImportPopup(true)}
                >
                  {t('processor.importLinks')}
                </Button>
                <Button
                  colorScheme="blue"
                  onClick={writeFutureData}
                  isLoading={loading}
                  loadingText={t('processor.writing')}
                  size="sm"
                >
                  {t('processor.writeBnbFuture')}
                </Button>
              </HStack>
            </HStack>
          </CardHeader>
          <CardBody>
            <FormControl>
              <FormLabel color="gray.300">{t('processor.uploadBookingFile')}</FormLabel>
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
                  <option value="airbnb">{t('processor.platforms.airbnb')}</option>
                  <option value="booking">{t('processor.platforms.booking')}</option>
                  <option value="vrbo">{t('processor.platforms.vrbo', 'VRBO')}</option>
                  <option value="direct">{t('processor.platforms.direct')}</option>
                  <option value="payout">{t('processor.platforms.payout')}</option>
                </Select>
                <Input
                  type="file"
                  accept={selectedPlatform === 'payout' ? '.csv' : '.csv,.xlsx,.xls'}
                  multiple={selectedPlatform === 'vrbo'}
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
                  loadingText={t('processor.processing')}
                  minW="150px"
                >
                  {selectedPlatform === 'payout' ? t('processor.importPayout') : t('processor.processFile')}
                </Button>
              </HStack>
              {selectedFiles.length > 0 && (
                <Text color="green.300" fontSize="sm" mt={2}>
                  ✓ {t('processor.selectedFile')}: {selectedFiles.map(f => f.name).join(', ')}
                </Text>
              )}
              {selectedPlatform === 'vrbo' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md">
                  <AlertIcon />
                  <Box color="white" fontSize="xs">
                    <Text fontWeight="bold">VRBO Import</Text>
                    <Text>Select both Reservations CSV(s) and Payouts CSV. Files are auto-detected by header.</Text>
                  </Box>
                </Alert>
              )}
              {selectedPlatform === 'payout' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md">
                  <AlertIcon />
                  <Box color="white" fontSize="xs">
                    <Text fontWeight="bold">{t('processor.payoutInfo.title')}</Text>
                    <Text>{t('processor.payoutInfo.description')}</Text>
                    <Text mt={1}>{t('processor.payoutInfo.format')}</Text>
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
              <Heading size="sm" color="white">{t('processor.payoutResults.title')}</Heading>
            </CardHeader>
            <CardBody>
              <Grid templateColumns="repeat(3, 1fr)" gap={4} mb={4}>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.payoutResults.totalRows')}</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {payoutResult.processing.total_rows}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.payoutResults.reservations')}</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {payoutResult.processing.reservation_rows}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.payoutResults.updatesPrepared')}</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {payoutResult.processing.updates_prepared}
                  </Text>
                </GridItem>
              </Grid>

              <Grid templateColumns="repeat(3, 1fr)" gap={4}>
                <GridItem>
                  <Badge colorScheme="green" fontSize="md" p={2}>
                    ✓ {t('processor.payoutResults.updated')}: {payoutResult.summary.total_updated}
                  </Badge>
                </GridItem>
                <GridItem>
                  <Badge colorScheme="orange" fontSize="md" p={2}>
                    ⚠ {t('processor.payoutResults.notFound')}: {payoutResult.summary.total_not_found}
                  </Badge>
                </GridItem>
                <GridItem>
                  <Badge colorScheme="red" fontSize="md" p={2}>
                    ✗ {t('processor.payoutResults.errors')}: {payoutResult.summary.total_errors}
                  </Badge>
                </GridItem>
              </Grid>

              {payoutResult.database.not_found && payoutResult.database.not_found.length > 0 && (
                <Box mt={4}>
                  <Text color="gray.300" fontSize="sm" fontWeight="bold" mb={2}>
                    {t('processor.payoutResults.notFoundInDatabase')}
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
                        {t('processor.payoutResults.andMore', { count: payoutResult.database.not_found.length - 10 })}
                      </Text>
                    )}
                  </Box>
                  <Text color="gray.400" fontSize="xs" mt={2}>
                    {t('processor.payoutResults.mayBeCancelled')}
                  </Text>
                </Box>
              )}

              {payoutResult.database.errors && payoutResult.database.errors.length > 0 && (
                <Box mt={4}>
                  <Text color="red.300" fontSize="sm" fontWeight="bold" mb={2}>
                    {t('processor.payoutResults.errorsList')}
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
                  <Heading size="md">{t('processor.importDataLinks.title')}</Heading>
                  <Text color="gray.300" fontSize="sm">
                    {t('processor.importDataLinks.period', { from: dateFrom, to: dateTo })}
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
                  <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.bookingStudios')}</Text>
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
                  <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.bookingPayout')}</Text>
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
                    {t('processor.importDataLinks.financialReports')}
                  </Link>
                </Box>
                
                <Box>
                  <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.airbnb')}</Text>
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
                    {t('processor.importDataLinks.allReservations')}
                  </Link>
                </Box>
                
                <Box>
                  <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.jabakiDirect')}</Text>
                  <Box p={2} bg="blue.600" borderRadius="md">
                    {t('processor.importDataLinks.fileLocation')}
                  </Box>
                </Box>
              </VStack>
            </Box>
          </Box>
        )}

        {summary && (
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">{t('processor.summary.title')}</Heading>
            </CardHeader>
            <CardBody>
              <Grid templateColumns="repeat(4, 1fr)" gap={4}>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.summary.totalBookings')}</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {summary.total_bookings}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.summary.totalNights')}</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    {summary.total_nights}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.summary.totalGross')}</Text>
                  <Text color="white" fontSize="xl" fontWeight="bold">
                    €{summary.total_gross ? summary.total_gross.toFixed(2) : '0.00'}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">{t('processor.summary.channels')}</Text>
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
                <Heading size="md" color="white">{t('processor.reviewBookings.title')}</Heading>
                <HStack>
                  <Button
                    colorScheme="blue"
                    onClick={writeFutureData}
                    isLoading={loading}
                    loadingText={t('processor.writing')}
                    isDisabled={plannedBookings.length === 0}
                  >
                    {t('processor.writeBnbFuture')}
                  </Button>
                  <Button
                    colorScheme="orange"
                    onClick={saveBookings}
                    isLoading={loading}
                    loadingText={t('processor.reviewBookings.saving')}
                  >
                    {t('processor.reviewBookings.approveAndSave')}
                  </Button>
                </HStack>
              </HStack>
            </CardHeader>
            <CardBody>
              <Tabs variant="enclosed" colorScheme="orange">
                <TabList>
                  <Tab color="white">{t('processor.reviewBookings.realised')} ({realisedBookings.length})</Tab>
                  <Tab color="white">{t('processor.reviewBookings.planned')} ({plannedBookings.length})</Tab>
                  <Tab color="white">{t('processor.reviewBookings.alreadyLoaded')} ({alreadyLoadedBookings.length})</Tab>
                </TabList>
                <TabPanels>
                  <TabPanel p={0} pt={4}>
                    {realisedBookings.length > 0 && (
                      <TableContainer>
                        <Table size="sm" variant="simple">
                          <Thead>
                            <Tr>
                              <Th color="gray.300">{t('processor.table.channel')}</Th>
                              <Th color="gray.300">{t('processor.table.guest')}</Th>
                              <Th color="gray.300">{t('processor.table.listing')}</Th>
                              <Th color="gray.300">{t('processor.table.checkIn')}</Th>
                              <Th color="gray.300">{t('processor.table.checkOut')}</Th>
                              <Th color="gray.300">{t('processor.table.nights')}</Th>
                              <Th color="gray.300">{t('processor.table.guests')}</Th>
                              <Th color="gray.300">{t('processor.table.gross')}</Th>
                              <Th color="gray.300">{t('processor.table.fee')}</Th>
                              <Th color="gray.300">{t('processor.table.net')}</Th>
                              <Th color="gray.300">{t('processor.table.status')}</Th>
                              <Th color="gray.300">{t('processor.table.code')}</Th>
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
                                <Td color="white">
                                  {booking.channel === 'vrbo' ? (
                                    <Input size="xs" type="number" step="0.01" w="90px"
                                      defaultValue={booking.amountGross?.toFixed(2) || '0.00'}
                                      bg="gray.600" color="white" borderColor="gray.500"
                                      onBlur={async (e) => {
                                        const newGross = parseFloat(e.target.value) || 0;
                                        const channelFee = newGross * 0.25;
                                        try {
                                          const resp = await authenticatedPost('/api/str/calculate-taxes', {
                                            amountGross: newGross,
                                            checkinDate: booking.checkinDate,
                                            channelFee: channelFee,
                                          });
                                          const tax = await resp.json();
                                          if (tax.success) {
                                            const updated = [...realisedBookings];
                                            updated[index] = {
                                              ...updated[index],
                                              amountGross: Math.round(newGross * 100) / 100,
                                              amountChannelFee: Math.round(channelFee * 100) / 100,
                                              amountVat: tax.amountVat,
                                              amountTouristTax: tax.amountTouristTax,
                                              amountNett: tax.amountNett,
                                            };
                                            setRealisedBookings(updated);
                                          }
                                        } catch { /* keep current values */ }
                                      }}
                                    />
                                  ) : <>€{booking.amountGross ? booking.amountGross.toFixed(2) : '0.00'}</>}
                                </Td>
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
                              <Th color="gray.300">{t('processor.table.channel')}</Th>
                              <Th color="gray.300">{t('processor.table.guest')}</Th>
                              <Th color="gray.300">{t('processor.table.listing')}</Th>
                              <Th color="gray.300">{t('processor.table.checkIn')}</Th>
                              <Th color="gray.300">{t('processor.table.checkOut')}</Th>
                              <Th color="gray.300">{t('processor.table.nights')}</Th>
                              <Th color="gray.300">{t('processor.table.guests')}</Th>
                              <Th color="gray.300">{t('processor.table.gross')}</Th>
                              <Th color="gray.300">{t('processor.table.fee')}</Th>
                              <Th color="gray.300">{t('processor.table.net')}</Th>
                              <Th color="gray.300">{t('processor.table.status')}</Th>
                              <Th color="gray.300">{t('processor.table.code')}</Th>
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
                              <Th color="gray.300">{t('processor.table.channel')}</Th>
                              <Th color="gray.300">{t('processor.table.guest')}</Th>
                              <Th color="gray.300">{t('processor.table.listing')}</Th>
                              <Th color="gray.300">{t('processor.table.checkIn')}</Th>
                              <Th color="gray.300">{t('processor.table.checkOut')}</Th>
                              <Th color="gray.300">{t('processor.table.nights')}</Th>
                              <Th color="gray.300">{t('processor.table.guests')}</Th>
                              <Th color="gray.300">{t('processor.table.gross')}</Th>
                              <Th color="gray.300">{t('processor.table.fee')}</Th>
                              <Th color="gray.300">{t('processor.table.net')}</Th>
                              <Th color="gray.300">{t('processor.table.status')}</Th>
                              <Th color="gray.300">{t('processor.table.code')}</Th>
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