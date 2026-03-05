import React from 'react';
import {
  Card,
  CardBody,
  CardHeader,
  Heading,
  Table,
  TableContainer,
  Tbody,
  Td,
  Th,
  Thead,
  Tr
} from '@chakra-ui/react';
import { useTypedTranslation } from '../../hooks/useTypedTranslation';

interface BnbYearMonthMatrixProps {
  data: any[];
  viewType: 'listing' | 'channel';
  displayFormat: string;
  selectedAmounts: string[];
}

const BnbYearMonthMatrix: React.FC<BnbYearMonthMatrixProps> = ({
  data,
  viewType,
  displayFormat,
  selectedAmounts
}) => {
  const { t } = useTypedTranslation('reports');

  // Format amount based on display format
  const formatAmount = (amount: number, format: string): string => {
    const num = Number(amount) || 0;
    
    switch (format) {
      case '2dec':
        return `€${num.toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      case '0dec':
        return `€${Math.round(num).toLocaleString('nl-NL')}`;
      case 'k':
        return `€${(num / 1000).toFixed(1)}K`;
      case 'm':
        return `€${(num / 1000000).toFixed(1)}M`;
      default:
        return `€${num.toLocaleString('nl-NL', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    }
  };

  // Group data by year and month
  const yearMonthData = data.reduce((acc, row) => {
    const year = row.year;
    const month = row.m || 1;
    
    if (!acc[year]) {
      acc[year] = {};
      for (let m = 1; m <= 12; m++) {
        acc[year][m] = {
          amountGross: 0,
          amountNett: 0,
          amountChannelFee: 0,
          amountTouristTax: 0,
          amountVat: 0
        };
      }
    }
    
    acc[year][month].amountGross += Number(row.amountGross) || 0;
    acc[year][month].amountNett += Number(row.amountNett) || 0;
    acc[year][month].amountChannelFee += Number(row.amountChannelFee) || 0;
    acc[year][month].amountTouristTax += Number(row.amountTouristTax) || 0;
    acc[year][month].amountVat += Number(row.amountVat) || 0;
    
    return acc;
  }, {} as any);

  const years = Object.keys(yearMonthData).sort((a, b) => parseInt(b) - parseInt(a));
  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  // Get the primary selected amount for display
  const primaryAmount = selectedAmounts[0] || 'amountGross';
  const amountLabel = {
    'amountGross': t('bnb.grossRevenue'),
    'amountNett': t('bnb.netRevenue'),
    'amountChannelFee': t('bnb.channelFees'),
    'amountTouristTax': t('tables.touristTax'),
    'amountVat': t('tables.vat')
  }[primaryAmount] || primaryAmount;

  return (
    <Card bg="gray.700">
      <CardHeader>
        <Heading size="md" color="white">
          {t('bnb.yearMonthOverview')} - {amountLabel}
        </Heading>
      </CardHeader>
      <CardBody>
        <TableContainer>
          <Table size="sm" variant="simple">
            <Thead>
              <Tr>
                <Th color="white" position="sticky" left={0} bg="gray.700" zIndex={1}>
                  {t('tables.year')}
                </Th>
                {monthNames.map((month, index) => (
                  <Th key={index} color="white" textAlign="right">
                    {month}
                  </Th>
                ))}
                <Th color="white" textAlign="right" fontWeight="bold">
                  {t('charts.total')}
                </Th>
              </Tr>
            </Thead>
            <Tbody>
              {years.map(year => {
                const yearData = yearMonthData[year];
                const yearTotal = Object.values(yearData).reduce(
                  (sum: number, monthData: any) => sum + (monthData[primaryAmount] || 0),
                  0
                );
                
                return (
                  <Tr key={year}>
                    <Td 
                      color="white" 
                      fontWeight="bold" 
                      position="sticky" 
                      left={0} 
                      bg="gray.700" 
                      zIndex={1}
                    >
                      {year}
                    </Td>
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(month => (
                      <Td key={month} color="white" textAlign="right">
                        {formatAmount(yearData[month]?.[primaryAmount] || 0, displayFormat)}
                      </Td>
                    ))}
                    <Td color="white" textAlign="right" fontWeight="bold" bg="gray.600">
                      {formatAmount(yearTotal, displayFormat)}
                    </Td>
                  </Tr>
                );
              })}
              {/* Total row */}
              {years.length > 0 && (
                <Tr bg="gray.600">
                  <Td 
                    color="white" 
                    fontWeight="bold" 
                    position="sticky" 
                    left={0} 
                    bg="gray.600" 
                    zIndex={1}
                  >
                    {t('charts.total')}
                  </Td>
                  {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].map(month => {
                    const monthTotal = years.reduce((sum, year) => {
                      return sum + (yearMonthData[year][month]?.[primaryAmount] || 0);
                    }, 0);
                    return (
                      <Td key={month} color="white" textAlign="right" fontWeight="bold">
                        {formatAmount(monthTotal, displayFormat)}
                      </Td>
                    );
                  })}
                  <Td color="white" textAlign="right" fontWeight="bold">
                    {formatAmount(
                      years.reduce((sum, year) => {
                        return sum + Object.values(yearMonthData[year]).reduce(
                          (yearSum: number, monthData: any) => yearSum + (monthData[primaryAmount] || 0),
                          0
                        );
                      }, 0),
                      displayFormat
                    )}
                  </Td>
                </Tr>
              )}
            </Tbody>
          </Table>
        </TableContainer>
      </CardBody>
    </Card>
  );
};

export default BnbYearMonthMatrix;
