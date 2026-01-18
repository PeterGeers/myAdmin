# myFilter.md - Filter Implementation Guide

\*\*\* The filters should be cascading - when you select an Administration, the Ledger dropdown should only show ledgers that exist for that specific Administration. Let me update the backend to support filtered options and the frontend to implement cascading filters.

## Multi-Select Years Filter

Custom multi-select dropdown using Menu with checkboxes that looks like a standard dropdown:

- Orange background with white text for visibility
- Dropdown behavior similar to other filters
- Multiple year selection with checkboxes
- Displays selected years in button text

### Required Imports

```typescript
import {
  Menu,
  MenuButton,
  MenuList,
  MenuItem,
  Checkbox,
} from "@chakra-ui/react";
```

### State Management

```typescript
const [selectedFilters, setSelectedFilters] = useState({
  years: ["2025"], // Array for multiple years
  // other filters...
});
```

## Overview

Standaard implementatie voor dynamische filters gebaseerd op database velden uit `vw_mutaties` en `vw_bnb_total` tabellen.

## Backend API Endpoints

### 1. Filter Options Endpoint

```python
# /api/reports/filter-options
@app.route('/api/reports/filter-options', methods=['GET'])
def get_filter_options():
    try:
        # vw_mutaties filters
        mutaties_filters = {
            'Administration': get_distinct_values('vw_mutaties', 'Administration'),
            'AccountName': get_distinct_values('vw_mutaties', 'AccountName'),
            'ledger': get_distinct_values('vw_mutaties', 'ledger'),
            'Parent': get_distinct_values('vw_mutaties', 'Parent'),
            'VW': get_distinct_values('vw_mutaties', 'VW'),
            'jaar': get_distinct_values('vw_mutaties', 'jaar'),
            'ReferenceNumber': get_distinct_values('vw_mutaties', 'ReferenceNumber')
        }

        # vw_bnb_total filters
        bnb_filters = {
            'channel': get_distinct_values('vw_bnb_total', 'channel'),
            'listing': get_distinct_values('vw_bnb_total', 'listing'),
            'status': get_distinct_values('vw_bnb_total', 'status'),
            'year': get_distinct_values('vw_bnb_total', 'year')
        }

        return jsonify({
            'success': True,
            'mutaties': mutaties_filters,
            'bnb': bnb_filters
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

def get_distinct_values(table, field):
    query = f"SELECT DISTINCT {field} FROM {table} WHERE {field} IS NOT NULL ORDER BY {field}"
    cursor.execute(query)
    return [row[0] for row in cursor.fetchall()]
```

## Frontend React Implementation

### 1. State Management

```typescript
// Filter state voor vw_mutaties
const [mutatiesFilterOptions, setMutatiesFilterOptions] = useState({
  Administration: [],
  AccountName: [],
  ledger: [],
  Parent: [],
  VW: [],
  jaar: [],
  ReferenceNumber: [],
});

// Filter state voor vw_bnb_total
const [bnbFilterOptions, setBnbFilterOptions] = useState({
  channel: [],
  listing: [],
  status: [],
  year: [],
});

// Geselecteerde filter waarden
const [selectedFilters, setSelectedFilters] = useState({
  // vw_mutaties filters
  administration: "all",
  accountName: "all",
  ledger: "all",
  parent: "all",
  vw: "all",
  jaar: "all",
  referenceNumber: "all",

  // bnb filters
  channel: "all",
  listing: "all",
  status: "all",
  year: "all",

  // Datum filters
  dateFrom: new Date(new Date().getFullYear(), 0, 1)
    .toISOString()
    .split("T")[0],
  dateTo: new Date().toISOString().split("T")[0],
});
```

### 2. Filter Options Laden

```typescript
const fetchFilterOptions = async () => {
  try {
    const response = await fetch(
      "http://localhost:5000/api/reports/filter-options",
    );
    const data = await response.json();

    if (data.success) {
      setMutatiesFilterOptions(data.mutaties);
      setBnbFilterOptions(data.bnb);
    }
  } catch (err) {
    console.error("Error fetching filter options:", err);
  }
};

useEffect(() => {
  fetchFilterOptions();
}, []);
```

### 3. Filter Component Template

```tsx
<Card bg="gray.700">
  <CardHeader>
    <Heading size="md" color="white">
      Filters
    </Heading>
  </CardHeader>
  <CardBody>
    <Grid templateColumns="repeat(auto-fit, minmax(200px, 1fr))" gap={4}>
      {/* Datum Filters */}
      <GridItem>
        <Text color="white" mb={2}>
          Van Datum
        </Text>
        <Input
          type="date"
          value={selectedFilters.dateFrom}
          onChange={(e) =>
            setSelectedFilters((prev) => ({
              ...prev,
              dateFrom: e.target.value,
            }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        />
      </GridItem>

      <GridItem>
        <Text color="white" mb={2}>
          Tot Datum
        </Text>
        <Input
          type="date"
          value={selectedFilters.dateTo}
          onChange={(e) =>
            setSelectedFilters((prev) => ({ ...prev, dateTo: e.target.value }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        />
      </GridItem>

      {/* Dynamische vw_mutaties Filters */}
      <GridItem>
        <Text color="white" mb={2}>
          Administratie
        </Text>
        <Select
          value={selectedFilters.administration}
          onChange={(e) =>
            setSelectedFilters((prev) => ({
              ...prev,
              administration: e.target.value,
            }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        >
          <option value="all">Alle</option>
          {mutatiesFilterOptions.Administration.map((option, index) => (
            <option key={index} value={option}>
              {option}
            </option>
          ))}
        </Select>
      </GridItem>

      <GridItem>
        <Text color="white" mb={2}>
          Grootboek
        </Text>
        <Select
          value={selectedFilters.ledger}
          onChange={(e) =>
            setSelectedFilters((prev) => ({ ...prev, ledger: e.target.value }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        >
          <option value="all">Alle</option>
          {mutatiesFilterOptions.ledger.map((option, index) => (
            <option key={index} value={option}>
              {option}
            </option>
          ))}
        </Select>
      </GridItem>

      <GridItem>
        <Text color="white" mb={2}>
          VW Account
        </Text>
        <Select
          value={selectedFilters.vw}
          onChange={(e) =>
            setSelectedFilters((prev) => ({ ...prev, vw: e.target.value }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        >
          <option value="all">Alle</option>
          {mutatiesFilterOptions.VW.map((option, index) => (
            <option key={index} value={option}>
              {option}
            </option>
          ))}
        </Select>
      </GridItem>

      {/* Multi-Select Years Filter */}
      <GridItem>
        <Text color="white" mb={2}>
          Select Years
        </Text>
        <Menu closeOnSelect={false}>
          <MenuButton
            as={Button}
            bg="orange.500"
            color="white"
            size="sm"
            width="100%"
            textAlign="left"
            rightIcon={<span>▼</span>}
            _hover={{ bg: "orange.600" }}
            _active={{ bg: "orange.600" }}
          >
            {selectedFilters.years.length > 0
              ? selectedFilters.years.join(", ")
              : "Select years..."}
          </MenuButton>
          <MenuList bg="gray.600" border="1px solid" borderColor="gray.500">
            {availableYears.map((year) => (
              <MenuItem
                key={year}
                bg="gray.600"
                _hover={{ bg: "gray.500" }}
                closeOnSelect={false}
              >
                <Checkbox
                  isChecked={selectedFilters.years.includes(year)}
                  onChange={(e) => {
                    const isChecked = e.target.checked;
                    setSelectedFilters((prev) => ({
                      ...prev,
                      years: isChecked
                        ? [...prev.years, year]
                        : prev.years.filter((y) => y !== year),
                    }));
                  }}
                  colorScheme="orange"
                >
                  <Text color="white" ml={2}>
                    {year}
                  </Text>
                </Checkbox>
              </MenuItem>
            ))}
          </MenuList>
        </Menu>
      </GridItem>

      {/* Dynamische vw_bnb_total Filters */}
      <GridItem>
        <Text color="white" mb={2}>
          Kanaal
        </Text>
        <Select
          value={selectedFilters.channel}
          onChange={(e) =>
            setSelectedFilters((prev) => ({ ...prev, channel: e.target.value }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        >
          <option value="all">Alle</option>
          {bnbFilterOptions.channel.map((option, index) => (
            <option key={index} value={option}>
              {option}
            </option>
          ))}
        </Select>
      </GridItem>

      <GridItem>
        <Text color="white" mb={2}>
          Accommodatie
        </Text>
        <Select
          value={selectedFilters.listing}
          onChange={(e) =>
            setSelectedFilters((prev) => ({ ...prev, listing: e.target.value }))
          }
          bg="gray.600"
          color="white"
          size="sm"
        >
          <option value="all">Alle</option>
          {bnbFilterOptions.listing.map((option, index) => (
            <option key={index} value={option}>
              {option}
            </option>
          ))}
        </Select>
      </GridItem>
    </Grid>

    <HStack mt={4}>
      <Button colorScheme="orange" onClick={fetchData} isLoading={loading}>
        Data Bijwerken
      </Button>
      <Button variant="outline" onClick={resetFilters}>
        Reset Filters
      </Button>
    </HStack>
  </CardBody>
</Card>
```

### 4. Data Fetch met Filters

```typescript
const fetchData = async () => {
  setLoading(true);
  try {
    const params = new URLSearchParams();

    // Voeg alleen non-'all' filters toe
    Object.entries(selectedFilters).forEach(([key, value]) => {
      if (value !== "all" && value !== "") {
        params.append(key, value);
      }
    });

    const response = await fetch(
      `http://localhost:5000/api/reports/data?${params}`,
    );
    const data = await response.json();

    if (data.success) {
      setTableData(data.data);
    }
  } catch (err) {
    console.error("Error fetching data:", err);
  } finally {
    setLoading(false);
  }
};
```

### 5. Reset Functie

```typescript
const resetFilters = () => {
  setSelectedFilters({
    administration: "all",
    accountName: "all",
    ledger: "all",
    parent: "all",
    vw: "all",
    jaar: "all",
    referenceNumber: "all",
    channel: "all",
    listing: "all",
    status: "all",
    year: "all",
    dateFrom: new Date(new Date().getFullYear(), 0, 1)
      .toISOString()
      .split("T")[0],
    dateTo: new Date().toISOString().split("T")[0],
  });
};
```

## Meest Gebruikte Filter Combinaties

### vw_mutaties

- **Administration** - Voor administratie scheiding (GoodwinSolutions, PeterPrive)
- **VW** - Voor V&W account filtering (Y/N)
- **ledger** - Voor grootboek filtering
- **jaar** - Voor jaar filtering
- **Parent** - Voor hoofdcategorie filtering

### vw_bnb_total

- **channel** - Voor platform filtering (Airbnb, Booking.com)
- **listing** - Voor accommodatie filtering
- **year** - Voor jaar filtering
- **status** - Voor reservering status

## Backend Query Building

```python
def build_where_clause(filters):
    conditions = []
    params = []

    for field, value in filters.items():
        if value and value != 'all':
            if field in ['dateFrom', 'dateTo']:
                continue  # Handle separately
            conditions.append(f"{field} = %s")
            params.append(value)

    # Date range handling
    if filters.get('dateFrom'):
        conditions.append("TransactionDate >= %s")
        params.append(filters['dateFrom'])

    if filters.get('dateTo'):
        conditions.append("TransactionDate <= %s")
        params.append(filters['dateTo'])

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, params
```

### 6. Display Format Filter

```tsx
<GridItem>
  <Text color="white" mb={2}>
    Display Format
  </Text>
  <Select
    value={selectedFilters.displayFormat}
    onChange={(e) =>
      setSelectedFilters((prev) => ({ ...prev, displayFormat: e.target.value }))
    }
    bg="gray.600"
    color="white"
    size="sm"
  >
    <option value="2dec">€1,234.56 (2 decimals)</option>
    <option value="0dec">€1,235 (whole numbers)</option>
    <option value="k">€1.2K (thousands)</option>
    <option value="m">€1.2M (millions)</option>
  </Select>
</GridItem>
```

### Display Format Implementation

```tsx
// Format amount based on display format
const formatAmount = (amount: number, format: string): string => {
  const num = Number(amount) || 0;

  switch (format) {
    case "2dec":
      return `€${num.toLocaleString("nl-NL", { minimumFractionDigits: 2 })}`;
    case "0dec":
      return `€${Math.round(num).toLocaleString("nl-NL")}`;
    case "k":
      return `€${(num / 1000).toFixed(1)}K`;
    case "m":
      return `€${(num / 1000000).toFixed(1)}M`;
    default:
      return `€${num.toLocaleString("nl-NL", { minimumFractionDigits: 2 })}`;
  }
};

// Usage in table cells
<Td>{formatAmount(row.amount, selectedFilters.displayFormat)}</Td>;
```

## Gebruik

1. Kopieer de backend endpoint naar `reporting_routes.py`
2. Implementeer de frontend state en components
3. Pas de filter velden aan per pagina behoefte
4. Test de dynamische filter loading bij pagina load
5. Voeg displayFormat toe aan selectedFilters state
6. Gebruik formatAmount functie voor alle bedrag weergaves
