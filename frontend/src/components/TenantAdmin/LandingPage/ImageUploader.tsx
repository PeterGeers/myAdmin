/**
 * ImageUploader — Upload images for landing page blocks.
 *
 * Features:
 * - Drag-and-drop zone
 * - Click to select file
 * - Upload progress indicator
 * - Preview of uploaded/current image
 * - File type validation (jpg, png, webp, svg) + size limit (5MB)
 * - Error messages for invalid files
 * - "Choose existing" option to pick from asset library (AssetPicker)
 *
 * Task 2.18, Task 8.3
 */

import React, { useCallback, useRef, useState } from 'react';
import {
  Box, Text, VStack, HStack, Icon, Progress, Image,
  IconButton, useToast, Button, useDisclosure,
} from '@chakra-ui/react';
import { FiUploadCloud, FiX, FiImage, FiFolder } from 'react-icons/fi';
import { uploadImage } from '../../../services/landingPageApi';
import { AssetPicker } from '../../common/AssetPicker/AssetPicker';
import type { MediaAsset, AssetCategory, AssetMediaType } from '@/types/mediaAsset';
import { useDuplicateNotification } from '@/hooks/useDuplicateNotification';

const ALLOWED_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp', '.svg'];
const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/svg+xml'];
const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB

interface ImageUploaderProps {
  onUpload: (imageKey: string) => void;
  currentImageKey?: string;
  label?: string;
  /** Show "Choose existing" button to open asset picker (default: true) */
  showAssetPicker?: boolean;
  /** Default category filter for asset picker */
  assetPickerCategory?: AssetCategory;
  /** Restrict allowed media types in asset picker */
  assetPickerMediaTypes?: AssetMediaType[];
}

export default function ImageUploader({
  onUpload,
  currentImageKey,
  label,
  showAssetPicker = true,
  assetPickerCategory,
  assetPickerMediaTypes = ['image'],
}: ImageUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const toast = useToast();
  const { isOpen: isPickerOpen, onOpen: onPickerOpen, onClose: onPickerClose } = useDisclosure();
  const { notifyDuplicate } = useDuplicateNotification();

  const validateFile = useCallback((file: File): string | null => {
    // Check extension
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      return `Invalid file type "${ext}". Allowed: jpg, png, webp, svg`;
    }

    // Check MIME type
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      return `Invalid file type "${file.type}". Allowed: image/jpeg, image/png, image/webp, image/svg+xml`;
    }

    // Check size
    if (file.size > MAX_FILE_SIZE) {
      const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
      return `File too large (${sizeMB}MB). Maximum size is 5MB.`;
    }

    return null;
  }, []);

  const handleUpload = useCallback(async (file: File) => {
    const validationError = validateFile(file);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setIsUploading(true);
    setProgress(0);

    // Show local preview
    const localPreview = URL.createObjectURL(file);
    setPreviewUrl(localPreview);

    try {
      const result = await uploadImage(file, (progressEvent) => {
        if (progressEvent.total) {
          setProgress(Math.round((progressEvent.loaded / progressEvent.total) * 100));
        }
      });

      onUpload(result.image_key);
      notifyDuplicate(result);
      toast({
        title: 'Image uploaded',
        status: 'success',
        duration: 2000,
        isClosable: true,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Upload failed';
      setError(message);
      setPreviewUrl(null);
      toast({
        title: 'Upload failed',
        description: message,
        status: 'error',
        duration: 4000,
        isClosable: true,
      });
    } finally {
      setIsUploading(false);
      URL.revokeObjectURL(localPreview);
    }
  }, [validateFile, onUpload, toast, notifyDuplicate]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleUpload(files[0]);
    }
  }, [handleUpload]);

  const handleClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleUpload(files[0]);
    }
    // Reset input so same file can be selected again
    e.target.value = '';
  }, [handleUpload]);

  const handleRemove = useCallback(() => {
    setPreviewUrl(null);
    setError(null);
    onUpload('');
  }, [onUpload]);

  /** Handle asset selection from the AssetPicker modal */
  const handleAssetSelect = useCallback((asset: MediaAsset) => {
    // Extract S3 key from presigned URL or use the asset id as fallback
    // The presigned URL contains the S3 key in the path — but we use the
    // original_filename and id to construct a reference the backend understands.
    // Convention: the asset's s3_key is embedded in the presigned_url path.
    // However, the most reliable approach is to use the asset ID which the
    // backend can resolve. For ImageUploader's onUpload callback (which expects
    // an S3 image key), we extract the key from the presigned URL path.
    if (asset.presigned_url) {
      try {
        const url = new URL(asset.presigned_url);
        // S3 presigned URLs have the key as the pathname (after the leading slash)
        const s3Key = decodeURIComponent(url.pathname.slice(1));
        setPreviewUrl(asset.presigned_url);
        onUpload(s3Key);
      } catch {
        // Fallback: use presigned_url directly for preview, asset id for key
        setPreviewUrl(asset.presigned_url);
        onUpload(asset.id);
      }
    } else {
      // No presigned URL — use the asset id
      onUpload(asset.id);
    }
    toast({
      title: 'Asset selected',
      description: asset.original_filename,
      status: 'success',
      duration: 2000,
      isClosable: true,
    });
  }, [onUpload, toast]);

  // Determine what to show as preview
  const showImage = previewUrl || currentImageKey;

  return (
    <VStack spacing={2} align="stretch">
      {label && (
        <Text color="gray.300" fontSize="xs" fontWeight="medium">
          {label}
        </Text>
      )}

      {/* Preview of current/uploaded image */}
      {showImage && !isUploading && (
        <Box position="relative" borderRadius="md" overflow="hidden">
          <Image
            src={previewUrl || (currentImageKey ? `https://${import.meta.env.VITE_CLOUDFRONT_DOMAIN || ''}/${currentImageKey}` : undefined)}
            alt="Uploaded image"
            maxH="120px"
            maxW="100%"
            objectFit="contain"
            borderRadius="md"
            fallback={
              <HStack bg="gray.700" p={3} borderRadius="md" justify="center">
                <Icon as={FiImage} color="gray.400" />
                <Text color="gray.400" fontSize="xs" noOfLines={1}>
                  {currentImageKey}
                </Text>
              </HStack>
            }
          />
          <IconButton
            aria-label="Remove image"
            icon={<FiX />}
            size="xs"
            position="absolute"
            top={1}
            right={1}
            colorScheme="red"
            variant="solid"
            opacity={0.8}
            onClick={handleRemove}
            _hover={{ opacity: 1 }}
          />
        </Box>
      )}

      {/* Upload zone */}
      <Box
        border="2px dashed"
        borderColor={isDragging ? 'blue.400' : error ? 'red.400' : 'gray.600'}
        borderRadius="md"
        p={4}
        textAlign="center"
        cursor="pointer"
        bg={isDragging ? 'blue.900' : 'gray.750'}
        transition="all 0.2s"
        _hover={{ borderColor: 'blue.400', bg: 'gray.700' }}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={handleClick}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".jpg,.jpeg,.png,.webp,.svg"
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        {isUploading ? (
          <VStack spacing={2}>
            <Text color="gray.300" fontSize="xs">Uploading...</Text>
            <Progress
              value={progress}
              size="sm"
              colorScheme="blue"
              borderRadius="full"
              w="100%"
              hasStripe
              isAnimated
            />
            <Text color="gray.400" fontSize="xs">{progress}%</Text>
          </VStack>
        ) : (
          <VStack spacing={1}>
            <Icon as={FiUploadCloud} color="gray.400" boxSize={5} />
            <Text color="gray.300" fontSize="xs">
              Drop image here or click to upload
            </Text>
            <Text color="gray.500" fontSize="xs">
              jpg, png, webp, svg — max 5MB
            </Text>
          </VStack>
        )}
      </Box>

      {/* Error message */}
      {error && (
        <Text color="red.300" fontSize="xs">
          {error}
        </Text>
      )}

      {/* Choose existing asset button */}
      {showAssetPicker && !isUploading && (
        <Button
          size="xs"
          variant="ghost"
          color="gray.400"
          fontWeight="normal"
          leftIcon={<Icon as={FiFolder} />}
          onClick={onPickerOpen}
          _hover={{ color: 'orange.300' }}
          data-testid="choose-existing-asset-btn"
        >
          or choose existing
        </Button>
      )}

      {/* Asset Picker Modal */}
      {showAssetPicker && (
        <AssetPicker
          isOpen={isPickerOpen}
          onClose={onPickerClose}
          onSelect={handleAssetSelect}
          defaultCategory={assetPickerCategory}
          defaultMediaType=""
          allowedMediaTypes={assetPickerMediaTypes}
        />
      )}
    </VStack>
  );
}
