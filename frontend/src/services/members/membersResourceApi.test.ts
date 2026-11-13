/**
 * Focused tests for the PURE mappers exported by membersResourceApi.ts
 * (cadence <-> cron and delivery <-> stored block). No network is exercised.
 */

import { describe, it, expect } from 'vitest';
import {
  CADENCE_CRON,
  SCHEDULE_CADENCES,
  cadenceToCron,
  cronToCadence,
  deliveryFromBackend,
  deliveryToBackend,
} from './membersResourceApi';
import type { MemberDelivery } from '../../types/members';

type RawDeliveryArg = Parameters<typeof deliveryFromBackend>[0];

describe('cadence <-> cron', () => {
  it('exposes the monthly/weekly cadences and their cron expressions', () => {
    expect(SCHEDULE_CADENCES).toEqual(['monthly', 'weekly']);
    expect(CADENCE_CRON.monthly).toBe('cron(0 8 1 * ? *)');
    expect(CADENCE_CRON.weekly).toBe('cron(0 8 ? * MON *)');
  });

  it('maps cadence -> cron', () => {
    expect(cadenceToCron('monthly')).toBe('cron(0 8 1 * ? *)');
    expect(cadenceToCron('weekly')).toBe('cron(0 8 ? * MON *)');
  });

  it('recovers cadence from cron (trimmed) and falls back to monthly', () => {
    expect(cronToCadence('cron(0 8 ? * MON *)')).toBe('weekly');
    expect(cronToCadence('  cron(0 8 1 * ? *)  ')).toBe('monthly');
    expect(cronToCadence('cron(0 0 * * ? *)')).toBe('monthly');
    expect(cronToCadence('')).toBe('monthly');
  });
});

describe('delivery mapping', () => {
  it('maps an absent/invalid stored block to undefined', () => {
    expect(deliveryFromBackend(null)).toBeUndefined();
    expect(deliveryFromBackend(undefined)).toBeUndefined();
    expect(deliveryFromBackend({ mode: 'nope' } as unknown as RawDeliveryArg)).toBeUndefined();
  });

  it('maps a stored to_fixed block (recipients kept, labelOptions null for csv)', () => {
    expect(
      deliveryFromBackend({
        mode: 'to_fixed',
        template_id: 't1',
        attachment: 'csv',
        recipients: ['a', 'b'],
      } as unknown as RawDeliveryArg),
    ).toEqual({
      mode: 'to_fixed',
      templateId: 't1',
      attachment: 'csv',
      recipients: ['a', 'b'],
      labelOptions: null,
    });
  });

  it('maps non-array recipients to []', () => {
    const mapped = deliveryFromBackend({
      mode: 'to_fixed',
      recipients: 'not-an-array',
    } as unknown as RawDeliveryArg);
    expect(mapped?.recipients).toEqual([]);
  });

  it('stores recipients only for to_fixed and null label_options for csv', () => {
    const toFixed: MemberDelivery = {
      mode: 'to_fixed',
      templateId: 't1',
      attachment: 'csv',
      recipients: ['a', 'b'],
      labelOptions: null,
    };
    expect(deliveryToBackend(toFixed)).toEqual({
      mode: 'to_fixed',
      template_id: 't1',
      attachment: 'csv',
      recipients: ['a', 'b'],
      label_options: null,
    });

    const perRecipient: MemberDelivery = {
      mode: 'per_recipient',
      templateId: null,
      attachment: null,
      recipients: ['ignored'],
      labelOptions: null,
    };
    expect(deliveryToBackend(perRecipient)).toEqual({
      mode: 'per_recipient',
      template_id: null,
      attachment: null,
      recipients: [],
      label_options: null,
    });
  });
});
