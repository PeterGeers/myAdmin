/**
 * Component tests for MemberScheduleEditor (analytics/MemberScheduleEditor.tsx).
 *
 * Verifies task 5.4 (R5, pivot-output-actions): the attach/manage-a-schedule
 * editor on a saved set that HAS a delivery block —
 *   - a set with NO delivery blocks saving and shows the clear reason (a schedule
 *     can only be attached to a set with a delivery block, R5);
 *   - the friendly cadence picker (monthly/weekly) + the enable/disable toggle;
 *   - Save on a NEW schedule calls onCreate (→ POST) with the picked cadence +
 *     enabled; Save on an EXISTING schedule calls onUpdate (→ PUT); Delete calls
 *     onDelete (→ DELETE);
 *   - an existing schedule seeds the cadence from its stored cron (cronToCadence)
 *     and its enabled flag;
 *   - no hardcoded English (labels resolve from the `members` namespace, echoed by
 *     the i18n mock).
 *
 * The create/update/delete functions are injected via props (no network); only
 * the i18n hook is mocked. The real `membersApiService` cadence helpers
 * (SCHEDULE_CADENCES / cronToCadence) are used (no mocking) so the shared mapping
 * is exercised; the service reads its base URL lazily so importing those
 * constants needs no env setup.
 */
import { vi, describe, it, expect, beforeEach } from 'vitest';
import React from 'react';

// Echo i18n keys so assertions are locale-independent (prove no hardcoded English).
vi.mock('../../../hooks/useTypedTranslation', () => ({
  useTypedTranslation: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params ? `${key} ${JSON.stringify(params)}` : key,
  }),
}));

import { render, screen, fireEvent, waitFor } from '@/test-utils';
import MemberScheduleEditor, {
  type MemberScheduleEditorProps,
} from './MemberScheduleEditor';
import { MemberScheduleEditor as FromBarrel } from './index';
import type { MemberSchedule } from '../../../types/members';

let onCreate: ReturnType<typeof vi.fn>;
let onUpdate: ReturnType<typeof vi.fn>;
let onDelete: ReturnType<typeof vi.fn>;
let onClose: ReturnType<typeof vi.fn>;

function makeProps(
  overrides: Partial<MemberScheduleEditorProps> = {},
): MemberScheduleEditorProps {
  return {
    isOpen: true,
    onClose: onClose as unknown as MemberScheduleEditorProps['onClose'],
    setName: 'Jubilees',
    hasDelivery: true,
    onCreate: onCreate as unknown as MemberScheduleEditorProps['onCreate'],
    onUpdate: onUpdate as unknown as MemberScheduleEditorProps['onUpdate'],
    onDelete: onDelete as unknown as MemberScheduleEditorProps['onDelete'],
    ...overrides,
  };
}

beforeEach(() => {
  onCreate = vi.fn().mockResolvedValue(undefined);
  onUpdate = vi.fn().mockResolvedValue(undefined);
  onDelete = vi.fn().mockResolvedValue(undefined);
  onClose = vi.fn();
});

describe('MemberScheduleEditor', () => {
  it('is exported from the analytics barrel', () => {
    expect(FromBarrel).toBe(MemberScheduleEditor);
  });

  it('defaults a set with no existing schedule to monthly + enabled', async () => {
    render(<MemberScheduleEditor {...makeProps()} />);

    const cadence = (await screen.findByTestId('schedule-cadence-select')) as HTMLSelectElement;
    expect(cadence.value).toBe('monthly');
    const enabled = screen.getByTestId('schedule-enabled-switch') as HTMLInputElement;
    expect(enabled.checked).toBe(true);
    // A new schedule shows no Delete (nothing to delete yet).
    expect(screen.queryByTestId('member-schedule-delete')).not.toBeInTheDocument();
  });

  // Validates: Requirements 5 (R5) — schedule only on a set with a delivery block.
  it('blocks saving + shows the reason when the set has no delivery block', async () => {
    render(<MemberScheduleEditor {...makeProps({ hasDelivery: false })} />);

    expect(await screen.findByTestId('member-schedule-no-delivery')).toBeInTheDocument();
    const save = screen.getByTestId('member-schedule-save') as HTMLButtonElement;
    expect(save).toBeDisabled();
    // The cadence picker is disabled too — nothing can be edited without a delivery.
    expect(screen.getByTestId('schedule-cadence-select')).toBeDisabled();

    // A click never reaches onCreate (defence in depth beyond the disabled button).
    fireEvent.click(save);
    await waitFor(() => expect(onCreate).not.toHaveBeenCalled());
  });

  // Validates: Requirements 5 (R5) — Save on a NEW schedule → POST (onCreate).
  it('Save on a new schedule calls onCreate (POST) with the picked cadence + enabled', async () => {
    render(<MemberScheduleEditor {...makeProps()} />);

    // Pick weekly, keep enabled.
    fireEvent.change(await screen.findByTestId('schedule-cadence-select'), {
      target: { value: 'weekly' },
    });
    fireEvent.click(await screen.findByTestId('member-schedule-save'));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledWith('weekly', true);
    expect(onUpdate).not.toHaveBeenCalled();
    // A successful save closes the modal.
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  // Validates: Requirements 5 (R5) — the enable/disable toggle.
  it('the enable/disable toggle flows through to onCreate', async () => {
    render(<MemberScheduleEditor {...makeProps()} />);

    // Disable the schedule, then save.
    fireEvent.click(await screen.findByTestId('schedule-enabled-switch'));
    fireEvent.click(await screen.findByTestId('member-schedule-save'));

    await waitFor(() => expect(onCreate).toHaveBeenCalledTimes(1));
    expect(onCreate).toHaveBeenCalledWith('monthly', false);
  });

  // Validates: Requirements 5 (R5) — Save on an EXISTING schedule → PUT (onUpdate).
  it('seeds from an existing schedule (cron→cadence) and Save calls onUpdate (PUT)', async () => {
    const existing: MemberSchedule = {
      scheduleId: 'sch-1',
      setId: 'set-1',
      cron: 'cron(0 8 ? * MON *)', // weekly
      enabled: false,
      createdBy: 'sub-1',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    render(<MemberScheduleEditor {...makeProps({ initialSchedule: existing })} />);

    // The stored cron maps back to the weekly cadence; the disabled flag is seeded.
    const cadence = (await screen.findByTestId('schedule-cadence-select')) as HTMLSelectElement;
    expect(cadence.value).toBe('weekly');
    const enabled = screen.getByTestId('schedule-enabled-switch') as HTMLInputElement;
    expect(enabled.checked).toBe(false);

    // Re-enable + save → onUpdate (PUT), not onCreate.
    fireEvent.click(enabled);
    fireEvent.click(await screen.findByTestId('member-schedule-save'));

    await waitFor(() => expect(onUpdate).toHaveBeenCalledTimes(1));
    expect(onUpdate).toHaveBeenCalledWith('weekly', true);
    expect(onCreate).not.toHaveBeenCalled();
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  // Validates: Requirements 5 (R5) — Delete → DELETE (onDelete).
  it('Delete calls onDelete (DELETE) for an existing schedule', async () => {
    const existing: MemberSchedule = {
      scheduleId: 'sch-1',
      setId: 'set-1',
      cron: 'cron(0 8 1 * ? *)',
      enabled: true,
      createdBy: 'sub-1',
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    };
    render(<MemberScheduleEditor {...makeProps({ initialSchedule: existing })} />);

    fireEvent.click(await screen.findByTestId('member-schedule-delete'));
    await waitFor(() => expect(onDelete).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});
