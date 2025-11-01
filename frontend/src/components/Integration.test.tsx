import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock fetch
global.fetch = jest.fn();

// Mock parent-child communication
const ParentComponent = () => {
  const [data, setData] = React.useState('');
  return (
    <div>
      <ChildComponent onDataChange={setData} />
      <div data-testid="parent-data">{data}</div>
    </div>
  );
};

const ChildComponent = ({ onDataChange }: { onDataChange: (data: string) => void }) => (
  <button onClick={() => onDataChange('child data')}>
    Update Parent
  </button>
);

// Mock context provider
const TestContext = React.createContext({ user: 'guest' });

const ContextProvider = ({ children }: { children: React.ReactNode }) => (
  <TestContext.Provider value={{ user: 'admin' }}>
    {children}
  </TestContext.Provider>
);

const ContextConsumer = () => {
  const { user } = React.useContext(TestContext);
  return <div>User: {user}</div>;
};

// Mock API integration
const APIComponent = () => {
  const [data, setData] = React.useState('');
  const [loading, setLoading] = React.useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/test');
      const result = await response.json();
      setData(result.message);
    } catch (error) {
      setData('Error loading data');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <button onClick={fetchData}>Fetch Data</button>
      {loading && <div>Loading...</div>}
      <div data-testid="api-data">{data}</div>
    </div>
  );
};

// Mock form submission
const FormComponent = () => {
  const [submitted, setSubmitted] = React.useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
  };

  return (
    <form onSubmit={handleSubmit}>
      <input name="email" placeholder="Email" />
      <button type="submit">Submit</button>
      {submitted && <div>Form submitted</div>}
    </form>
  );
};

// Mock navigation flow
const NavigationComponent = () => {
  const [currentView, setCurrentView] = React.useState('home');

  return (
    <div>
      <nav>
        <button onClick={() => setCurrentView('home')}>Home</button>
        <button onClick={() => setCurrentView('about')}>About</button>
        <button onClick={() => setCurrentView('contact')}>Contact</button>
      </nav>
      <main>
        {currentView === 'home' && <div>Home Page</div>}
        {currentView === 'about' && <div>About Page</div>}
        {currentView === 'contact' && <div>Contact Page</div>}
      </main>
    </div>
  );
};

describe('Integration Tests', () => {
  beforeEach(() => {
    (fetch as jest.Mock).mockClear();
  });

  describe('Parent-child communication', () => {
    it('passes data from child to parent', async () => {
      const user = userEvent.setup();
      render(<ParentComponent />);

      const button = screen.getByText('Update Parent');
      await user.click(button);

      expect(screen.getByTestId('parent-data')).toHaveTextContent('child data');
    });
  });

  describe('Context providers', () => {
    it('provides context data to consumers', () => {
      render(
        <ContextProvider>
          <ContextConsumer />
        </ContextProvider>
      );

      expect(screen.getByText('User: admin')).toBeInTheDocument();
    });

    it('uses default context when no provider', () => {
      render(<ContextConsumer />);
      expect(screen.getByText('User: guest')).toBeInTheDocument();
    });
  });

  describe('API integration', () => {
    it('fetches and displays data', async () => {
      const user = userEvent.setup();
      (fetch as jest.Mock).mockResolvedValue({
        json: () => Promise.resolve({ message: 'API data loaded' })
      });

      render(<APIComponent />);

      const button = screen.getByText('Fetch Data');
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByTestId('api-data')).toHaveTextContent('API data loaded');
      });
    });

    it('handles API errors', async () => {
      const user = userEvent.setup();
      (fetch as jest.Mock).mockRejectedValue(new Error('API Error'));

      render(<APIComponent />);

      const button = screen.getByText('Fetch Data');
      await user.click(button);

      await waitFor(() => {
        expect(screen.getByTestId('api-data')).toHaveTextContent('Error loading data');
      });
    });
  });

  describe('Form submissions', () => {
    it('handles form submission', async () => {
      const user = userEvent.setup();
      render(<FormComponent />);

      const input = screen.getByPlaceholderText('Email');
      const button = screen.getByText('Submit');

      await user.type(input, 'test@example.com');
      await user.click(button);

      expect(screen.getByText('Form submitted')).toBeInTheDocument();
    });
  });

  describe('Navigation flows', () => {
    it('navigates between views', async () => {
      const user = userEvent.setup();
      render(<NavigationComponent />);

      expect(screen.getByText('Home Page')).toBeInTheDocument();

      await user.click(screen.getByText('About'));
      expect(screen.getByText('About Page')).toBeInTheDocument();

      await user.click(screen.getByText('Contact'));
      expect(screen.getByText('Contact Page')).toBeInTheDocument();

      await user.click(screen.getByText('Home'));
      expect(screen.getByText('Home Page')).toBeInTheDocument();
    });
  });

  describe('Component integration', () => {
    it('integrates multiple components', async () => {
      const user = userEvent.setup();
      
      const IntegratedApp = () => (
        <ContextProvider>
          <div>
            <ContextConsumer />
            <FormComponent />
          </div>
        </ContextProvider>
      );

      render(<IntegratedApp />);

      expect(screen.getByText('User: admin')).toBeInTheDocument();

      const submitButton = screen.getByText('Submit');
      await user.click(submitButton);

      expect(screen.getByText('Form submitted')).toBeInTheDocument();
    });
  });
});