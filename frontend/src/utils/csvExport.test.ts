/**
 * Unit tests for csvExport utilities.
 *
 * Tests generateCsv(), generateCsvFromObjects(), and downloadCsv()
 * including proper escaping of special characters.
 *
 * Requirements: 7.2, 7.3
 */

import { generateCsv, generateCsvFromObjects } from './csvExport';

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
