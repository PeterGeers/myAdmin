/**
 * Regression test for the BNB violin extraction (task 2.2, spec
 * `.kiro/specs/Members/member-analytics`, design C3; R3.2/R6.5).
 *
 * BnbViolinsReport no longer owns an inline violin/stats implementation — it maps its
 * domain shape `{listing, channel, value}` onto the generic `ViolinDatum {group, value}`
 * and computes its stats via the SHARED `charts/violinStats` helper, rendering through
 * the shared `charts/ViolinChart`.
 *
 * This test pins the EXTRACTED path against the ORIGINAL inline BNB algorithm so a future
 * change to the shared helper can't silently alter BNB numbers. The `legacyBnbStats`
 * oracle below is the exact per-group statistics block that previously lived inside
 * `BnbViolinsReport.tsx` (verbatim), run over a fixed dataset. We assert the shared path
 * reproduces it group-for-group, field-for-field.
 */
import { describe, it, expect } from 'vitest';
import { violinStats } from '../charts';

interface ViolinDataPoint {
  listing: string;
  channel: string;
  value: number;
}

/**
 * The ORIGINAL inline BNB per-group stats computation, lifted verbatim from the
 * pre-refactor `BnbViolinsReport.tsx` (grouping + the `statsData` map). Used here as the
 * behavioral oracle the shared path must reproduce exactly.
 */
function legacyBnbStats(data: ViolinDataPoint[], groupBy: 'listing' | 'channel') {
  const grouped = data.reduce((acc, item) => {
    const key = item[groupBy as keyof ViolinDataPoint] as string;
    if (!acc[key]) acc[key] = [];
    acc[key].push(Number(item.value) || 0);
    return acc;
  }, {} as Record<string, number[]>);

  const sortedGroups = Object.keys(grouped).sort();

  return sortedGroups.map((name) => {
    const values = grouped[name].sort((a: number, b: number) => a - b);
    const len = values.length;

    const min = values[0];
    const max = values[len - 1];
    const median =
      len % 2 === 0
        ? (values[len / 2 - 1] + values[len / 2]) / 2
        : values[Math.floor(len / 2)];
    const q1 = values[Math.floor(len * 0.25)];
    const q3 = values[Math.floor(len * 0.75)];
    const mean = values.reduce((sum: number, val: number) => sum + val, 0) / len;

    return { name, count: len, min, q1, median, mean, q3, max, range: max - min };
  });
}

/**
 * The EXTRACTED path exactly as the refactored component builds it: map
 * `{listing, channel, value}` -> `{group, value}` by the chosen grouping, group by
 * `group`, sort alphabetically, and compute each group via the shared `violinStats`.
 */
function extractedBnbStats(data: ViolinDataPoint[], groupBy: 'listing' | 'channel') {
  const violinData = data.map((item) => ({
    group: item[groupBy],
    value: Number(item.value) || 0,
  }));

  const grouped = violinData.reduce((acc, item) => {
    const key = item.group;
    if (!acc[key]) acc[key] = [];
    acc[key].push(item.value);
    return acc;
  }, {} as Record<string, number[]>);

  return Object.keys(grouped)
    .sort()
    .map((name) => ({ name, ...violinStats([...grouped[name]]) }));
}

// Fixed dataset with hand-verifiable quartiles. NB: BNB uses POSITIONAL indexing
// (q1=values[floor(len*0.25)], q3=values[floor(len*0.75)]) and an even-length median
// of the two middle elements — NOT linear interpolation. These expectations follow
// that exact algorithm.
//   listing "Beach House": price values [50,60,70,80,90,100,110,120] (len 8, even)
//     -> count 8, min 50, q1 values[2]=70, median (80+90)/2=85, mean 85,
//        q3 values[6]=110, max 120, range 70
//   listing "City Flat":  price values [40]
//     -> count 1, min 40, q1 40, median 40, mean 40, q3 40, max 40, range 0
//   channel "Airbnb":     [50,70,90,110,40] -> sorted [40,50,70,90,110] (len 5, odd)
//     -> count 5, min 40, q1 values[1]=50, median values[2]=70, mean 72,
//        q3 values[3]=90, max 110, range 70
//   channel "Booking":    [60,80,100,120]  -> sorted [60,80,100,120] (len 4, even)
//     -> count 4, min 60, q1 values[1]=80, median (80+100)/2=90, mean 90,
//        q3 values[3]=120, max 120, range 60
const fixtureData: ViolinDataPoint[] = [
  { listing: 'Beach House', channel: 'Airbnb', value: 50 },
  { listing: 'Beach House', channel: 'Booking', value: 60 },
  { listing: 'Beach House', channel: 'Airbnb', value: 70 },
  { listing: 'Beach House', channel: 'Booking', value: 80 },
  { listing: 'Beach House', channel: 'Airbnb', value: 90 },
  { listing: 'Beach House', channel: 'Booking', value: 100 },
  { listing: 'Beach House', channel: 'Airbnb', value: 110 },
  { listing: 'Beach House', channel: 'Booking', value: 120 },
  { listing: 'City Flat', channel: 'Airbnb', value: 40 },
];

describe('BnbViolinsReport extraction — stats regression (R3.2/R6.5)', () => {
  it('reproduces legacy BNB stats grouped by listing', () => {
    expect(extractedBnbStats(fixtureData, 'listing')).toEqual(
      legacyBnbStats(fixtureData, 'listing')
    );
  });

  it('reproduces legacy BNB stats grouped by channel', () => {
    expect(extractedBnbStats(fixtureData, 'channel')).toEqual(
      legacyBnbStats(fixtureData, 'channel')
    );
  });

  it('matches the hand-computed quartiles for the fixed dataset (by listing)', () => {
    const byListing = extractedBnbStats(fixtureData, 'listing');

    expect(byListing).toEqual([
      {
        name: 'Beach House',
        count: 8,
        min: 50,
        q1: 70,
        median: 85,
        mean: 85,
        q3: 110,
        max: 120,
        range: 70,
      },
      {
        name: 'City Flat',
        count: 1,
        min: 40,
        q1: 40,
        median: 40,
        mean: 40,
        q3: 40,
        max: 40,
        range: 0,
      },
    ]);
  });

  it('matches the hand-computed quartiles for the fixed dataset (by channel)', () => {
    const byChannel = extractedBnbStats(fixtureData, 'channel');

    expect(byChannel).toEqual([
      {
        name: 'Airbnb',
        count: 5,
        min: 40,
        q1: 50,
        median: 70,
        mean: 72,
        q3: 90,
        max: 110,
        range: 70,
      },
      {
        name: 'Booking',
        count: 4,
        min: 60,
        q1: 80,
        median: 90,
        mean: 90,
        q3: 120,
        max: 120,
        range: 60,
      },
    ]);
  });
});
