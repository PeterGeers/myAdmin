/**
 * Aging analysis stacked bar chart using Recharts.
 * Reference: .kiro/specs/zzp-module/design.md §6.3
 */

import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { AgingBuckets } from '../../types/zzp';

interface AgingChartProps {
  buckets: AgingBuckets;
}

const BUCKET_LABELS: Record<string, string> = {
  current: 'Huidig',
  '1_30_days': '1-30 dagen',
  '31_60_days': '31-60 dagen',
  '61_90_days': '61-90 dagen',
  '90_plus_days': '90+ dagen',
};

const BUCKET_COLORS: Record<string, string> = {
  current: '#38A169',
  '1_30_days': '#ECC94B',
  '31_60_days': '#ED8936',
  '61_90_days': '#E53E3E',
  '90_plus_days': '#9B2C2C',
};

export const AgingChart: React.FC<AgingChartProps> = ({ buckets }) => {
  const data = Object.entries(buckets).map(([key, value]) => ({
    name: BUCKET_LABELS[key] || key,
    amount: value,
    fill: BUCKET_COLORS[key] || '#718096',
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="name" />
        <YAxis />
        <Tooltip formatter={(value: number) => `€ ${value.toFixed(2)}`} />
        <Legend />
        <Bar dataKey="amount" name="Bedrag" fill="#3182CE" />
      </BarChart>
    </ResponsiveContainer>
  );
};
