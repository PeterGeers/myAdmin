/**
 * TemplatePreview Component Unit Tests
 * 
 * Tests for iframe rendering, loading states, and security sandbox.
 */

import React from 'react';
import { render, screen } from '@testing-library/react';
import { TemplatePreview } from '../TemplatePreview';

// Mock Chakra UI
jest.mock('@chakra-ui/react', () => require('../chakraMock').chakraMock);
jest.mock('@chakra-ui/icons', () => require('../chakraMock').iconsMock);

describe('TemplatePreview', () => {
  describe('No Preview State', () => {
    it('shows placeholder when no preview HTML', () => {
      render(<TemplatePreview previewHtml="" />);
      
      expect(screen.getByText(/no preview available/i)).toBeInTheDocument();
      expect(screen.getByText(/upload a template to see the preview/i)).toBeInTheDocument();
    });

    it('shows dashed border for empty state', () => {
      render(<TemplatePreview previewHtml="" />);
      
      const placeholder = screen.getByText(/no preview available/i).closest('div');
      expect(placeholder).toHaveStyle({ borderStyle: 'dashed' });
    });
  });

  describe('Loading State', () => {
    it('shows loading skeletons when loading', () => {
      render(<TemplatePreview previewHtml="" loading={true} />);
      
      // Chakra Skeleton components are rendered
      const skeletons = document.querySelectorAll('[class*="chakra-skeleton"]');
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('hides preview when loading', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" loading={true} />);
      
      expect(screen.queryByTitle(/template preview/i)).not.toBeInTheDocument();
    });

    it('hides placeholder when loading', () => {
      render(<TemplatePreview previewHtml="" loading={true} />);
      
      expect(screen.queryByText(/no preview available/i)).not.toBeInTheDocument();
    });
  });

  describe('Preview Rendering', () => {
    const sampleHtml = '<html><head><title>Test</title></head><body><h1>Preview</h1></body></html>';

    it('renders iframe with preview HTML', () => {
      render(<TemplatePreview previewHtml={sampleHtml} />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toBeInTheDocument();
      expect(iframe).toHaveAttribute('srcdoc', sampleHtml);
    });

    it('applies sandbox attribute to iframe', () => {
      render(<TemplatePreview previewHtml={sampleHtml} />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toHaveAttribute('sandbox', 'allow-same-origin');
    });

    it('sets iframe dimensions to 100%', () => {
      render(<TemplatePreview previewHtml={sampleHtml} />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toHaveStyle({ width: '100%', height: '100%' });
    });

    it('removes iframe border', () => {
      render(<TemplatePreview previewHtml={sampleHtml} />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toHaveStyle({ border: 'none' });
    });
  });

  describe('Sample Data Info', () => {
    const sampleHtml = '<html><body>Test</body></html>';

    it('shows database source info', () => {
      render(
        <TemplatePreview
          previewHtml={sampleHtml}
          sampleDataInfo={{ source: 'database', record_count: 5 }}
        />
      );
      
      expect(screen.getByText(/loaded from database/i)).toBeInTheDocument();
      expect(screen.getByText(/5 record\(s\)/i)).toBeInTheDocument();
    });

    it('shows placeholder source info', () => {
      render(
        <TemplatePreview
          previewHtml={sampleHtml}
          sampleDataInfo={{ source: 'placeholder' }}
        />
      );
      
      expect(screen.getByText(/using placeholder data/i)).toBeInTheDocument();
      expect(screen.getByText(/no real data available/i)).toBeInTheDocument();
    });

    it('shows generic message when no sample data info', () => {
      render(<TemplatePreview previewHtml={sampleHtml} />);
      
      expect(screen.getByText(/this shows how your template will look with sample data/i)).toBeInTheDocument();
      expect(screen.queryByText(/loaded from/i)).not.toBeInTheDocument();
    });

    it('handles database source without record count', () => {
      render(
        <TemplatePreview
          previewHtml={sampleHtml}
          sampleDataInfo={{ source: 'database' }}
        />
      );
      
      expect(screen.getByText(/loaded from database/i)).toBeInTheDocument();
      expect(screen.queryByText(/record\(s\)/i)).not.toBeInTheDocument();
    });
  });

  describe('Security Note', () => {
    it('always shows security warning', () => {
      render(<TemplatePreview previewHtml="" />);
      
      expect(screen.getByText(/security:/i)).toBeInTheDocument();
      expect(screen.getByText(/sandboxed iframe/i)).toBeInTheDocument();
      expect(screen.getByText(/no javascript will execute/i)).toBeInTheDocument();
    });

    it('shows security warning even when loading', () => {
      render(<TemplatePreview previewHtml="" loading={true} />);
      
      expect(screen.getByText(/security:/i)).toBeInTheDocument();
    });

    it('shows security warning with preview', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" />);
      
      expect(screen.getByText(/security:/i)).toBeInTheDocument();
    });
  });

  describe('Info Alert', () => {
    it('shows info alert with sample data message', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" />);
      
      const alert = screen.getByText(/this shows how your template will look/i).closest('[role="alert"]');
      expect(alert).toBeInTheDocument();
    });
  });

  describe('Layout', () => {
    it('sets minimum height for preview container', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" />);
      
      const iframe = screen.getByTitle(/template preview/i);
      const container = iframe.closest('div');
      expect(container).toHaveStyle({ minHeight: '600px' });
    });

    it('sets minimum height for placeholder', () => {
      render(<TemplatePreview previewHtml="" />);
      
      const placeholder = screen.getByText(/no preview available/i).closest('div');
      expect(placeholder).toHaveStyle({ minHeight: '600px' });
    });

    it('uses white background for preview', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" />);
      
      const iframe = screen.getByTitle(/template preview/i);
      const container = iframe.closest('div');
      expect(container).toHaveStyle({ backgroundColor: 'white' });
    });
  });

  describe('Edge Cases', () => {
    it('handles empty HTML string', () => {
      render(<TemplatePreview previewHtml="" />);
      
      expect(screen.getByText(/no preview available/i)).toBeInTheDocument();
    });

    it('handles null sample data info', () => {
      render(
        <TemplatePreview
          previewHtml="<html><body>Test</body></html>"
          sampleDataInfo={null}
        />
      );
      
      expect(screen.queryByText(/loaded from/i)).not.toBeInTheDocument();
    });

    it('handles complex HTML with special characters', () => {
      const complexHtml = '<html><body><div>Test & "quotes" <script>alert("test")</script></div></body></html>';
      render(<TemplatePreview previewHtml={complexHtml} />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toHaveAttribute('srcdoc', complexHtml);
    });

    it('handles very long HTML content', () => {
      const longHtml = '<html><body>' + 'x'.repeat(10000) + '</body></html>';
      render(<TemplatePreview previewHtml={longHtml} />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toHaveAttribute('srcdoc', longHtml);
    });
  });

  describe('Accessibility', () => {
    it('has accessible iframe title', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" />);
      
      const iframe = screen.getByTitle(/template preview/i);
      expect(iframe).toHaveAttribute('title', 'Template Preview');
    });

    it('has accessible alert roles', () => {
      render(<TemplatePreview previewHtml="<html><body>Test</body></html>" />);
      
      const alerts = screen.getAllByRole('alert');
      expect(alerts.length).toBeGreaterThan(0);
    });
  });
});






