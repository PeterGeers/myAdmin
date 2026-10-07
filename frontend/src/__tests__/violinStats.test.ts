/**
 * Unit tests for the shared `violinStats` helper (charts/violinStats.ts).
 *
 * Verifies the quartile math lifted verbatim from `BnbViolinsReport.tsx` against
 * fixed datasets with hand-computed expected quartiles, so the extraction preserves
 * BNB behavior. Spec: `.kiro/specs/Members/member-analytics` task 1.2 (R3.4).
 */
import { describe, it, expect } from 'vitest';
import { violinStats } from '../components/charts/violinStats';
import { violinStats as violinStatsFromBarrel } from '../components/charts';

describe('violinStats', () => {
  it('computes known quartiles for an 8-point even-length dataset', () => {
    // [10,20,30,40,50,60,70,80], len=8
    //   min=10 max=80
    //   median = (sorted[3]+sorted[4])/2 = (40+50)/2 = 45
    //   q1 = sorted[floor(8*0.25)=2] = 30
    //   q3 = sorted[floor(8*0.75)=6] = 70
    //   mean = 360/8 = 45  range = 70
    const stats = violinStats([10, 20, 30, 40, 50, 60, 70, 80]);
    expect(stats).toEqual({
      count: 8,
      min: 10,
      q1: 30,
      median: 45,
      mean: 45,
      q3: 70,
      max: 80,
      range: 70,
    });
  });

  it('computes known quartiles for an odd-length unsorted dataset (sorts first)', () => {
    // input [5,1,3,9,7] -> sorted [1,3,5,7,9], len=5
    //   min=1 max=9
    //   median = sorted[floor(5/2)=2] = 5
    //   q1 = sorted[floor(5*0.25)=1] = 3
    //   q3 = sorted[floor(5*0.75)=3] = 7
    //   mean = 25/5 = 5  range = 8
    const stats = violinStats([5, 1, 3, 9, 7]);
    expect(stats).toEqual({
      count: 5,
      min: 1,
      q1: 3,
      median: 5,
      mean: 5,
      q3: 7,
      max: 9,
      range: 8,
    });
  });

  it('handles a single-element dataset', () => {
    const stats = violinStats([42]);
    expect(stats).toEqual({
      count: 1,
      min: 42,
      q1: 42,
      median: 42,
      mean: 42,
      q3: 42,
      max: 42,
      range: 0,
    });
  });

  it('matches the positional (non-interpolated) quartile indexing of the BNB original', () => {
    // 10 points 1..10, len=10
    //   q1 = sorted[floor(10*0.25)=2] = 3  (positional, not interpolated 2.75/3.25)
    //   q3 = sorted[floor(10*0.75)=7] = 8
    //   median = (sorted[4]+sorted[5])/2 = (5+6)/2 = 5.5
    const stats = violinStats([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    expect(stats.q1).toBe(3);
    expect(stats.median).toBe(5.5);
    expect(stats.q3).toBe(8);
    expect(stats.mean).toBe(5.5);
    expect(stats.range).toBe(9);
  });

  it('is exported from the charts barrel', () => {
    expect(violinStatsFromBarrel).toBe(violinStats);
  });
});
