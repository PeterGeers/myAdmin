/**
 * STRProcessor Component
 *
 * Main page for processing STR (Short-Term Rental) booking files.
 * Handles file upload, platform selection, and delegates display
 * to STRBookingTable and STRSummaryPanel sub-components.
 */

import React, { useState, useEffect } from 'react';
import {
  Box, Button, Text, VStack, HStack, Alert, AlertIcon,
  Card, CardBody, CardHeader, Heading,
  Input, Select, FormControl, FormLabel,
  Tabs, TabList, TabPanels, Tab, TabPanel, Link,
} from '@chakra-ui/react';
import { authenticatedPost, authenticatedFormData } from '../services/apiService';
import { useTypedTranslation } from '../hooks/useTypedTranslation';
import { STRBookingTable, STRBooking } from './STRBookingTable';
import { STRSummaryPanel, STRPayoutResultsPanel, STRSummary } from './STRSummaryPanel';

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const STRProcessor: React.FC = () => {
  const { t } = useTypedTranslation('str');
  const [loading, setLoading] = useState(false);
  const [realisedBookings, setRealisedBookings] = useState<STRBooking[]>([]);
  const [plannedBookings, setPlannedBookings] = useState<STRBooking[]>([]);
  const [alreadyLoadedBookings, setAlreadyLoadedBookings] = useState<STRBooking[]>([]);
  const [summary, setSummary] = useState<STRSummary | null>(null);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [warning, setWarning] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [selectedPlatform, setSelectedPlatform] = useState<string>('airbnb');
  const [dateFrom, setDateFrom] = useState<string>('');
  const [dateTo, setDateTo] = useState<string>('');
  const [showImportPopup, setShowImportPopup] = useState<boolean>(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    if (selectedPlatform === 'vrbo' || selectedPlatform === 'booking' || selectedPlatform === 'airbnb') {
      const fileList = Array.from(files);
      setSelectedFiles(fileList);
      setSelectedFile(fileList[0]);
      setError('');
    } else {
      const file = files[0];
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
    setWarning('');
    setPayoutResult(null);

    try {
      if (selectedPlatform === 'payout') {
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
        const formData = new FormData();
        for (const f of selectedFiles) formData.append('file', f);
        formData.append('platform', selectedPlatform);
        const response = await authenticatedFormData('/api/str/upload', formData);
        const data = await response.json();
        if (data.success) {
          setRealisedBookings(data.realised);
          setPlannedBookings(data.planned);
          setAlreadyLoadedBookings(data.already_loaded || []);
          setSummary(data.summary);
          if ((selectedPlatform === 'booking' || selectedPlatform === 'airbnb') && selectedFiles.length > 1) {
            setMessage(t('processor.messages.multiFileProcessedSuccess', { fileCount: selectedFiles.length, realised: data.realised.length, planned: data.planned.length, alreadyLoaded: data.already_loaded?.length || 0 }));
          } else {
            setMessage(t('processor.messages.processedSuccess', { realised: data.realised.length, planned: data.planned.length, alreadyLoaded: data.already_loaded?.length || 0, filename: selectedFile.name }));
          }
          setSelectedFile(null);
        } else {
          const errorMsg = data.error || '';
          if ((selectedPlatform === 'booking' || selectedPlatform === 'airbnb') && errorMsg.includes('failed to parse')) {
            setWarning(errorMsg);
          } else {
            setError(errorMsg);
          }
        }
      }
    } catch {
      setError(t('processor.messages.failedToUpload'));
    } finally {
      setLoading(false);
    }
  };

  const saveBookings = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await authenticatedPost('/api/str/save', { realised: realisedBookings, planned: plannedBookings });
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
    } catch {
      setError('Failed to save bookings');
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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        setMessage(`${data.message}. Summary: ${data.summary.map((s: any) => `${s.channel}/${s.listing}: €${s.amount} (${s.items} items)`).join(', ')}`);
      } else {
        setError(data.error);
      }
    } catch {
      setError(t('processor.messages.failedToWriteFuture'));
    } finally {
      setLoading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Import links
  // ---------------------------------------------------------------------------

  const generateBookingUrl = (hotelId: string) => {
    const baseUrl = "https://admin.booking.com/hotel/hoteladmin/extranet_ng/manage/search_reservations.html";
    const params = new URLSearchParams({ upcoming_reservations: '1', source: 'nav', hotel_id: hotelId, lang: 'en', ses: '3e915e852e81630c46774e403f6c181e', date_from: dateFrom, date_to: dateTo, date_type: 'arrival' });
    return `${baseUrl}?${params.toString()}`;
  };

  const accommodations = [
    { id: '5615303', name: 'Red Studio', color: 'red' },
    { id: '5620035', name: 'Green Studio', color: 'green' },
    { id: '4392906', name: 'Child Friendly', color: 'blue' },
  ];

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <Box p={4} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        {error && <Alert status="error"><AlertIcon />{error}</Alert>}
        {warning && <Alert status="warning"><AlertIcon /><Text color="black">{warning}</Text></Alert>}
        {message && <Alert status="success"><AlertIcon /><Text color="black">{message}</Text></Alert>}

        {/* File Upload Card */}
        <Card bg="gray.700">
          <CardHeader>
            <HStack justify="space-between">
              <Heading size="md" color="white">{t('processor.fileProcessing')}</Heading>
              <HStack spacing={2}>
                <Button colorScheme="green" size="sm" onClick={() => setShowImportPopup(true)}>
                  {t('processor.importLinks')}
                </Button>
                <Button colorScheme="blue" onClick={writeFutureData} isLoading={loading} loadingText={t('processor.writing')} size="sm">
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
                  onChange={(e) => { setSelectedPlatform(e.target.value); setSelectedFile(null); setError(''); }}
                  bg="gray.600" color="white" maxW="220px"
                >
                  <option value="airbnb">{t('processor.platforms.airbnb')}</option>
                  <option value="booking">{t('processor.platforms.booking')}</option>
                  <option value="vrbo">{t('processor.platforms.vrbo', 'VRBO')}</option>
                  <option value="direct">{t('processor.platforms.direct')}</option>
                  <option value="payout">{t('processor.platforms.payout')}</option>
                </Select>
                <Input
                  type="file"
                  accept={selectedPlatform === 'payout' || selectedPlatform === 'airbnb' ? '.csv' : '.csv,.tsv,.xlsx,.xls'}
                  multiple={selectedPlatform === 'vrbo' || selectedPlatform === 'booking' || selectedPlatform === 'airbnb'}
                  onChange={handleFileUpload}
                  bg="gray.600" color="white"
                  key={selectedPlatform}
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
                <Text color="green.300" fontSize="sm" mt={2}>✓ {t('processor.selectedFile')}: {selectedFiles.map(f => f.name).join(', ')}</Text>
              )}
              {selectedPlatform === 'vrbo' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md"><AlertIcon /><Box color="white" fontSize="xs"><Text fontWeight="bold">VRBO Import</Text><Text>Select both Reservations CSV(s) and Payouts CSV. Files are auto-detected by header.</Text></Box></Alert>
              )}
              {selectedPlatform === 'booking' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md"><AlertIcon /><Box color="white" fontSize="xs"><Text fontWeight="bold">{t('processor.bookingMultiFileInfo.title')}</Text><Text>{t('processor.bookingMultiFileInfo.description')}</Text></Box></Alert>
              )}
              {selectedPlatform === 'airbnb' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md"><AlertIcon /><Box color="white" fontSize="xs"><Text fontWeight="bold">{t('processor.airbnbMultiFileInfo.title')}</Text><Text>{t('processor.airbnbMultiFileInfo.description')}</Text></Box></Alert>
              )}
              {selectedPlatform === 'payout' && (
                <Alert status="info" mt={3} bg="blue.900" borderRadius="md"><AlertIcon /><Box color="white" fontSize="xs"><Text fontWeight="bold">{t('processor.payoutInfo.title')}</Text><Text>{t('processor.payoutInfo.description')}</Text><Text mt={1}>{t('processor.payoutInfo.format')}</Text></Box></Alert>
              )}
            </FormControl>
          </CardBody>
        </Card>

        {/* Payout Results */}
        {payoutResult && <STRPayoutResultsPanel payoutResult={payoutResult} t={t} />}

        {/* Import Links Popup */}
        {showImportPopup && (
          <ImportLinksPopup
            dateFrom={dateFrom}
            dateTo={dateTo}
            accommodations={accommodations}
            generateBookingUrl={generateBookingUrl}
            onClose={() => setShowImportPopup(false)}
            t={t}
          />
        )}

        {/* Summary */}
        <STRSummaryPanel summary={summary} t={t} />

        {/* Results Table */}
        {(realisedBookings.length > 0 || plannedBookings.length > 0 || alreadyLoadedBookings.length > 0) && (
          <Card bg="gray.700">
            <CardHeader>
              <HStack justify="space-between">
                <Heading size="md" color="white">{t('processor.reviewBookings.title')}</Heading>
                <HStack>
                  <Button colorScheme="blue" onClick={writeFutureData} isLoading={loading} loadingText={t('processor.writing')} isDisabled={plannedBookings.length === 0}>
                    {t('processor.writeBnbFuture')}
                  </Button>
                  <Button colorScheme="orange" onClick={saveBookings} isLoading={loading} loadingText={t('processor.reviewBookings.saving')}>
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
                    <STRBookingTable bookings={realisedBookings} editable onBookingsChange={setRealisedBookings} t={t} />
                  </TabPanel>
                  <TabPanel p={0} pt={4}>
                    <STRBookingTable bookings={plannedBookings} t={t} />
                  </TabPanel>
                  <TabPanel p={0} pt={4}>
                    <STRBookingTable bookings={alreadyLoadedBookings} t={t} />
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

// ---------------------------------------------------------------------------
// Import Links Popup (private sub-component)
// ---------------------------------------------------------------------------

interface ImportLinksPopupProps {
  dateFrom: string;
  dateTo: string;
  accommodations: Array<{ id: string; name: string; color: string }>;
  generateBookingUrl: (hotelId: string) => string;
  onClose: () => void;
  t: (key: string, params?: Record<string, unknown>) => string;
}

const ImportLinksPopup: React.FC<ImportLinksPopupProps> = ({ dateFrom, dateTo, accommodations, generateBookingUrl, onClose, t }) => (
  <Box position="fixed" top={0} left={0} width="100%" height="100%" bg="rgba(0,0,0,0.4)" zIndex={1000} onClick={onClose}>
    <Box bg="gray.700" margin="15% auto" padding={5} border="1px solid #888" width="50%" borderRadius="8px" color="white" onClick={(e) => e.stopPropagation()}>
      <HStack justify="space-between" mb={4}>
        <Box>
          <Heading size="md">{t('processor.importDataLinks.title')}</Heading>
          <Text color="gray.300" fontSize="sm">{t('processor.importDataLinks.period', { from: dateFrom, to: dateTo })}</Text>
        </Box>
        <Button size="sm" variant="ghost" color="gray.400" onClick={onClose} fontSize="20px">×</Button>
      </HStack>
      <VStack spacing={4} align="stretch">
        <Box>
          <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.bookingStudios')}</Text>
          <VStack spacing={2}>
            {accommodations.map((acc) => (
              <Link key={acc.id} href={generateBookingUrl(acc.id)} isExternal w="full" p={2} bg="gray.600" borderRadius="md" textDecoration="none" _hover={{ bg: 'gray.500' }}>{acc.name}</Link>
            ))}
          </VStack>
        </Box>
        <Box>
          <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.bookingPayout')}</Text>
          <Link href="https://admin.booking.com/hotel/hoteladmin/groups/finance/financial-reports.html?lang=en&ses=09e4df8beca29c56616bb0d50937218e" isExternal w="full" p={2} bg="purple.600" borderRadius="md" textDecoration="none" _hover={{ bg: 'purple.500' }} display="block">{t('processor.importDataLinks.financialReports')}</Link>
        </Box>
        <Box>
          <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.airbnb')}</Text>
          <Link href="https://www.airbnb.nl/hosting/reservations/all" isExternal w="full" p={2} bg="gray.600" borderRadius="md" textDecoration="none" _hover={{ bg: 'gray.500' }} display="block">{t('processor.importDataLinks.allReservations')}</Link>
        </Box>
        <Box>
          <Text fontWeight="bold" mb={2}>{t('processor.importDataLinks.jabakiDirect')}</Text>
          <Box p={2} bg="blue.600" borderRadius="md">{t('processor.importDataLinks.fileLocation')}</Box>
        </Box>
        <Box>
          <Text fontWeight="bold" mb={2}>VRBO:</Text>
          <VStack spacing={2}>
            <Link href="https://www.vrbo.com/nl-nl/p/calendar/617.10744968.5775196/rail/downloadBookingDetails" isExternal w="full" p={2} bg="orange.600" borderRadius="md" textDecoration="none" _hover={{ bg: 'orange.500' }} display="block">VRBO Reservations</Link>
            <Link href="https://www.vrbo.com/nl-nl/supply/financial-reporting?tab=upcoming-payouts" isExternal w="full" p={2} bg="orange.700" borderRadius="md" textDecoration="none" _hover={{ bg: 'orange.600' }} display="block">VRBO Payouts</Link>
          </VStack>
        </Box>
      </VStack>
    </Box>
  </Box>
);

export default STRProcessor;
