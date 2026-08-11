/**
 * AssetPicker component tests
 */

import React from 'react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@/test-utils';
import { fetchAuthSession } from 'aws-amplify/auth';
import { AssetPicker } from './AssetPicker';
import type { MediaAsset } from '@/types/mediaAsset';

// ─── Mock data ────────────────────────────────────────────────────────────────

const mockAssets: MediaAsset[] = [
  {
    id: 'ast_001',
    original_filename: 'company_logo.png',
    mime_type: 'image/png',
    file_size: 245000,
    category: 'branding',
    media_type: 'image',
    created_at: '2025-06-01T10:00:00Z',
    reference_count: 3,
    presigned_url: 'https://s3.example.com/logo.png',
  },
  {
    id: 'ast_002',
    original_filename: 'invoice_q1.pdf',
    mime_type: 'application/pdf',
    file_size: 1024000,
    category: 'invoices',
    media_type: 'document',
    created_at: '2025-05-20T08:30:00Z',
    reference_count: 1,
    presigned_url: null,
  },
];

const mockSearchResponse = {
  success: true,
  data: mockAssets,
  pagination: { page: 1, page_size: 20, total: 2, total_pages: 1 },
};

// ─── Setup ────────────────────────────────────────────────────────────────────

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.resetAllMocks();

  // Mock fetchAuthSession to return a valid token
  vi.mocked(fetchAuthSession).mockResolvedValue({
    tokens: {
      idToken: { toString: () => 'mock-token-123' },
    },
  } as any);

  // Mock fetch to return asset search results
  fetchSpy = vi.spyOn(global, 'fetch').mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(mockSearchResponse),
    status: 200,
    headers: new Headers(),
  } as Response);
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('AssetPicker', () => {
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSelect: vi.fn(),
  };

  it('renders the modal when isOpen is true', () => {
    render(<AssetPicker {...defaultProps} />);

    expect(screen.getByText('Choose Existing Asset')).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    render(<AssetPicker {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Choose Existing Asset')).not.toBeInTheDocument();
  });

  it('shows loading state while fetching assets', () => {
    // Make fetch hang (never resolves)
    fetchSpy.mockReturnValue(new Promise(() => {}));

    render(<AssetPicker {...defaultProps} />);

    expect(screen.getByText('Loading assets...')).toBeInTheDocument();
  });

  it('displays search and filter controls', () => {
    render(<AssetPicker {...defaultProps} />);

    expect(screen.getByTestId('asset-search-input')).toBeInTheDocument();
    expect(screen.getByTestId('asset-category-filter')).toBeInTheDocument();
    expect(screen.getByTestId('asset-media-type-filter')).toBeInTheDocument();
    expect(screen.getByTestId('asset-sort-select')).toBeInTheDocument();
  });

  it('displays asset tiles after loading', async () => {
    render(<AssetPicker {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('company_logo.png')).toBeInTheDocument();
    });

    expect(screen.getByText('invoice_q1.pdf')).toBeInTheDocument();
  });

  it('calls onSelect when an asset tile is clicked', async () => {
    const onSelect = vi.fn();
    render(<AssetPicker {...defaultProps} onSelect={onSelect} />);

    await waitFor(() => {
      expect(screen.getByText('company_logo.png')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('asset-tile-ast_001'));

    expect(onSelect).toHaveBeenCalledWith(mockAssets[0]);
  });

  it('calls onClose after selecting an asset', async () => {
    const onClose = vi.fn();
    render(<AssetPicker {...defaultProps} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByText('company_logo.png')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('asset-tile-ast_001'));

    expect(onClose).toHaveBeenCalled();
  });

  it('shows file size and reference count on tiles', async () => {
    render(<AssetPicker {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('company_logo.png')).toBeInTheDocument();
    });

    // company_logo.png is 245000 bytes ≈ 239.3 KB
    expect(screen.getByText('239.3 KB')).toBeInTheDocument();
    expect(screen.getByText('3 refs')).toBeInTheDocument();
  });

  it('shows "No assets found" when search returns empty', async () => {
    fetchSpy.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({
        success: true,
        data: [],
        pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
      }),
      status: 200,
      headers: new Headers(),
    } as Response);

    render(<AssetPicker {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('No assets found')).toBeInTheDocument();
    });
  });

  it('applies defaultCategory to the category filter', () => {
    render(<AssetPicker {...defaultProps} defaultCategory="branding" />);

    const categorySelect = screen.getByTestId('asset-category-filter') as HTMLSelectElement;
    expect(categorySelect.value).toBe('branding');
  });

  it('applies defaultMediaType to the media type filter', () => {
    render(<AssetPicker {...defaultProps} defaultMediaType="image" />);

    const mediaTypeSelect = screen.getByTestId('asset-media-type-filter') as HTMLSelectElement;
    expect(mediaTypeSelect.value).toBe('image');
  });

  it('restricts media type options when allowedMediaTypes is provided', () => {
    render(<AssetPicker {...defaultProps} allowedMediaTypes={['image', 'video']} />);

    const mediaTypeSelect = screen.getByTestId('asset-media-type-filter');
    const options = mediaTypeSelect.querySelectorAll('option');
    const values = Array.from(options).map((o) => o.getAttribute('value'));

    expect(values).toContain('');
    expect(values).toContain('image');
    expect(values).toContain('video');
    expect(values).not.toContain('document');
  });

  it('shows error message on fetch failure', async () => {
    fetchSpy.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ error: 'Server error' }),
      status: 500,
      headers: new Headers(),
    } as unknown as Response);

    render(<AssetPicker {...defaultProps} />);

    await waitFor(() => {
      expect(screen.getByText('Server error')).toBeInTheDocument();
    });
  });
});
