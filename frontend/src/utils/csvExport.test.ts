/**
 * Unit tests for csvExport utilities.
 *
 * Tests generateCsv(), generateCsvFromObjects(), and downloadCsv()
 * including proper escaping of special characters.
 *
 * Requirements: 7.2, 7.3
 */

import { generateCsv, generateCsvFromObjects, sanitize, exportFileName } from './csvExport';

describe('generateCsv', () => {
  it('generates header-only CSV for empty rows', () => {
    const csv = generateCsv(['Name', 'Amount'], []);
    expect(csv).toBe('Name,Amount');
  });

  it('generates CSV with headers and data rows', () => {
    const csv = generateCsv(
      ['Channel', 'Amount'],
      [['Airbnb', 12345.67], ['Booking.com', 8901.23]],
    );
    const lines = csv.split('\n');
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe('Channel,Amount');
    expect(lines[1]).toBe('Airbnb,12345.67');
    expect(lines[2]).toBe('Booking.com,8901.23');
  });

  it('escapes fields containing commas', () => {
    const csv = generateCsv(['Name'], [['Hello, World']]);
    const lines = csv.split('\n');
    expect(lines[1]).toBe('"Hello, World"');
  });

  it('escapes fields containing double quotes', () => {
    const csv = generateCsv(['Name'], [['Say "hello"']]);
    const lines = csv.split('\n');
    expect(lines[1]).toBe('"Say ""hello"""');
  });

  it('escapes fields containing newlines', () => {
    const csv = generateCsv(['Name'], [['Line1\nLine2']]);
    const lines = csv.split('\n');
    // The field should be quoted, so splitting by \n gives us parts of the quoted field
    expect(csv).toContain('"Line1\nLine2"');
  });

  it('escapes header fields containing commas', () => {
    const csv = generateCsv(['Name, First'], [['John']]);
    expect(csv.startsWith('"Name, First"')).toBe(true);
  });

  it('converts null and undefined to empty string', () => {
    const csv = generateCsv(['A', 'B'], [[null, undefined]]);
    const lines = csv.split('\n');
    expect(lines[1]).toBe(',');
  });

  it('converts numbers to strings', () => {
    const csv = generateCsv(['Amount'], [[42]]);
    const lines = csv.split('\n');
    expect(lines[1]).toBe('42');
  });

  it('applies custom formatter to data cells', () => {
    const csv = generateCsv(
      ['Amount'],
      [[1234.5]],
      { formatter: (val) => `€${val}` },
    );
    const lines = csv.split('\n');
    expect(lines[1]).toBe('€1234.5');
  });

  it('uses custom delimiter', () => {
    const csv = generateCsv(
      ['A', 'B'],
      [['x', 'y']],
      { delimiter: ';' },
    );
    expect(csv).toBe('A;B\nx;y');
  });

  it('uses custom line separator', () => {
    const csv = generateCsv(
      ['A'],
      [['x']],
      { lineSeparator: '\r\n' },
    );
    expect(csv).toBe('A\r\nx');
  });

  it('produces consistent field count across all rows', () => {
    const headers = ['A', 'B', 'C'];
    const rows = [
      ['1', '2', '3'],
      ['4', '5', '6'],
    ];
    const csv = generateCsv(headers, rows);
    const lines = csv.split('\n');
    const headerCount = lines[0].split(',').length;
    for (const line of lines.slice(1)) {
      expect(line.split(',').length).toBe(headerCount);
    }
  });
});

describe('generateCsvFromObjects', () => {
  it('generates CSV from array of objects', () => {
    const columns = [
      { key: 'channel', header: 'Channel' },
      { key: 'amount', header: 'Amount' },
    ];
    const data = [
      { channel: 'Airbnb', amount: 100 },
      { channel: 'Booking.com', amount: 200 },
    ];

    const csv = generateCsvFromObjects(columns, data);
    const lines = csv.split('\n');
    expect(lines).toHaveLength(3);
    expect(lines[0]).toBe('Channel,Amount');
    expect(lines[1]).toBe('Airbnb,100');
    expect(lines[2]).toBe('Booking.com,200');
  });

  it('handles missing keys as undefined (empty string)', () => {
    const columns = [
      { key: 'name', header: 'Name' },
      { key: 'missing', header: 'Missing' },
    ];
    const data = [{ name: 'Test' }];

    const csv = generateCsvFromObjects(columns, data);
    const lines = csv.split('\n');
    expect(lines[1]).toBe('Test,');
  });

  it('applies formatter to object values', () => {
    const columns = [{ key: 'val', header: 'Value' }];
    const data = [{ val: 1000 }];

    const csv = generateCsvFromObjects(columns, data, {
      formatter: (val) => `$${val}`,
    });
    const lines = csv.split('\n');
    expect(lines[1]).toBe('$1000');
  });
});

// ---------------------------------------------------------------------------
// Export naming rule (shared tenant-pivot filename) — Requirements 5.1, 5.4
// ---------------------------------------------------------------------------

describe('sanitize', () => {
  it('leaves a plain name unchanged', () => {
    expect(sanitize('Acme')).toBe('Acme');
  });

  it('strips path separators', () => {
    expect(sanitize('a/b\\c')).toBe('abc');
  });

  it('strips ASCII control characters incl. newlines and NUL', () => {
    expect(sanitize('a\nb\tc\u0000d\u007f')).toBe('a b cd');
  });

  it('collapses runs of whitespace to a single space and trims the edges', () => {
    expect(sanitize('  Big   Charity\tFoundation  ')).toBe('Big Charity Foundation');
  });

  it('returns an empty string for empty / whitespace-only input', () => {
    expect(sanitize('')).toBe('');
    expect(sanitize('   ')).toBe('');
  });

  it('treats null/undefined as empty', () => {
    expect(sanitize(undefined as unknown as string)).toBe('');
    expect(sanitize(null as unknown as string)).toBe('');
  });

  it('preserves unicode letters', () => {
    expect(sanitize('Stichting Café')).toBe('Stichting Café');
  });
});

describe('exportFileName', () => {
  it('builds {Tenant}-{Pivot}.csv from the sanitized parts', () => {
    expect(exportFileName('Acme', 'Members by city')).toBe('Acme-Members by city.csv');
  });

  it('sanitizes both parts (no path separators or control chars leak through)', () => {
    // Path separators (/, \) are stripped outright; a newline is whitespace, so
    // it collapses to a single space (same rule as the `sanitize` cases above:
    // `a\nb` -> `a b`), never a deletion.
    expect(exportFileName('a/b', 'x\\y\nz')).toBe('ab-xy z.csv');
  });

  it('always ends in .csv', () => {
    expect(exportFileName('T', 'P').endsWith('.csv')).toBe(true);
    expect(exportFileName('', '').endsWith('.csv')).toBe(true);
  });

  it('is deterministic for the same inputs', () => {
    expect(exportFileName('Acme', 'Donors')).toBe(exportFileName('Acme', 'Donors'));
  });

  it('is never the fixed members.csv', () => {
    expect(exportFileName('members', '')).not.toBe('members.csv');
    expect(exportFileName('Acme', 'Donors')).not.toBe('members.csv');
  });
});
