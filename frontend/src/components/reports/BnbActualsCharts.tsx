import React from 'react';
import {
  Card,
  CardBody,
  CardHeader,
  Grid,
  GridItem,
  Heading,
  Text,
  VStack
} from '@chakra-ui/react';
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import type { BnbDataRow } from './BnbActualsReport';

export interface BnbActualsChartsProps {
  data: BnbDataRow[];
  viewType: 'listing' | 'channel';
  displayFormat: string;
  selectedAmounts: string[];
  formatAmount: (amount: number, format: string) => string;
  t: (key: string) => string;
}

const BnbActualsCharts: React.FC<BnbActualsChartsProps> = ({
  data,
  viewType,
  displayFormat,
  selectedAmounts,
  formatAmount,
  t
}) => {
  return (
    <>
      {/* Revenue Trend Chart */}
      <Card bg="gray.700">
        <CardHeader>
          <Heading size="md" color="white">{t('bnb.revenueTrend')}</Heading>
        </CardHeader>
        <CardBody>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart
              data={(() => {
                const trendData = data.reduce((acc, row) => {
                  const period = `${row.year}-Q${row.q || 1}`;
                  if (!acc[period]) {
                    acc[period] = { period, year: row.year, quarter: row.q || 1 };
                    selectedAmounts.forEach(amount => {
                      acc[period][amount] = 0;
                    });
                  }
                  selectedAmounts.forEach(amount => {
                    acc[period][amount] += Number(row[amount]) || 0;
                  });
                  return acc;
                }, {} as Record<string, Record<string, unknown>>);
                return Object.values(trendData).sort((a, b) => {
                  const aObj = a as { year: number; quarter: number };
                  const bObj = b as { year: number; quarter: number };
                  if (aObj.year !== bObj.year) return aObj.year - bObj.year;
                  return aObj.quarter - bObj.quarter;
                });
              })()}
              margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="period" tick={{fill: 'white'}} />
              <YAxis tick={{fill: 'white'}} />
              <Tooltip formatter={(value) => formatAmount(Number(value), displayFormat)} />
              <Legend wrapperStyle={{color: 'white'}} />
              {selectedAmounts.map((amount, index) => {
                const amountLabel = {
                  'amountGross': t('bnb.grossRevenue'),
                  'amountNett': t('bnb.netRevenue'),
                  'amountChannelFee': t('bnb.channelFees'),
                  'amountTouristTax': t('tables.touristTax'),
                  'amountVat': t('tables.vat')
                }[amount] || amount;
                return (
                  <Line
                    key={amount}
                    type="monotone"
                    dataKey={amount}
                    stroke={`hsl(${index * 60}, 70%, 60%)`}
                    strokeWidth={2}
                    name={amountLabel}
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        </CardBody>
      </Card>

      {/* Charts Grid */}
      <Grid templateColumns={{ base: "1fr", lg: "1fr 400px" }} gap={4}>
        <GridItem>
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">
                {viewType === 'listing' ? t('bnb.listingDistribution') : t('bnb.channelDistribution')}
              </Heading>
            </CardHeader>
            <CardBody>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={(() => {
                      const primaryAmount = selectedAmounts[0] || 'amountGross';
                      const grouped = data.reduce((acc, row) => {
                        const key = row[viewType];
                        if (!acc[key]) acc[key] = 0;
                        acc[key] += Number(row[primaryAmount]) || 0;
                        return acc;
                      }, {} as Record<string, number>);
                      return Object.entries(grouped)
                        .map(([name, value]) => ({ name, value: Math.abs(Number(value)) }))
                        .filter(item => item.value > 0)
                        .sort((a, b) => b.value - a.value);
                    })()}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                    label={(entry: { name: string; percent: number }) => `${entry.name}: ${(entry.percent * 100).toFixed(1)}%`}
                  >
                    {(() => {
                      const primaryAmount = selectedAmounts[0] || 'amountGross';
                      const grouped = data.reduce((acc, row) => {
                        const key = row[viewType];
                        if (!acc[key]) acc[key] = 0;
                        acc[key] += Number(row[primaryAmount]) || 0;
                        return acc;
                      }, {} as Record<string, number>);
                      return Object.entries(grouped)
                        .map(([name, value]) => ({ name, value: Math.abs(Number(value)) }))
                        .filter(item => item.value > 0)
                        .sort((a, b) => b.value - a.value)
                        .map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
                        ));
                    })()}
                  </Pie>
                  <Tooltip formatter={(value) => formatAmount(Number(value), displayFormat)} />
                </PieChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
        </GridItem>
        
        <GridItem>
          <Card bg="gray.700">
            <CardHeader>
              <Heading size="md" color="white">{t('bnb.yearOverYearPerformance')}</Heading>
            </CardHeader>
            <CardBody>
              {(() => {
                const primaryAmount = selectedAmounts[0] || 'amountGross';
                const years = Array.from(new Set(data.map(row => row.year))).sort((a, b) => b - a);
                const currentYear = years[0];
                const previousYear = years[1];
                
                const currentTotal = data
                  .filter(row => row.year === currentYear)
                  .reduce((sum, row) => sum + (Number(row[primaryAmount]) || 0), 0);
                const previousTotal = data
                  .filter(row => row.year === previousYear)
                  .reduce((sum, row) => sum + (Number(row[primaryAmount]) || 0), 0);
                
                const percentage = previousTotal > 0 ? (currentTotal / previousTotal) * 100 : 0;
                const difference = currentTotal - previousTotal;
                
                const getColor = (pct: number) => {
                  if (pct >= 100) return '#22c55e'; // Green
                  if (pct >= 90) return '#eab308';  // Yellow
                  return '#ef4444'; // Red
                };
                
                return (
                  <VStack spacing={4}>
                    <ResponsiveContainer width="100%" height={200}>
                      <RadialBarChart
                        cx="50%"
                        cy="50%"
                        innerRadius="60%"
                        outerRadius="90%"
                        startAngle={180}
                        endAngle={0}
                        data={[
                          { name: 'background', value: 150, fill: '#1f2937' },
                          { name: 'performance', value: Math.min(percentage, 150), fill: getColor(percentage) }
                        ]}
                      >
                        <RadialBar dataKey="value" />
                        {/* Custom Needle */}
                        <g>
                          <line
                            x1="50%"
                            y1="50%"
                            x2={`${50 + 35 * Math.cos((180 - (percentage / 150) * 180) * Math.PI / 180)}%`}
                            y2={`${50 - 35 * Math.sin((180 - (percentage / 150) * 180) * Math.PI / 180)}%`}
                            stroke="white"
                            strokeWidth="3"
                            strokeLinecap="round"
                          />
                          <circle
                            cx="50%"
                            cy="50%"
                            r="4"
                            fill="white"
                          />
                        </g>
                      </RadialBarChart>
                    </ResponsiveContainer>
                    <VStack spacing={2} textAlign="center">
                      <Text color="white" fontSize="2xl" fontWeight="bold">
                        {percentage.toFixed(1)}%
                      </Text>
                      <Text color="white" fontSize="sm">
                        {currentYear} vs {previousYear}
                      </Text>
                      <Text color={difference >= 0 ? 'green.400' : 'red.400'} fontSize="sm">
                        {difference >= 0 ? '+' : ''}{formatAmount(difference, displayFormat)}
                      </Text>
                      <Text color="gray.400" fontSize="xs">
                        {percentage >= 100 ? t('bnb.growth') : percentage >= 90 ? t('bnb.slightDecline') : t('bnb.significantDecline')}
                      </Text>
                    </VStack>
                  </VStack>
                );
              })()}
            </CardBody>
          </Card>
        </GridItem>
      </Grid>
    </>
  );
};

export default BnbActualsCharts;
