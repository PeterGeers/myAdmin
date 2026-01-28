import React, { useState, useEffect } from 'react';
import {
  Box,
  Button,
  Card,
  CardBody,
  CardHeader,
  Grid,
  Heading,
  HStack,
  Select,
  Text,
  VStack
} from '@chakra-ui/react';
import { authenticatedGet, authenticatedPost } from '../../services/apiService';

const ToeristenbelastingReport: React.FC = () => {
  const [toeristenbelastingData, setToeristenbelastingData] = useState<any>(null);
  const [toeristenbelastingFilters, setToeristenbelastingFilters] = useState({
    year: new Date().getFullYear().toString()
  });
  const [toeristenbelastingAvailableYears, setToeristenbelastingAvailableYears] = useState<string[]>(() => {
    const currentYear = new Date().getFullYear();
    return [currentYear, currentYear - 1, currentYear - 2, currentYear - 3].map(y => y.toString());
  });
  const [toeristenbelastingLoading, setToeristenbelastingLoading] = useState(false);

  const fetchToeristenbelastingData = async () => {
    setToeristenbelastingLoading(true);
    try {
      const response = await authenticatedPost(
        '/api/toeristenbelasting/generate-report',
        { year: toeristenbelastingFilters.year }
      );
      
      const data = await response.json();
      
      if (data.success) {
        setToeristenbelastingData(data.data);
      }
    } catch (err) {
      console.error('Error fetching Toeristenbelasting data:', err);
    } finally {
      setToeristenbelastingLoading(false);
    }
  };

  const fetchToeristenbelastingAvailableYears = async () => {
    try {
      const response = await authenticatedGet('/api/toeristenbelasting/available-years');
      const data = await response.json();
      
      if (data.success) {
        setToeristenbelastingAvailableYears(data.years);
      }
    } catch (err) {
      console.error('Error fetching Toeristenbelasting available years:', err);
    }
  };

  const exportToeristenbelastingHTML = async () => {
    try {
      const response = await authenticatedPost(
        '/api/toeristenbelasting/generate-report',
        { year: toeristenbelastingFilters.year }
      );
      
      const data = await response.json();
      
      if (data.success && data.html_report) {
        const blob = new Blob([data.html_report], { type: 'text/html' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Aangifte_Toeristenbelasting_${toeristenbelastingFilters.year}.html`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      }
    } catch (err) {
      console.error('Error exporting Toeristenbelasting HTML:', err);
    }
  };

  useEffect(() => {
    fetchToeristenbelastingAvailableYears();
    fetchToeristenbelastingData();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (toeristenbelastingFilters.year) {
      fetchToeristenbelastingData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toeristenbelastingFilters.year]);

  return (
    <VStack spacing={4} align="stretch">
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">Aangifte Toeristenbelasting</Heading>
        </CardHeader>
        <CardBody>
          <VStack spacing={4} align="stretch">
            <HStack spacing={4}>
              <Box minW="150px">
                <Text color="white" mb={2} fontSize="sm">Jaar</Text>
                <Select
                  value={toeristenbelastingFilters.year}
                  onChange={(e) => setToeristenbelastingFilters(prev => ({ ...prev, year: e.target.value }))}
                  bg="gray.600"
                  color="white"
                  size="xs"
                >
                  {toeristenbelastingAvailableYears.map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </Select>
              </Box>
              <Box>
                <Button 
                  colorScheme="orange" 
                  onClick={exportToeristenbelastingHTML}
                  size="xs"
                  mt={6}
                >
                  Export HTML
                </Button>
              </Box>
            </HStack>
          </VStack>
        </CardBody>
      </Card>

      {toeristenbelastingLoading && (
        <Card bg="gray.700">
          <CardBody>
            <Text color="white">Loading...</Text>
          </CardBody>
        </Card>
      )}

      {!toeristenbelastingLoading && toeristenbelastingData && (
        <Card bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">Overzicht Aangifte {toeristenbelastingData.year}</Heading>
          </CardHeader>
          <CardBody>
            <VStack spacing={6} align="stretch">
              <Box>
                <Heading size="sm" color="orange.300" mb={3}>Contactgegevens</Heading>
                <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                  <Text color="gray.300" fontSize="sm">Functie:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.functie}</Text>
                  <Text color="gray.300" fontSize="sm">Telefoonnummer:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.telefoonnummer}</Text>
                  <Text color="gray.300" fontSize="sm">E-mailadres:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.email}</Text>
                </Grid>
              </Box>

              <Box>
                <Heading size="sm" color="orange.300" mb={3}>Periode en Accommodatie</Heading>
                <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                  <Text color="gray.300" fontSize="sm">Periode:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.periode_van} t/m {toeristenbelastingData.periode_tm}</Text>
                  <Text color="gray.300" fontSize="sm">Aantal kamers:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.aantal_kamers}</Text>
                  <Text color="gray.300" fontSize="sm">Aantal slaapplaatsen:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.aantal_slaapplaatsen}</Text>
                </Grid>
              </Box>

              <Box>
                <Heading size="sm" color="orange.300" mb={3}>Verhuurgegevens</Heading>
                <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                  <Text color="gray.300" fontSize="sm">Totaal verhuurde nachten:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.totaal_verhuurde_nachten}</Text>
                  <Text color="gray.300" fontSize="sm">Cancelled nachten:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.cancelled_nachten}</Text>
                  <Text color="gray.300" fontSize="sm">Verhuurde nachten aan inwoners:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.verhuurde_kamers_inwoners}</Text>
                  <Text color="gray.300" fontSize="sm">Totaal belastbare nachten:</Text>
                  <Text color="white" fontSize="sm" fontWeight="bold">{toeristenbelastingData.totaal_belastbare_nachten}</Text>
                  <Text color="gray.300" fontSize="sm">Kamerbezettingsgraad (%):</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.kamerbezettingsgraad}%</Text>
                  <Text color="gray.300" fontSize="sm">Bedbezettingsgraad (%):</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.bedbezettingsgraad}%</Text>
                </Grid>
              </Box>

              <Box>
                <Heading size="sm" color="orange.300" mb={3}>Financiële Gegevens</Heading>
                <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                  <Text color="gray.300" fontSize="sm">Saldo totaal ingehouden toeristenbelasting:</Text>
                  <Text color="white" fontSize="sm">€ {toeristenbelastingData.saldo_toeristenbelasting.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="gray.300" fontSize="sm">[1] Ontvangsten excl. BTW en excl. Toeristenbelasting:</Text>
                  <Text color="white" fontSize="sm">€ {toeristenbelastingData.ontvangsten_excl_btw_excl_toeristenbelasting.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="gray.300" fontSize="sm">[2] Ontvangsten logies inwoners excl. BTW:</Text>
                  <Text color="white" fontSize="sm">€ {toeristenbelastingData.ontvangsten_logies_inwoners.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="gray.300" fontSize="sm">[3] Kortingen / provisie / commissie:</Text>
                  <Text color="white" fontSize="sm">€ {toeristenbelastingData.kortingen_provisie_commissie.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="gray.300" fontSize="sm">[4] No-show omzet:</Text>
                  <Text color="white" fontSize="sm">€ {toeristenbelastingData.no_show_omzet.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="gray.300" fontSize="sm" fontWeight="bold">[5] Totaal 2 + 3 + 4:</Text>
                  <Text color="white" fontSize="sm" fontWeight="bold">€ {toeristenbelastingData.totaal_2_3_4.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="orange.300" fontSize="sm" fontWeight="bold">[6] Belastbare omzet logies ([1] - [5]):</Text>
                  <Text color="orange.300" fontSize="sm" fontWeight="bold">€ {toeristenbelastingData.belastbare_omzet_logies.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                  <Text color="yellow.300" fontSize="sm" fontWeight="bold">Verwachte belastbare omzet {parseInt(toeristenbelastingData.year) + 1}:</Text>
                  <Text color="yellow.300" fontSize="sm" fontWeight="bold">€ {toeristenbelastingData.verwachte_belastbare_omzet_volgend_jaar.toLocaleString('nl-NL', {minimumFractionDigits: 2})}</Text>
                </Grid>
              </Box>

              <Box>
                <Heading size="sm" color="orange.300" mb={3}>Ondertekening</Heading>
                <Grid templateColumns="repeat(2, 1fr)" gap={2}>
                  <Text color="gray.300" fontSize="sm">Naam:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.naam}</Text>
                  <Text color="gray.300" fontSize="sm">Plaats:</Text>
                  <Text color="white" fontSize="sm">{toeristenbelastingData.plaats}</Text>
                </Grid>
              </Box>
            </VStack>
          </CardBody>
        </Card>
      )}
    </VStack>
  );
};

export default ToeristenbelastingReport;
