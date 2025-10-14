import React, { useState } from 'react';
import {
  Box, Button, Text, VStack, HStack, Alert, AlertIcon,
  Card, CardBody, CardHeader, Heading, Badge, Grid, GridItem,
  Input, Select, FormControl, FormLabel, Table, Thead, Tbody,
  Tr, Th, Td, TableContainer, Tabs, TabList, TabPanels, Tab, TabPanel
} from '@chakra-ui/react';

interface STRFile {
  [platform: string]: string[];
}

interface STRBooking {
  sourceFile: string;
  channel: string;
  listing: string;
  checkinDate: string;
  nights: number;
  guests: number;
  amountGross: number;
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
  const [files, setFiles] = useState<STRFile>({});
  const [loading, setLoading] = useState(false);
  const [realisedBookings, setRealisedBookings] = useState<STRBooking[]>([]);
  const [plannedBookings, setPlannedBookings] = useState<STRBooking[]>([]);
  const [summary, setSummary] = useState<STRSummary | null>(null);
  const [message, setMessage] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [selectedPlatform, setSelectedPlatform] = useState<string>('airbnb');

  const scanFiles = async () => {
    setLoading(true);
    setError('');
    
    try {
      const response = await fetch('/api/str/scan-files');
      const data = await response.json();
      
      if (data.success) {
        setFiles(data.files);
        setMessage(`Found ${Object.values(data.files).flat().length} STR files`);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError('Failed to scan files');
    } finally {
      setLoading(false);
    }
  };

  const processFiles = async (platform: string, filePaths: string[]) => {
    if (filePaths.length === 0) return;
    
    setLoading(true);
    setError('');
    
    try {
      const response = await fetch('/api/str/process-files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ platform, files: filePaths })
      });
      
      const data = await response.json();
      
      if (data.success) {
        setRealisedBookings(data.realised);
        setPlannedBookings(data.planned);
        setSummary(data.summary);
        setMessage(`Processed ${data.realised.length} realised, ${data.planned.length} planned bookings`);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError('Failed to process files');
    } finally {
      setLoading(false);
    }
  };

  const saveBookings = async () => {
    setLoading(true);
    setError('');
    
    try {
      const response = await fetch('/api/str/save', {
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
      setSelectedFile(file);
    }
  };

  const uploadAndProcess = async () => {
    if (!selectedFile) return;
    
    setLoading(true);
    setError('');
    
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      formData.append('platform', selectedPlatform);
      
      const response = await fetch('/api/str/upload', {
        method: 'POST',
        body: formData
      });
      
      const data = await response.json();
      
      if (data.success) {
        setRealisedBookings(data.realised);
        setPlannedBookings(data.planned);
        setSummary(data.summary);
        setMessage(`Processed ${data.realised.length} realised, ${data.planned.length} planned bookings from ${selectedFile.name}`);
        setSelectedFile(null);
      } else {
        setError(data.error);
      }
    } catch (err) {
      setError('Failed to upload and process file');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box p={4} bg="gray.800" minH="100vh">
      <VStack spacing={6} align="stretch">
        <Heading color="orange.400">STR Processor</Heading>

        {error && (
          <Alert status="error">
            <AlertIcon />
            {error}
          </Alert>
        )}
        
        {message && (
          <Alert status="success">
            <AlertIcon />
            {message}
          </Alert>
        )}

        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">File Processing</Heading>
          </CardHeader>
          <CardBody>
            <VStack spacing={4} align="stretch">
              <HStack spacing={4}>
                <Button 
                  colorScheme="orange"
                  onClick={scanFiles}
                  isLoading={loading}
                  loadingText="Scanning..."
                  flex={1}
                >
                  Scan Download Folder
                </Button>
                <Text color="gray.300">OR</Text>
                <Box flex={2}>
                  <FormControl>
                    <FormLabel color="gray.300" fontSize="sm">Upload Single File</FormLabel>
                    <HStack>
                      <Select 
                        value={selectedPlatform} 
                        onChange={(e) => setSelectedPlatform(e.target.value)}
                        bg="gray.600"
                        color="white"
                        size="sm"
                      >
                        <option value="airbnb">Airbnb</option>
                        <option value="booking">Booking.com</option>
                        <option value="direct">Direct</option>
                      </Select>
                      <Input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        onChange={handleFileUpload}
                        bg="gray.600"
                        color="white"
                        size="sm"
                      />
                      <Button
                        colorScheme="orange"
                        size="sm"
                        onClick={uploadAndProcess}
                        isDisabled={!selectedFile || loading}
                        isLoading={loading}
                      >
                        Process
                      </Button>
                    </HStack>
                  </FormControl>
                </Box>
              </HStack>
            </VStack>

            {Object.keys(files).length > 0 && (
              <Grid templateColumns="repeat(3, 1fr)" gap={4}>
                {Object.entries(files).map(([platform, filePaths]) => (
                  <GridItem key={platform}>
                    <Card bg="gray.600">
                      <CardHeader>
                        <Heading size="md" color="white">
                          {platform.toUpperCase()}
                        </Heading>
                        <Text color="gray.300" fontSize="sm">
                          {filePaths.length} files found
                        </Text>
                      </CardHeader>
                      <CardBody>
                        <VStack align="stretch" spacing={2}>
                          {filePaths.map((file, index) => (
                            <Badge key={index} colorScheme="blue" fontSize="xs">
                              {file.split('\\').pop()}
                            </Badge>
                          ))}
                          <Button
                            size="sm"
                            colorScheme="orange"
                            variant="outline"
                            onClick={() => processFiles(platform, filePaths)}
                            isDisabled={loading || filePaths.length === 0}
                          >
                            Process {platform}
                          </Button>
                        </VStack>
                      </CardBody>
                    </Card>
                  </GridItem>
                ))}
              </Grid>
            )}
          </CardBody>
        </Card>

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
                    €{summary.total_gross.toFixed(2)}
                  </Text>
                </GridItem>
                <GridItem>
                  <Text color="gray.300" fontSize="sm">Channels</Text>
                  <HStack wrap="wrap">
                    {Object.entries(summary.channels).map(([channel, count]) => (
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

        {(realisedBookings.length > 0 || plannedBookings.length > 0) && (
          <Card bg="gray.700">
            <CardHeader>
              <HStack justify="space-between">
                <Heading size="md" color="white">Review Bookings</Heading>
                <Button
                  colorScheme="orange"
                  onClick={saveBookings}
                  isLoading={loading}
                  loadingText="Saving..."
                >
                  Approve & Save to Database
                </Button>
              </HStack>
            </CardHeader>
            <CardBody>
              <Tabs variant="enclosed" colorScheme="orange">
                <TabList>
                  <Tab color="white">Realised ({realisedBookings.length})</Tab>
                  <Tab color="white">Planned ({plannedBookings.length})</Tab>
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
                              <Th color="gray.300">Nights</Th>
                              <Th color="gray.300">Guests</Th>
                              <Th color="gray.300">Amount</Th>
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
                                <Td color="white">{booking.nights}</Td>
                                <Td color="white">{booking.guests}</Td>
                                <Td color="white">€{booking.amountGross.toFixed(2)}</Td>
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
                              <Th color="gray.300">Nights</Th>
                              <Th color="gray.300">Guests</Th>
                              <Th color="gray.300">Amount</Th>
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
                                <Td color="white">{booking.nights}</Td>
                                <Td color="white">{booking.guests}</Td>
                                <Td color="white">€{booking.amountGross.toFixed(2)}</Td>
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