/**
 * Tests for useDuplicateNotification hook
 *
 * Task 8.4: Duplicate detection notification
 */

import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDuplicateNotification } from '../useDuplicateNotification';

// Mock Chakra useToast
const mockToast = vi.fn();
vi.mock('@chakra-ui/react', () => ({
  useToast: () => mockToast,
}));

describe('useDuplicateNotification', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should show info toast when duplicate_of is present', () => {
    const { result } = renderHook(() => useDuplicateNotification());

    act(() => {
      result.current.notifyDuplicate({
        duplicate_of: {
          asset_id: 'ast_01H5K3ABCDEFG',
          original_filename: 'invoice.pdf',
        },
      });
    });

    expect(mockToast).toHaveBeenCalledTimes(1);
    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        title: 'Duplicate detected',
        description: "This file matches 'invoice.pdf'. Merge in Asset Admin.",
        status: 'info',
        duration: 8000,
        isClosable: true,
      }),
    );
  });

  it('should not show toast when duplicate_of is null', () => {
    const { result } = renderHook(() => useDuplicateNotification());

    act(() => {
      result.current.notifyDuplicate({ duplicate_of: null });
    });

    expect(mockToast).not.toHaveBeenCalled();
  });

  it('should not show toast when duplicate_of is undefined', () => {
    const { result } = renderHook(() => useDuplicateNotification());

    act(() => {
      result.current.notifyDuplicate({});
    });

    expect(mockToast).not.toHaveBeenCalled();
  });

  it('should include the original filename in the description', () => {
    const { result } = renderHook(() => useDuplicateNotification());

    act(() => {
      result.current.notifyDuplicate({
        duplicate_of: {
          asset_id: 'ast_XYZ',
          original_filename: 'my-company-logo.png',
        },
      });
    });

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        description: "This file matches 'my-company-logo.png'. Merge in Asset Admin.",
      }),
    );
  });

  it('should set position to top-right for non-blocking display', () => {
    const { result } = renderHook(() => useDuplicateNotification());

    act(() => {
      result.current.notifyDuplicate({
        duplicate_of: {
          asset_id: 'ast_123',
          original_filename: 'test.jpg',
        },
      });
    });

    expect(mockToast).toHaveBeenCalledWith(
      expect.objectContaining({
        position: 'top-right',
      }),
    );
  });
});
