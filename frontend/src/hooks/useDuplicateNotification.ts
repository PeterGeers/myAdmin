/**
 * useDuplicateNotification — Show a non-blocking toast when an upload
 * result indicates the file is a duplicate of an existing asset.
 *
 * Task 8.4: Duplicate detection notification
 */

import { useToast } from '@chakra-ui/react';
import { useCallback } from 'react';
import type { DuplicateInfo } from '@/types/mediaAsset';

/** Shape of an upload result that may include duplicate info */
export interface UploadResultWithDuplicate {
  duplicate_of?: DuplicateInfo | null;
}

/**
 * Returns a `notifyDuplicate` function that checks the upload result
 * for a duplicate match and shows an info toast if one is found.
 */
export function useDuplicateNotification() {
  const toast = useToast();

  const notifyDuplicate = useCallback(
    (uploadResult: UploadResultWithDuplicate) => {
      if (!uploadResult.duplicate_of) return;

      const { original_filename } = uploadResult.duplicate_of;

      toast({
        title: 'Duplicate detected',
        description: `This file matches '${original_filename}'. Merge in Asset Admin.`,
        status: 'info',
        duration: 8000,
        isClosable: true,
        position: 'top-right',
      });
    },
    [toast],
  );

  return { notifyDuplicate };
}
