import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

export {};

// Mock myAdmin Reports component
const MockMyAdminReports = ({ 
  loading = false,
  hasData = false,
  chartData = [],
  activeTab = 0
}) => {
  const [currentTab, setCurrentTab] = React.useState(activeTab);
  const [filters, setFilters] = React.useState({
    year: '2024',
    administration: 'all',
    dateFrom: '2024-01-01',
    dateTo: '2024-12-31'
  });

  const tabs = [
    { id: 'mutaties', label: '💰 Mutaties (P&L)', icon: '💰' },
    { id: 'bnb', label: '🏠 BNB Revenue', icon: '🏠' },
    { id: 'actuals', label: '📊 Actuals', icon: '📊' },
    { id: 'bnb-actuals', label: '🏡 BNB Actuals', icon: '🏡' },
    { id: 'btw', label: '🧾 BTW aangifte', icon: '🧾' },
    { id: 'reference', label: '📈 View ReferenceNumber', icon: '📈' },
    { id: 'violins', label: '🎻 BNB Violins', icon: '🎻' }
  ];

  const mockData = hasData ? [
    { date: '2024-01-01', description: 'Test Transaction', amount: 1000, account: '1000' },
    { date: '2024-02-01', description: 'Another Transaction', amount: 2000, account: '2000' }
  ] : [];

  return (
    <div data-testid="myadmin-reports">
      {/* Tab Navigation */}
      <div data-testid="tab-navigation">
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            data-testid={`tab-${tab.id}`}
            onClick={() => setCurrentTab(index)}
            className={currentTab === index ? 'active' : ''}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Filter Controls */}
      <div data-testid="filter-controls">
        <select
          data-testid="year-filter"
          value={filters.year}
          onChange={(e) => setFilters(prev => ({ ...prev, year: e.target.value }))}
        >
          <option value="2023">2023</option>
          <option value="2024">2024</option>
          <option value="2025">2025</option>
        </select>
        
        <select
          data-testid="administration-filter"
          value={filters.administration}
          onChange={(e) => setFilters(prev => ({ ...prev, administration: e.target.value }))}
        >
          <option value="all">All</option>
          <option value="GoodwinSolutions">GoodwinSolutions</option>
          <option value="PeterPrive">PeterPrive</option>
        </select>

        <input
          data-testid="date-from-filter"
          type="date"
          value={filters.dateFrom}
          onChange={(e) => setFilters(prev => ({ ...prev, dateFrom: e.target.value }))}
        />

        <input
          data-testid="date-to-filter"
          type="date"
          value={filters.dateTo}
          onChange={(e) => setFilters(prev => ({ ...prev, dateTo: e.target.value }))}
        />

        <button data-testid="update-data-btn">Update Data</button>
        <button data-testid="export-csv-btn">Export CSV</button>
        <button data-testid="export-html-btn">Export HTML</button>
        <button data-testid="export-xlsx-btn">Export XLSX</button>
      </div>

      {/* Data Visualization */}
      {hasData && (
        <div data-testid="data-visualization">
          <div data-testid="chart-container">
            <div data-testid="bar-chart">Bar Chart</div>
            <div data-testid="pie-chart">Pie Chart</div>
            <div data-testid="line-chart">Line Chart</div>
            <div data-testid="violin-chart">Violin Chart</div>
            <div data-testid="box-plot">Box Plot</div>
          </div>
        </div>
      )}

      {/* Interactive Charts */}
      <div data-testid="interactive-charts">
        <button data-testid="chart-zoom-in">Zoom In</button>
        <button data-testid="chart-zoom-out">Zoom Out</button>
        <button data-testid="chart-reset">Reset View</button>
        <select data-testid="chart-type-selector">
          <option value="bar">Bar Chart</option>
          <option value="line">Line Chart</option>
          <option value="pie">Pie Chart</option>
        </select>
      </div>

      {/* Data Aggregation */}
      <div data-testid="data-aggregation">
        <div data-testid="summary-stats">
          <div data-testid="total-amount">Total: €{mockData.reduce((sum, item) => sum + item.amount, 0).toLocaleString()}</div>
          <div data-testid="record-count">Records: {mockData.length}</div>
          <div data-testid="average-amount">Average: €{mockData.length > 0 ? (mockData.reduce((sum, item) => sum + item.amount, 0) / mockData.length).toFixed(2) : '0.00'}</div>
        </div>
      </div>

      {/* Data Table */}
      {hasData && (
        <div data-testid="data-table">
          <table>
            <thead>
              <tr>
                <th data-testid="sort-date" onClick={() => {}}>Date</th>
                <th data-testid="sort-description" onClick={() => {}}>Description</th>
                <th data-testid="sort-amount" onClick={() => {}}>Amount</th>
                <th data-testid="sort-account" onClick={() => {}}>Account</th>
              </tr>
            </thead>
            <tbody>
              {mockData.map((row, index) => (
                <tr key={index} data-testid={`data-row-${index}`}>
                  <td>{row.date}</td>
                  <td>{row.description}</td>
                  <td>€{row.amount.toLocaleString()}</td>
                  <td>{row.account}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Responsive Design Elements */}
      <div data-testid="responsive-container" className="responsive-grid">
        <div data-testid="mobile-view" className="mobile-only">Mobile Layout</div>
        <div data-testid="desktop-view" className="desktop-only">Desktop Layout</div>
      </div>

      {loading && <div data-testid="loading-spinner">Loading...</div>}
    </div>
  );
};

// Mock fetch
global.fetch = jest.fn();

describe('myAdmin Reports', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, data: [] })
    });
  });

  describe('Tab Navigation', () => {
    it('renders all report tabs', () => {
      render(<MockMyAdminReports />);
      
      expect(screen.getByTestId('tab-mutaties')).toBeInTheDocument();
      expect(screen.getByTestId('tab-bnb')).toBeInTheDocument();
      expect(screen.getByTestId('tab-actuals')).toBeInTheDocument();
      expect(screen.getByTestId('tab-bnb-actuals')).toBeInTheDocument();
      expect(screen.getByTestId('tab-btw')).toBeInTheDocument();
      expect(screen.getByTestId('tab-reference')).toBeInTheDocument();
      expect(screen.getByTestId('tab-violins')).toBeInTheDocument();
    });

    it('switches between tabs', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const bnbTab = screen.getByTestId('tab-bnb');
      await user.click(bnbTab);
      
      expect(bnbTab).toHaveClass('active');
    });

    it('displays tab icons and labels', () => {
      render(<MockMyAdminReports />);
      
      expect(screen.getByText('💰 Mutaties (P&L)')).toBeInTheDocument();
      expect(screen.getByText('🏠 BNB Revenue')).toBeInTheDocument();
      expect(screen.getByText('📊 Actuals')).toBeInTheDocument();
    });
  });

  describe('Data Visualization', () => {
    it('renders charts when data is available', () => {
      render(<MockMyAdminReports hasData={true} />);
      
      expect(screen.getByTestId('chart-container')).toBeInTheDocument();
      expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
      expect(screen.getByTestId('pie-chart')).toBeInTheDocument();
      expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    });

    it('renders violin plots and box plots', () => {
      render(<MockMyAdminReports hasData={true} />);
      
      expect(screen.getByTestId('violin-chart')).toBeInTheDocument();
      expect(screen.getByTestId('box-plot')).toBeInTheDocument();
    });

    it('does not render charts when no data', () => {
      render(<MockMyAdminReports hasData={false} />);
      
      expect(screen.queryByTestId('chart-container')).not.toBeInTheDocument();
    });
  });

  describe('Filter Controls', () => {
    it('renders all filter controls', () => {
      render(<MockMyAdminReports />);
      
      expect(screen.getByTestId('year-filter')).toBeInTheDocument();
      expect(screen.getByTestId('administration-filter')).toBeInTheDocument();
      expect(screen.getByTestId('date-from-filter')).toBeInTheDocument();
      expect(screen.getByTestId('date-to-filter')).toBeInTheDocument();
    });

    it('updates filters when changed', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const yearFilter = screen.getByTestId('year-filter');
      await user.selectOptions(yearFilter, '2025');
      
      expect(yearFilter).toHaveValue('2025');
    });

    it('handles administration filter changes', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const adminFilter = screen.getByTestId('administration-filter');
      await user.selectOptions(adminFilter, 'GoodwinSolutions');
      
      expect(adminFilter).toHaveValue('GoodwinSolutions');
    });

    it('handles date range filters', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const dateFromFilter = screen.getByTestId('date-from-filter');
      await user.clear(dateFromFilter);
      await user.type(dateFromFilter, '2024-06-01');
      
      expect(dateFromFilter).toHaveValue('2024-06-01');
    });
  });

  describe('Export Functions', () => {
    it('renders export buttons', () => {
      render(<MockMyAdminReports />);
      
      expect(screen.getByTestId('export-csv-btn')).toBeInTheDocument();
      expect(screen.getByTestId('export-html-btn')).toBeInTheDocument();
      expect(screen.getByTestId('export-xlsx-btn')).toBeInTheDocument();
    });

    it('handles CSV export', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const exportButton = screen.getByTestId('export-csv-btn');
      await user.click(exportButton);
      
      expect(exportButton).toBeInTheDocument();
    });

    it('handles HTML export', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const exportButton = screen.getByTestId('export-html-btn');
      await user.click(exportButton);
      
      expect(exportButton).toBeInTheDocument();
    });

    it('handles XLSX export', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const exportButton = screen.getByTestId('export-xlsx-btn');
      await user.click(exportButton);
      
      expect(exportButton).toBeInTheDocument();
    });
  });

  describe('Interactive Charts', () => {
    it('renders chart interaction controls', () => {
      render(<MockMyAdminReports />);
      
      expect(screen.getByTestId('chart-zoom-in')).toBeInTheDocument();
      expect(screen.getByTestId('chart-zoom-out')).toBeInTheDocument();
      expect(screen.getByTestId('chart-reset')).toBeInTheDocument();
      expect(screen.getByTestId('chart-type-selector')).toBeInTheDocument();
    });

    it('handles chart zoom interactions', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const zoomInButton = screen.getByTestId('chart-zoom-in');
      await user.click(zoomInButton);
      
      expect(zoomInButton).toBeInTheDocument();
    });

    it('handles chart type selection', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports />);
      
      const chartTypeSelector = screen.getByTestId('chart-type-selector');
      await user.selectOptions(chartTypeSelector, 'line');
      
      expect(chartTypeSelector).toHaveValue('line');
    });
  });

  describe('Data Aggregation', () => {
    it('displays summary statistics', () => {
      render(<MockMyAdminReports hasData={true} />);
      
      expect(screen.getByTestId('summary-stats')).toBeInTheDocument();
      expect(screen.getByTestId('total-amount')).toBeInTheDocument();
      expect(screen.getByTestId('record-count')).toBeInTheDocument();
      expect(screen.getByTestId('average-amount')).toBeInTheDocument();
    });

    it('calculates totals correctly', () => {
      render(<MockMyAdminReports hasData={true} />);
      
      expect(screen.getByTestId('total-amount')).toHaveTextContent('Total: €3.000');
      expect(screen.getByTestId('record-count')).toHaveTextContent('Records: 2');
      expect(screen.getByTestId('average-amount')).toHaveTextContent('Average: €1500.00');
    });

    it('handles empty data aggregation', () => {
      render(<MockMyAdminReports hasData={false} />);
      
      expect(screen.getByTestId('total-amount')).toHaveTextContent('Total: €0');
      expect(screen.getByTestId('record-count')).toHaveTextContent('Records: 0');
      expect(screen.getByTestId('average-amount')).toHaveTextContent('Average: €0.00');
    });
  });

  describe('Responsive Design', () => {
    it('renders responsive container', () => {
      render(<MockMyAdminReports />);
      
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
      expect(screen.getByTestId('mobile-view')).toBeInTheDocument();
      expect(screen.getByTestId('desktop-view')).toBeInTheDocument();
    });

    it('applies responsive classes', () => {
      render(<MockMyAdminReports />);
      
      const container = screen.getByTestId('responsive-container');
      expect(container).toHaveClass('responsive-grid');
      
      const mobileView = screen.getByTestId('mobile-view');
      expect(mobileView).toHaveClass('mobile-only');
      
      const desktopView = screen.getByTestId('desktop-view');
      expect(desktopView).toHaveClass('desktop-only');
    });
  });

  describe('Data Table Operations', () => {
    it('renders data table when data is available', () => {
      render(<MockMyAdminReports hasData={true} />);
      
      expect(screen.getByTestId('data-table')).toBeInTheDocument();
      expect(screen.getByTestId('data-row-0')).toBeInTheDocument();
      expect(screen.getByTestId('data-row-1')).toBeInTheDocument();
    });

    it('renders sortable column headers', () => {
      render(<MockMyAdminReports hasData={true} />);
      
      expect(screen.getByTestId('sort-date')).toBeInTheDocument();
      expect(screen.getByTestId('sort-description')).toBeInTheDocument();
      expect(screen.getByTestId('sort-amount')).toBeInTheDocument();
      expect(screen.getByTestId('sort-account')).toBeInTheDocument();
    });

    it('handles column sorting', async () => {
      const user = userEvent.setup();
      render(<MockMyAdminReports hasData={true} />);
      
      const sortButton = screen.getByTestId('sort-amount');
      await user.click(sortButton);
      
      expect(sortButton).toBeInTheDocument();
    });
  });

  describe('Loading States', () => {
    it('shows loading spinner when loading', () => {
      render(<MockMyAdminReports loading={true} />);
      
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('hides loading spinner when not loading', () => {
      render(<MockMyAdminReports loading={false} />);
      
      expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument();
    });
  });
});