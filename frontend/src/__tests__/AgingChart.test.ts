/**
 * Tests for AgingChart data transformation logic.
 */
import { AgingBuckets } from '../types/zzp';

// Extract the data transformation from the component for testing
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

function transformBuckets(buckets: AgingBuckets) {
  return Object.entries(buckets).map(([key, value]) => ({
    name: BUCKET_LABELS[key] || key,
    amount: value,
    fill: BUCKET_COLORS[key] || '#718096',
  }));
}

describe('AgingChart data transformation', () => {
  const sampleBuckets: AgingBuckets = {
    current: 10000,
    '1_30_days': 5000,
    '31_60_days': 3000,
    '61_90_days': 1500,
    '90_plus_days': 500,
  };

  it('transforms all 5 buckets', () => {
    const data = transformBuckets(sampleBuckets);
    expect(data).toHaveLength(5);
  });

  it('maps bucket keys to Dutch labels', () => {
    const data = transformBuckets(sampleBuckets);
    expect(data[0].name).toBe('Huidig');
    expect(data[1].name).toBe('1-30 dagen');
    expect(data[4].name).toBe('90+ dagen');
  });

  it('preserves amounts', () => {
    const data = transformBuckets(sampleBuckets);
    expect(data[0].amount).toBe(10000);
    expect(data[4].amount).toBe(500);
  });

  it('assigns correct colors', () => {
    const data = transformBuckets(sampleBuckets);
    expect(data[0].fill).toBe('#38A169'); // green for current
    expect(data[3].fill).toBe('#E53E3E'); // red for 61-90
    expect(data[4].fill).toBe('#9B2C2C'); // dark red for 90+
  });

  it('handles zero amounts', () => {
    const zeroBuckets: AgingBuckets = {
      current: 0, '1_30_days': 0, '31_60_days': 0, '61_90_days': 0, '90_plus_days': 0,
    };
    const data = transformBuckets(zeroBuckets);
    expect(data.every(d => d.amount === 0)).toBe(true);
  });
});
