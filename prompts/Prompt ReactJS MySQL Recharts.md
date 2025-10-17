# 📊 myReporting: React + MySQL + Recharts Reporting Dashboard
## 📚 Resources

- **Recharts Documentation**: https://recharts.org/en-US/
- **Recharts Examples**: https://recharts.org/en-US/examples/
- **React Grid Layout**: https://github.com/react-grid-layout/react-grid-layout
- **Chakra UI Components**: https://chakra-ui.com/
- **React TypeScript**: https://react-typescript-cheatsheet.netlify.app/

## 🛠 Aanbevelingen
- Gebruik `ResponsiveContainer` voor alle charts
- Implementeer loading states en error handling
- Gebruik TypeScript voor type safety
- Test charts op verschillende schermgroottes
- Optimaliseer data queries voor performance
- Gebruik `.env` voor database configuratie
- Sla dashboard layout op in localStorage of database
- Implementeer widget add/remove functionaliteit
- Voeg export functie toe voor dashboard screenshots


## ✅ Doel
Een veilige, interactieve rapportagefunctie bouwen in ReactJS die financiële data uit een MySQL-database ophaalt en visualiseert met Recharts.

## 🧱 Architectuur

| Component     | Technologie         | Functie                                 |
|---------------|---------------------|------------------------------------------|
| Frontend      | ReactJS + Recharts  | UI en interactieve visualisaties        |
| Dashboard     | React Grid Layout   | Draggable, resizable dashboard widgets  |
| Backend API   | Python Flask        | Data ophalen en filteren via REST API   |
| Database      | MySQL               | Opslag van financiële gegevens          |
| UI Framework  | Chakra UI           | Moderne, responsive componenten          |

## 🔧 Functionaliteiten

### 1. 📈 Data Visualisatie met Recharts
- **Pie Charts**: Cirkeldiagrammen voor verdeling van categorieën
- **Line Charts**: Lijngrafieken voor trends over tijd
- **Bar Charts**: Staafdiagrammen voor vergelijkingen
- **BiaxialBarChart**: Dubbele Y-as voor verschillende metrics
- **Responsive Containers**: Automatische aanpassing aan schermgrootte
- **Interactive Tooltips**: Hover-effecten met gedetailleerde informatie

#### Recharts Voorbeelden
Bekijk uitgebreide voorbeelden op: **https://recharts.org/en-US/examples/**

### 2. 🔍 Dynamische Filters
- **Datum filters**: Van/tot datum selectie
- **Categorie filters**: Dropdown met dynamische opties uit database
- **Administratie filters**: Scheiding tussen verschillende administraties
- **Real-time filtering**: Directe update van charts bij filter wijziging

### 3. 📤 Exportopties
- **CSV Export**: Data downloaden als spreadsheet
- **Responsive Design**: Optimaal voor desktop en mobile

### 4. 🎨 UI/UX met Chakra UI
- **Dark Theme**: Professionele donkere interface
- **Responsive Grid**: Automatische layout aanpassing
- **Loading States**: Spinners en loading indicatoren
- **Error Handling**: Gebruiksvriendelijke foutmeldingen

### 5. 📋 Dashboard Layout met React Grid Layout
- **Draggable Widgets**: Sleep en plaats chart componenten
- **Resizable Charts**: Pas chart grootte aan naar behoefte
- **Responsive Breakpoints**: Automatische aanpassing per schermgrootte
- **Persistent Layout**: Sla gebruiker layout voorkeuren op
- **Widget Management**: Voeg toe, verwijder en configureer widgets

## 📊 Recharts Implementatie

### Basic Setup
```bash
# Core dashboard packages
npm install recharts react-grid-layout
npm install @chakra-ui/react @emotion/react @emotion/styled
npm install framer-motion

# Optional enhancements
npm install react-window react-virtualized-auto-sizer  # For large datasets
npm install date-fns  # Date handling
npm install lodash  # Data manipulation
```

### Pie Chart Voorbeeld
```tsx
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

<ResponsiveContainer width="100%" height={400}>
  <PieChart>
    <Pie
      data={chartData}
      cx="50%"
      cy="50%"
      innerRadius={80}
      outerRadius={160}
      paddingAngle={2}
      dataKey="value"
    >
      {chartData.map((entry, index) => (
        <Cell key={`cell-${index}`} fill={`hsl(${index * 45}, 70%, 60%)`} />
      ))}
    </Pie>
    <Tooltip 
      content={({ active, payload }) => {
        if (active && payload && payload.length) {
          return (
            <Box bg="gray.700" p={2} borderRadius="md">
              <Text color="white">{payload[0].name}</Text>
              <Text color="white">€{payload[0].value.toLocaleString('nl-NL')}</Text>
            </Box>
          );
        }
        return null;
      }}
    />
  </PieChart>
</ResponsiveContainer>
```

### Line Chart Voorbeeld
```tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

<ResponsiveContainer width="100%" height={400}>
  <LineChart data={trendsData}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="month" />
    <YAxis />
    <Tooltip />
    <Line type="monotone" dataKey="amount" stroke="#8884d8" strokeWidth={2} />
  </LineChart>
</ResponsiveContainer>
```

### Bar Chart Voorbeeld
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

<ResponsiveContainer width="100%" height={400}>
  <BarChart data={chartData}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="name" />
    <YAxis />
    <Tooltip />
    <Bar dataKey="value" fill="#8884d8" />
  </BarChart>
</ResponsiveContainer>
```

### BiaxialBarChart Voorbeeld
```tsx
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';

// Data met twee verschillende metrics
const biaxialData = [
  { name: 'Jan', revenue: 4000, profit: 2400, expenses: 1600 },
  { name: 'Feb', revenue: 3000, profit: 1398, expenses: 1602 },
  { name: 'Mar', revenue: 2000, profit: 9800, expenses: 800 },
  { name: 'Apr', revenue: 2780, profit: 3908, expenses: 1200 },
  { name: 'May', revenue: 1890, profit: 4800, expenses: 1400 },
  { name: 'Jun', revenue: 2390, profit: 3800, expenses: 1600 }
];

<ResponsiveContainer width="100%" height={400}>
  <BarChart data={biaxialData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
    <CartesianGrid strokeDasharray="3 3" />
    <XAxis dataKey="name" />
    <YAxis yAxisId="left" />
    <YAxis yAxisId="right" orientation="right" />
    <Tooltip 
      formatter={(value, name) => [
        `€${Number(value).toLocaleString('nl-NL')}`, 
        name === 'revenue' ? 'Omzet' : name === 'profit' ? 'Winst' : 'Kosten'
      ]}
    />
    <Legend />
    <Bar yAxisId="left" dataKey="revenue" fill="#8884d8" name="Omzet" />
    <Bar yAxisId="left" dataKey="expenses" fill="#ff7c7c" name="Kosten" />
    <Bar yAxisId="right" dataKey="profit" fill="#82ca9d" name="Winst" />
  </BarChart>
</ResponsiveContainer>
```

#### BiaxialBarChart Use Cases
- **Financiële vergelijking**: Omzet vs Winst vs Kosten
- **BNB Analytics**: Boekingen vs Inkomsten per maand
- **Trend analyse**: Verschillende metrics met verschillende schalen
- **Performance dashboard**: KPI's met verschillende eenheden

## 📋 React Grid Layout Dashboard

### Dashboard Setup
```tsx
import GridLayout from 'react-grid-layout';
import { Box, Card, CardBody, CardHeader, Heading } from '@chakra-ui/react';
import { PieChart, LineChart, BarChart, ResponsiveContainer } from 'recharts';
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

// Dashboard layout configuratie
const defaultLayout = [
  {i: 'revenue-pie', x: 0, y: 0, w: 6, h: 4, minW: 4, minH: 3},
  {i: 'profit-bar', x: 6, y: 0, w: 6, h: 4, minW: 4, minH: 3},
  {i: 'trends-line', x: 0, y: 4, w: 12, h: 6, minW: 8, minH: 4},
  {i: 'bnb-biaxial', x: 0, y: 10, w: 12, h: 6, minW: 8, minH: 4}
];

const DashboardGrid: React.FC = () => {
  const [layout, setLayout] = useState(defaultLayout);
  const [revenueData, setRevenueData] = useState([]);
  const [profitData, setProfitData] = useState([]);
  const [trendsData, setTrendsData] = useState([]);
  const [bnbData, setBnbData] = useState([]);

  return (
    <Box p={4} bg="gray.800" minH="100vh">
      <GridLayout
        className="layout"
        layout={layout}
        onLayoutChange={setLayout}
        cols={12}
        rowHeight={60}
        width={1200}
        isDraggable={true}
        isResizable={true}
        margin={[16, 16]}
      >
        {/* Revenue Pie Chart Widget */}
        <Card key="revenue-pie" bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">Omzet Verdeling</Heading>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart data={revenueData}>
                <Pie
                  data={revenueData}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  fill="#8884d8"
                  dataKey="value"
                />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        {/* Profit Bar Chart Widget */}
        <Card key="profit-bar" bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">Winst per Maand</Heading>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={profitData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="profit" fill="#82ca9d" />
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        {/* Trends Line Chart Widget */}
        <Card key="trends-line" bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">Trends Analyse</Heading>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="amount" stroke="#8884d8" />
              </LineChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>

        {/* BNB Biaxial Chart Widget */}
        <Card key="bnb-biaxial" bg="gray.700">
          <CardHeader>
            <Heading size="md" color="white">BNB Performance</Heading>
          </CardHeader>
          <CardBody>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={bnbData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis yAxisId="left" />
                <YAxis yAxisId="right" orientation="right" />
                <Tooltip />
                <Bar yAxisId="left" dataKey="bookings" fill="#8884d8" />
                <Bar yAxisId="right" dataKey="revenue" fill="#82ca9d" />
              </BarChart>
            </ResponsiveContainer>
          </CardBody>
        </Card>
      </GridLayout>
    </Box>
  );
};
```

### Dashboard Features

#### 1. Widget Management
```tsx
// Widget configuratie
const widgetConfig = {
  'revenue-pie': {
    title: 'Omzet Verdeling',
    component: PieChart,
    dataKey: 'revenueData',
    minSize: { w: 4, h: 3 }
  },
  'profit-bar': {
    title: 'Winst per Maand', 
    component: BarChart,
    dataKey: 'profitData',
    minSize: { w: 4, h: 3 }
  }
};

// Dynamic widget rendering
const renderWidget = (widgetId: string) => {
  const config = widgetConfig[widgetId];
  const Component = config.component;
  
  return (
    <Card key={widgetId} bg="gray.700">
      <CardHeader>
        <Heading size="md" color="white">{config.title}</Heading>
      </CardHeader>
      <CardBody>
        <ResponsiveContainer width="100%" height="100%">
          <Component data={data[config.dataKey]}>
            {/* Chart configuration */}
          </Component>
        </ResponsiveContainer>
      </CardBody>
    </Card>
  );
};
```

#### 2. Layout Persistence
```tsx
// Layout opslaan in localStorage
const saveLayout = (layout: Layout[]) => {
  localStorage.setItem('dashboardLayout', JSON.stringify(layout));
};

// Layout laden bij component mount
const loadLayout = (): Layout[] => {
  const saved = localStorage.getItem('dashboardLayout');
  return saved ? JSON.parse(saved) : defaultLayout;
};

// Layout change handler
const handleLayoutChange = (newLayout: Layout[]) => {
  setLayout(newLayout);
  saveLayout(newLayout);
};
```

#### 3. Responsive Breakpoints
```tsx
const responsiveLayouts = {
  lg: defaultLayout,
  md: [
    {i: 'revenue-pie', x: 0, y: 0, w: 6, h: 4},
    {i: 'profit-bar', x: 6, y: 0, w: 6, h: 4},
    {i: 'trends-line', x: 0, y: 4, w: 12, h: 6}
  ],
  sm: [
    {i: 'revenue-pie', x: 0, y: 0, w: 12, h: 4},
    {i: 'profit-bar', x: 0, y: 4, w: 12, h: 4},
    {i: 'trends-line', x: 0, y: 8, w: 12, h: 6}
  ]
};

<ResponsiveGridLayout
  className="layout"
  layouts={responsiveLayouts}
  breakpoints={{lg: 1200, md: 996, sm: 768}}
  cols={{lg: 12, md: 10, sm: 6}}
  rowHeight={60}
/>
```

## 🗄️ Database Integratie

### MySQL Tabellen
- **vw_mutaties**: Financiële transacties view
- **bnbtotal**: BNB reserveringen en inkomsten
- **Dynamische filters**: `SELECT DISTINCT` queries voor filter opties

### Backend API Endpoints
```python
# Filter opties ophalen
@app.route('/api/reports/filter-options')
def get_filter_options():
    return jsonify({
        'mutaties': {
            'Administration': get_distinct_values('vw_mutaties', 'Administration'),
            'ledger': get_distinct_values('vw_mutaties', 'ledger')
        },
        'bnb': {
            'channel': get_distinct_values('bnbtotal', 'channel'),
            'listing': get_distinct_values('bnbtotal', 'listing')
        }
    })

# Chart data ophalen
@app.route('/api/reports/chart-data')
def get_chart_data():
    # Query met filters
    # Return data in Recharts format
    return jsonify({
        'success': True,
        'data': [
            {'name': 'Category A', 'value': 1000},
            {'name': 'Category B', 'value': 2000}
        ]
    })
```

## 🎯 Recharts Voordelen

### vs Google Charts
| Feature | Recharts | Google Charts |
|---------|----------|---------------|
| **React Integration** | ✅ Native | ❌ Wrapper needed |
| **TypeScript Support** | ✅ Built-in | ⚠️ Limited |
| **Bundle Size** | ✅ Smaller | ❌ Larger |
| **Customization** | ✅ Full control | ⚠️ Limited |
| **Offline Support** | ✅ Yes | ❌ No |
| **Performance** | ✅ Better | ⚠️ Good |

### Responsive Design
```tsx
// Automatische aanpassing aan container grootte
<ResponsiveContainer width="100%" height={400} maxWidth={500}>
  <PieChart>
    {/* Chart content */}
  </PieChart>
</ResponsiveContainer>
```

### Custom Styling
```tsx
// Kleuren en styling volledig aanpasbaar
const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042'];

{data.map((entry, index) => (
  <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
))}
```

## 🛠 Best Practices

### 1. Data Formatting
```tsx
// Data transformatie voor Recharts
const chartData = rawData.map(item => ({
  name: item.ledger || 'N/A',
  value: Math.abs(Number(item.total_amount || 0))
}));
```

### 2. Loading States
```tsx
{loading ? (
  <Spinner size="xl" color="orange.400" />
) : (
  <ResponsiveContainer width="100%" height={400}>
    <PieChart data={chartData}>
      {/* Chart content */}
    </PieChart>
  </ResponsiveContainer>
)}
```

### 3. Error Handling
```tsx
{error ? (
  <Alert status="error">
    <AlertIcon />
    {error}
  </Alert>
) : (
  // Chart component
)}
```

