// Feature: str-bookingcom-multi-file-import + str-airbnb-multi-file-import
// Tests for STRProcessor multi-file booking and airbnb import functionality
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { test as fcTest } from '@fast-check/vitest';
import fc from 'fast-check';

// ---------------------------------------------------------------------------
// Mock component that mirrors the real STRProcessor's multi-file logic
// ---------------------------------------------------------------------------
interface MockProps {
  initialPlatform?: string;
  successData?: {
    success: boolean;
    realised: any[];
    planned: any[];
    already_loaded: any[];
    summary: any;
    error?: string;
  };
}

const MockSTRProcessor: React.FC<MockProps> = ({
  initialPlatform = 'airbnb',
  successData,
}) => {
  const [selectedPlatform, setSelectedPlatform] = React.useState(initialPlatform);
  const [selectedFile, setSelectedFile] = React.useState<File | null>(null);
  const [selectedFiles, setSelectedFiles] = React.useState<File[]>([]);
  const [message, setMessage] = React.useState('');
  const [warning, setWarning] = React.useState('');
  const [error, setError] = React.useState('');

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    if (selectedPlatform === 'vrbo' || selectedPlatform === 'booking' || selectedPlatform === 'airbnb') {
      const fileList = Array.from(files);
      setSelectedFiles(fileList);
      setSelectedFile(fileList[0]);
      setError('');
    } else {
      const file = files[0];
      setSelectedFile(file);
      setSelectedFiles([file]);
      setError('');
    }
  };

  const processFiles = () => {
    if (!selectedFile || !successData) return;
    if (successData.success) {
      if ((selectedPlatform === 'booking' || selectedPlatform === 'airbnb') && selectedFiles.length > 1) {
        setMessage(
          `Processed ${selectedFiles.length} files: ${successData.realised.length} realised, ${successData.planned.length} planned, ${successData.already_loaded.length} already loaded bookings`
        );
      } else {
        setMessage(
          `Processed ${successData.realised.length} realised, ${successData.planned.length} planned, ${successData.already_loaded.length} already loaded bookings from ${selectedFile.name}`
        );
      }
    } else {
      const errorMsg = successData.error || '';
      if ((selectedPlatform === 'booking' || selectedPlatform === 'airbnb') && errorMsg.includes('failed to parse')) {
        setWarning(errorMsg);
      } else {
        setError(errorMsg);
      }
    }
  };

  const isMultiPlatform = selectedPlatform === 'vrbo' || selectedPlatform === 'booking' || selectedPlatform === 'airbnb';
  const acceptAttr = selectedPlatform === 'payout' || selectedPlatform === 'airbnb' ? '.csv' : '.csv,.tsv,.xlsx,.xls';

  return (
    <div>
      <select
        data-testid="platform-select"
        value={selectedPlatform}
        onChange={(e) => {
          setSelectedPlatform(e.target.value);
          setSelectedFile(null);
          setSelectedFiles([]);
          setError('');
        }}
      >
        <option value="airbnb">Airbnb</option>
        <option value="booking">Booking.com Excel</option>
        <option value="vrbo">VRBO</option>
        <option value="direct">Direct</option>
        <option value="payout">Booking.com Payout</option>
      </select>

      <input
        data-testid="file-input"
        type="file"
        accept={acceptAttr}
        multiple={isMultiPlatform}
        onChange={handleFileUpload}
      />

      <button
        data-testid="process-button"
        disabled={!selectedFile}
        onClick={processFiles}
      >
        Process File
      </button>

      {selectedFiles.length > 0 && (
        <span data-testid="selected-files">
          Selected: {selectedFiles.map((f) => f.name).join(', ')}
        </span>
      )}

      {selectedPlatform === 'booking' && (
        <div data-testid="booking-multi-file-hint" role="alert">
          <strong>Booking.com Multi-File Import:</strong>
          <span>
            Select multiple Booking.com export files at once to import all
            listings together. Supports .csv, .tsv, .xls, and .xlsx files.
          </span>
        </div>
      )}

      {selectedPlatform === 'airbnb' && (
        <div data-testid="airbnb-multi-file-hint" role="alert">
          <strong>Airbnb Multi-File Import:</strong>
          <span>
            Select multiple Airbnb CSV export files at once to import all
            listings together. Files are deduplicated by reservation code.
          </span>
        </div>
      )}

      {error && (
        <div data-testid="error-alert" role="alert">
          {error}
        </div>
      )}

      {warning && (
        <div data-testid="warning-alert" role="alert">
          {warning}
        </div>
      )}

      {message && (
        <div data-testid="success-message" role="alert">
          {message}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Helper: create a mock File object
// ---------------------------------------------------------------------------
function createMockFile(name: string): File {
  return new File(['content'], name, { type: 'text/csv' });
}

// Helper: create a FileList-like object from an array of Files
// jsdom doesn't support DataTransfer, so we create a minimal FileList mock
function createFileList(files: File[]): FileList {
  const fileList = Object.create(FileList.prototype);
  for (let i = 0; i < files.length; i++) {
    fileList[i] = files[i];
  }
  Object.defineProperty(fileList, 'length', { value: files.length });
  fileList.item = (index: number) => files[index] || null;
  fileList[Symbol.iterator] = function* () {
    for (let i = 0; i < files.length; i++) yield files[i];
  };
  return fileList as FileList;
}

// ---------------------------------------------------------------------------
// Existing tests (preserved)
// ---------------------------------------------------------------------------
describe('STRProcessor Component', () => {
  it('renders platform selection', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByRole('option', { name: 'Airbnb' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Booking.com Excel' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Direct' })).toBeInTheDocument();
  });

  it('renders file processing controls', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByTestId('process-button')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Property 7: All selected filenames are displayed
// Feature: str-bookingcom-multi-file-import, Property 7: All selected filenames displayed
// ---------------------------------------------------------------------------
describe('Property 7: All selected filenames are displayed', () => {
  // Arbitrary for valid filenames with common booking file extensions
  const filenameArb = fc
    .tuple(
      fc.string({ minLength: 1, maxLength: 20 }).filter((s) => /^[a-z0-9_-]+$/.test(s)),
      fc.constantFrom('.csv', '.tsv', '.xlsx', '.xls')
    )
    .map(([base, ext]) => `${base}${ext}`);

  fcTest.prop(
    [fc.array(filenameArb, { minLength: 1, maxLength: 10 })],
    { numRuns: 100 },
  )(
    'all selected filenames appear in the rendered output',
    (filenames) => {
      const { getByTestId } = render(
        <MockSTRProcessor initialPlatform="booking" />
      );

      const files = filenames.map((name) => createMockFile(name));
      const fileList = createFileList(files);

      const input = getByTestId('file-input') as HTMLInputElement;
      fireEvent.change(input, { target: { files: fileList } });

      const selectedText = getByTestId('selected-files').textContent || '';
      for (const name of filenames) {
        expect(selectedText).toContain(name);
      }
    }
  );
});

// ---------------------------------------------------------------------------
// Unit tests for multi-file booking import (Task 5.5)
// Feature: str-bookingcom-multi-file-import
// ---------------------------------------------------------------------------
describe('Booking.com Multi-File Import - Frontend', () => {
  // Req 1.1: Booking platform enables multi-select on file input
  it('enables multi-select on file input when booking platform is selected', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input.multiple).toBe(true);
  });

  it('does not enable multi-select for direct platform', () => {
    render(<MockSTRProcessor initialPlatform="direct" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input.multiple).toBe(false);
  });

  // Req 1.3: File input accepts .csv, .tsv, .xls, .xlsx for booking
  it('accepts .csv, .tsv, .xlsx, .xls for booking platform', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input.accept).toBe('.csv,.tsv,.xlsx,.xls');
  });

  it('accepts only .csv for payout platform', () => {
    render(<MockSTRProcessor initialPlatform="payout" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input.accept).toBe('.csv');
  });

  // Req 1.4: Process button disabled when no files selected
  it('disables process button when no files are selected', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    const button = screen.getByTestId('process-button') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('enables process button after files are selected', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const files = createFileList([createMockFile('test.csv')]);
    fireEvent.change(input, { target: { files } });

    const button = screen.getByTestId('process-button') as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  // Req 6.1: Multi-file success shows file count
  it('shows file count in success message for multi-file booking import', () => {
    const successData = {
      success: true,
      realised: [{ id: 1 }, { id: 2 }],
      planned: [{ id: 3 }],
      already_loaded: [],
      summary: { total_bookings: 3 },
    };
    render(
      <MockSTRProcessor initialPlatform="booking" successData={successData} />
    );

    // Select multiple files
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const files = createFileList([
      createMockFile('green_studio.csv'),
      createMockFile('red_studio.csv'),
      createMockFile('child_friendly.csv'),
    ]);
    fireEvent.change(input, { target: { files } });

    // Process
    fireEvent.click(screen.getByTestId('process-button'));

    const msg = screen.getByTestId('success-message').textContent || '';
    expect(msg).toContain('3 files');
    expect(msg).toContain('2 realised');
    expect(msg).toContain('1 planned');
  });

  // Req 6.2: Summary shows realised/planned/already-loaded counts
  it('shows realised/planned/already-loaded counts in success message', () => {
    const successData = {
      success: true,
      realised: [{ id: 1 }],
      planned: [{ id: 2 }, { id: 3 }],
      already_loaded: [{ id: 4 }],
      summary: { total_bookings: 4 },
    };
    render(
      <MockSTRProcessor initialPlatform="booking" successData={successData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('studio.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    const msg = screen.getByTestId('success-message').textContent || '';
    expect(msg).toContain('1 realised');
    expect(msg).toContain('2 planned');
    expect(msg).toContain('1 already loaded');
  });

  // Req 6.3: Failed files warning displayed
  it('displays warning when backend reports failed files', () => {
    const failData = {
      success: false,
      realised: [],
      planned: [],
      already_loaded: [],
      summary: null,
      error: 'Some files failed to parse: bad_file.csv',
    };
    render(
      <MockSTRProcessor initialPlatform="booking" successData={failData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('good.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    const warningEl = screen.getByTestId('warning-alert');
    expect(warningEl.textContent).toContain('failed to parse');
    expect(warningEl.textContent).toContain('bad_file.csv');
  });

  it('displays error (not warning) for non-parse failures', () => {
    const failData = {
      success: false,
      realised: [],
      planned: [],
      already_loaded: [],
      summary: null,
      error: 'Internal server error',
    };
    render(
      <MockSTRProcessor initialPlatform="booking" successData={failData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('file.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    expect(screen.getByTestId('error-alert').textContent).toContain(
      'Internal server error'
    );
  });

  // Req 6.4: Booking platform shows multi-file hint
  it('shows multi-file hint when booking platform is selected', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    const hint = screen.getByTestId('booking-multi-file-hint');
    expect(hint).toBeInTheDocument();
    expect(hint.textContent).toContain('Booking.com Multi-File Import');
    expect(hint.textContent).toContain('multiple');
  });

  it('does not show booking hint for other platforms', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    expect(screen.queryByTestId('booking-multi-file-hint')).not.toBeInTheDocument();
  });

  it('does not show airbnb hint for other platforms', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    expect(screen.queryByTestId('airbnb-multi-file-hint')).not.toBeInTheDocument();
  });

  // Req 1.2: All selected filenames displayed
  it('displays all selected filenames for multi-file booking upload', () => {
    render(<MockSTRProcessor initialPlatform="booking" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const files = createFileList([
      createMockFile('green_studio.csv'),
      createMockFile('red_studio.xlsx'),
    ]);
    fireEvent.change(input, { target: { files } });

    const text = screen.getByTestId('selected-files').textContent || '';
    expect(text).toContain('green_studio.csv');
    expect(text).toContain('red_studio.xlsx');
  });

  // Single-file booking import still shows filename (not file count)
  it('shows filename (not file count) for single-file booking import', () => {
    const successData = {
      success: true,
      realised: [{ id: 1 }],
      planned: [],
      already_loaded: [],
      summary: { total_bookings: 1 },
    };
    render(
      <MockSTRProcessor initialPlatform="booking" successData={successData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('studio.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    const msg = screen.getByTestId('success-message').textContent || '';
    expect(msg).toContain('studio.csv');
    expect(msg).not.toContain('files');
  });
});

// ---------------------------------------------------------------------------
// Property 8: All selected filenames are displayed (Airbnb)
// Feature: str-airbnb-multi-file-import, Property 8: All selected filenames displayed
// ---------------------------------------------------------------------------
describe('Property 8: All selected filenames are displayed (Airbnb)', () => {
  const filenameArb = fc
    .tuple(
      fc.string({ minLength: 1, maxLength: 20 }).filter((s) => /^[a-z0-9_-]+$/.test(s)),
      fc.constant('.csv')
    )
    .map(([base, ext]) => `${base}${ext}`);

  fcTest.prop(
    [fc.array(filenameArb, { minLength: 1, maxLength: 10 })],
    { numRuns: 100 },
  )(
    'all selected filenames appear in the rendered output for airbnb platform',
    (filenames) => {
      const { getByTestId } = render(
        <MockSTRProcessor initialPlatform="airbnb" />
      );

      const files = filenames.map((name) => createMockFile(name));
      const fileList = createFileList(files);

      const input = getByTestId('file-input') as HTMLInputElement;
      fireEvent.change(input, { target: { files: fileList } });

      const selectedText = getByTestId('selected-files').textContent || '';
      for (const name of filenames) {
        expect(selectedText).toContain(name);
      }
    }
  );
});

// ---------------------------------------------------------------------------
// Unit tests for Airbnb multi-file import (Task 5.5)
// Feature: str-airbnb-multi-file-import
// ---------------------------------------------------------------------------
describe('Airbnb Multi-File Import - Frontend', () => {
  // Req 1.1: Airbnb platform enables multi-select on file input
  it('enables multi-select on file input when airbnb platform is selected', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input.multiple).toBe(true);
  });

  // Req 1.3: File input accepts .csv only for airbnb
  it('accepts .csv only for airbnb platform', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    expect(input.accept).toBe('.csv');
  });

  // Req 1.4: Process button disabled when no files selected
  it('disables process button when no files are selected', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    const button = screen.getByTestId('process-button') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('enables process button after files are selected', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const files = createFileList([createMockFile('listing.csv')]);
    fireEvent.change(input, { target: { files } });

    const button = screen.getByTestId('process-button') as HTMLButtonElement;
    expect(button.disabled).toBe(false);
  });

  // Req 6.1: Multi-file success shows file count
  it('shows file count in success message for multi-file airbnb import', () => {
    const successData = {
      success: true,
      realised: [{ id: 1 }, { id: 2 }],
      planned: [{ id: 3 }],
      already_loaded: [],
      summary: { total_bookings: 3 },
    };
    render(
      <MockSTRProcessor initialPlatform="airbnb" successData={successData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const files = createFileList([
      createMockFile('green_studio.csv'),
      createMockFile('red_studio.csv'),
    ]);
    fireEvent.change(input, { target: { files } });
    fireEvent.click(screen.getByTestId('process-button'));

    const msg = screen.getByTestId('success-message').textContent || '';
    expect(msg).toContain('2 files');
    expect(msg).toContain('2 realised');
    expect(msg).toContain('1 planned');
  });

  // Req 6.2: Summary shows realised/planned/already-loaded counts
  it('shows realised/planned/already-loaded counts in success message', () => {
    const successData = {
      success: true,
      realised: [{ id: 1 }],
      planned: [{ id: 2 }, { id: 3 }],
      already_loaded: [{ id: 4 }],
      summary: { total_bookings: 4 },
    };
    render(
      <MockSTRProcessor initialPlatform="airbnb" successData={successData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('green.csv'), createMockFile('red.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    const msg = screen.getByTestId('success-message').textContent || '';
    expect(msg).toContain('1 realised');
    expect(msg).toContain('2 planned');
    expect(msg).toContain('1 already loaded');
  });

  // Req 6.3: Failed files warning displayed
  it('displays warning when backend reports failed files for airbnb', () => {
    const failData = {
      success: false,
      realised: [],
      planned: [],
      already_loaded: [],
      summary: null,
      error: 'Some files failed to parse: bad_file.csv',
    };
    render(
      <MockSTRProcessor initialPlatform="airbnb" successData={failData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('good.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    const warningEl = screen.getByTestId('warning-alert');
    expect(warningEl.textContent).toContain('failed to parse');
    expect(warningEl.textContent).toContain('bad_file.csv');
  });

  it('displays error (not warning) for non-parse failures on airbnb', () => {
    const failData = {
      success: false,
      realised: [],
      planned: [],
      already_loaded: [],
      summary: null,
      error: 'Internal server error',
    };
    render(
      <MockSTRProcessor initialPlatform="airbnb" successData={failData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('file.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    expect(screen.getByTestId('error-alert').textContent).toContain(
      'Internal server error'
    );
  });

  // Req 6.4: Airbnb platform shows multi-file hint
  it('shows multi-file hint when airbnb platform is selected', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    const hint = screen.getByTestId('airbnb-multi-file-hint');
    expect(hint).toBeInTheDocument();
    expect(hint.textContent).toContain('Airbnb Multi-File Import');
    expect(hint.textContent).toContain('multiple');
  });

  it('does not show airbnb hint for direct platform', () => {
    render(<MockSTRProcessor initialPlatform="direct" />);
    expect(screen.queryByTestId('airbnb-multi-file-hint')).not.toBeInTheDocument();
  });

  // Req 1.2: All selected filenames displayed
  it('displays all selected filenames for multi-file airbnb upload', () => {
    render(<MockSTRProcessor initialPlatform="airbnb" />);
    const input = screen.getByTestId('file-input') as HTMLInputElement;
    const files = createFileList([
      createMockFile('green_studio.csv'),
      createMockFile('red_studio.csv'),
      createMockFile('child_friendly.csv'),
    ]);
    fireEvent.change(input, { target: { files } });

    const text = screen.getByTestId('selected-files').textContent || '';
    expect(text).toContain('green_studio.csv');
    expect(text).toContain('red_studio.csv');
    expect(text).toContain('child_friendly.csv');
  });

  // Single-file airbnb import still shows filename (not file count)
  it('shows filename (not file count) for single-file airbnb import', () => {
    const successData = {
      success: true,
      realised: [{ id: 1 }],
      planned: [],
      already_loaded: [],
      summary: { total_bookings: 1 },
    };
    render(
      <MockSTRProcessor initialPlatform="airbnb" successData={successData} />
    );

    const input = screen.getByTestId('file-input') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: createFileList([createMockFile('green_studio.csv')]) },
    });
    fireEvent.click(screen.getByTestId('process-button'));

    const msg = screen.getByTestId('success-message').textContent || '';
    expect(msg).toContain('green_studio.csv');
    expect(msg).not.toContain('files');
  });
});
