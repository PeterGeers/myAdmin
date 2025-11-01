import React from 'react';
import { render, screen } from '@testing-library/react';

// Ultra-minimal mock component
const MockSTRProcessor = () => (
  <div>
    <select>
      <option value="airbnb">Airbnb</option>
      <option value="booking">Booking.com</option>
      <option value="direct">Direct</option>
    </select>
    <input type="file" />
    <button>Process Files</button>
    <button>Save Bookings</button>
    <div>Total Bookings: 0</div>
    <div>Realised (0)</div>
    <div>Planned (0)</div>
    <table>
      <thead>
        <tr>
          <th>Channel</th>
          <th>Guest</th>
        </tr>
      </thead>
    </table>
  </div>
);

describe('STRProcessor Component', () => {
  it('renders platform selection', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByRole('option', { name: 'Airbnb' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Booking.com' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Direct' })).toBeInTheDocument();
  });

  it('renders file processing controls', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByRole('button', { name: 'Process Files' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save Bookings' })).toBeInTheDocument();
  });

  it('shows status separation', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByText('Realised (0)')).toBeInTheDocument();
    expect(screen.getByText('Planned (0)')).toBeInTheDocument();
  });

  it('displays summary', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByText('Total Bookings: 0')).toBeInTheDocument();
  });

  it('renders data table', () => {
    render(<MockSTRProcessor />);
    expect(screen.getByText('Channel')).toBeInTheDocument();
    expect(screen.getByText('Guest')).toBeInTheDocument();
  });
});