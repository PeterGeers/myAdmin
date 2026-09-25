/**
 * applyApiError — unit tests (API standard v1.0, task 4.3).
 *
 * Uses the REAL i18n instance so code resolution + fallback are exercised end to end (a code
 * with copy localizes; an unknown code falls back to the entry's English `detail`). `toast` and
 * `setFieldError` are spies.
 */

import { vi, describe, it, expect, beforeEach, type Mock } from 'vitest';
import i18n from '../../i18n';
import { applyApiError, type TranslateFn, type ToastFn } from './applyApiError';
import { ApiError } from './ApiError';

// The real translate, bound like a component's `t` (default namespace irrelevant — the helper
// resolves `errors:<path>` explicitly).
const t: TranslateFn = (key, options) => i18n.t(key, options) as unknown as string;

describe('applyApiError', () => {
  let toast: Mock & ToastFn;
  let setFieldError: Mock & ((field: string, message: string) => void);

  beforeEach(() => {
    i18n.changeLanguage('en');
    toast = vi.fn() as unknown as Mock & ToastFn;
    setFieldError = vi.fn() as unknown as Mock & ((field: string, message: string) => void);
  });

  it('renders a matched 422 field error INLINE (localized) and shows a summary toast', () => {
    const err = new ApiError(422, {
      error: 'Validation failed',
      code: 'errors.validation.failed',
      errors: [
        { field: 'personal.first_name', code: 'errors.validation.required', detail: 'is required' },
      ],
    });

    applyApiError(err, { toast, t, setFieldError, knownFields: ['personal.first_name'] });

    // Inline, LOCALIZED via the code (not the raw English detail).
    expect(setFieldError).toHaveBeenCalledTimes(1);
    const [field, line] = setFieldError.mock.calls[0];
    expect(field).toBe('personal.first_name');
    expect(line).toBe('This field is required.');
    // A summary toast still fires (localized from the top-level code).
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast.mock.calls[0][0].title).toBe('Validation failed. Please check your input.');
    expect(toast.mock.calls[0][0].status).toBe('error');
  });

  it('interpolates params on an inline field line', () => {
    const err = new ApiError(422, {
      error: 'Validation failed',
      errors: [
        {
          field: 'membership.status',
          code: 'errors.validation.mustBeOneOf',
          params: { allowed: 'active, inactive' },
          detail: 'must be one of: active, inactive',
        },
      ],
    });
    applyApiError(err, { toast, t, setFieldError, knownFields: ['membership.status'] });
    expect(setFieldError.mock.calls[0][1]).toContain('active, inactive');
  });

  it('folds an UNMATCHED field error into the summary toast', () => {
    const err = new ApiError(422, {
      error: 'Validation failed',
      errors: [
        { field: 'overlay.motor', code: 'no.copy.for.this', detail: 'an active member must have a motorcycle' },
      ],
    });
    // knownFields does NOT include overlay.motor → not inline.
    applyApiError(err, { toast, t, setFieldError, knownFields: ['personal.first_name'] });
    expect(setFieldError).not.toHaveBeenCalled();
    // The unmatched line (its English detail, since the code has no copy) folds into the toast.
    expect(toast.mock.calls[0][0].title).toContain('an active member must have a motorcycle');
  });

  it('falls back to the English detail when a field code has no locale copy', () => {
    const err = new ApiError(422, {
      errors: [{ field: 'x.y', code: 'totally.unknown.code', detail: 'backend english detail' }],
    });
    applyApiError(err, { toast, t, setFieldError, knownFields: ['x.y'] });
    expect(setFieldError.mock.calls[0][1]).toBe('backend english detail');
  });

  it('surfaces 409 reasons in the summary toast (localized)', () => {
    const err = new ApiError(409, {
      error: 'Transition denied',
      code: 'errors.transition.denied',
      reasons: [
        { code: 'errors.transition.denied', detail: 'member number required to activate' },
      ],
    });
    applyApiError(err, { toast, t });
    expect(toast).toHaveBeenCalledTimes(1);
    // Top-level code localizes the summary.
    expect(toast.mock.calls[0][0].title).toBe('This status change is not allowed.');
  });

  it('tolerates a legacy reasons: string[] (joined into the toast when no summary code)', () => {
    const err = new ApiError(409, {
      error: 'Transition denied',
      reasons: ['first reason', 'second reason'],
    });
    applyApiError(err, { toast, t });
    const title = toast.mock.calls[0][0].title;
    expect(title).toContain('first reason');
    expect(title).toContain('second reason');
  });

  it('shows the localized server-error fallback for a non-ApiError (network throw)', () => {
    applyApiError(new Error('Failed to fetch'), { toast, t });
    expect(toast).toHaveBeenCalledTimes(1);
    expect(toast.mock.calls[0][0].title).toBe('Server error. Please try again later.');
  });

  it('localizes in Dutch too', () => {
    i18n.changeLanguage('nl');
    const err = new ApiError(422, {
      code: 'errors.validation.failed',
      errors: [
        { field: 'personal.first_name', code: 'errors.validation.required', detail: 'is required' },
      ],
    });
    applyApiError(err, { toast, t, setFieldError, knownFields: ['personal.first_name'] });
    expect(setFieldError.mock.calls[0][1]).toBe('Dit veld is verplicht.');
    expect(toast.mock.calls[0][0].title).toBe('Validatie mislukt. Controleer uw invoer.');
  });
});
