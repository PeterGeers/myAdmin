# MyAdmin Backend

Clean, organized backend structure for the myAdmin application.

## Folder Structure

```
backend/
├── src/                          # Main application code
│   ├── app.py                    # Flask application
│   ├── aws_notifications.py      # AWS SNS notifications
│   └── ...                       # Other modules
│
├── tests/                        # All test files (69 tests)
│   ├── unit/                     # Unit tests
│   ├── api/                      # API endpoint tests
│   ├── database/                 # Database & query tests
│   ├── patterns/                 # Pattern analysis tests
│   ├── integration/              # Integration tests
│   └── conftest.py               # Pytest configuration
│
├── scripts/                      # Utility scripts (33 scripts)
│   ├── analysis/                 # Analysis & debugging scripts
│   ├── database/                 # Database migrations & fixes
│   └── data/                     # Data analysis & validation
│
├── docs/                         # Documentation
│   ├── guides/                   # Setup & user guides
│   └── summaries/                # Investigation summaries
│
├── powershell/                   # PowerShell scripts
│   ├── start_backend.ps1         # Start the backend server
│   ├── run_tests.ps1             # Run test suite
│   └── ...
│
├── sql/                          # SQL scripts
│
├── data/                         # Data files
│   ├── credentials.json          # Google API credentials
│   ├── token.json                # OAuth tokens
│   └── *.json                    # Debug/analysis data
│
├── cache/                        # Application cache
├── logs/                         # Application logs
├── uploads/                      # Uploaded files
├── storage/                      # File storage
├── static/                       # Static assets
├── templates/                    # HTML templates
│
├── .env                          # Environment variables
├── requirements.txt              # Python dependencies
├── pytest.ini                    # Pytest configuration
└── Dockerfile                    # Docker configuration
```

## Quick Start

### 1. Install Dependencies

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```env
DB_HOST=localhost
DB_USER=peter
DB_PASSWORD=your_password
DB_NAME=finance
SNS_TOPIC_ARN=your_sns_topic_arn
AWS_REGION=eu-west-1
OPENROUTER_API_KEY=sk-or-v1-your-api-key-here
```

**OpenRouter API Setup:**

The OpenRouter API is used for AI-powered features like template validation assistance. To set it up:

1. Create an account at [OpenRouter.ai](https://openrouter.ai/)
2. Navigate to the API Keys section in your dashboard
3. Generate a new API key
4. Copy the key (starts with `sk-or-v1-`)
5. Add it to your `.env` file as `OPENROUTER_API_KEY`

**Note**: The OpenRouter API is optional for basic functionality but required for AI template assistance features.

### 3. Start Backend

```powershell
.\powershell\start_backend.ps1
```

Or manually:

```powershell
.\.venv\Scripts\Activate.ps1
python src/app.py
```

### 4. Run Tests

```powershell
.\powershell\run_tests.ps1
```

Or specific test categories:

```powershell
pytest tests/api/           # API tests only
pytest tests/database/      # Database tests only
pytest tests/patterns/      # Pattern tests only
pytest tests/integration/   # Integration tests only
```

## Development

### Running Scripts

**Database scripts:**

```powershell
python scripts/database/fix_database_views.py
```

**Data analysis:**

```powershell
python scripts/data/analyze_pattern_storage_needs.py
```

### Testing

**Run all tests:**

```powershell
pytest
```

**Run specific test:**

```powershell
pytest tests/api/test_sns_notification.py
```

**Run with coverage:**

```powershell
pytest --cov=src tests/
```

## Documentation

- **Complete Documentation Index**: `docs/README.md`
- **Setup Guides**: `docs/guides/`
- **Investigation Summaries**: `docs/summaries/`
- **Security Analysis**: `docs/code_review_summary.md`
- **Performance Optimization**: `docs/performance_optimization_recommendations.sql`
- **API Documentation**: Available at `/api/docs` when server is running

### Security & Code Quality

- **Security Analysis Tools**: `scripts/security_analysis/`
- **Latest Security Review**: `docs/code_review_summary.md`
- **SQL Security Report**: `docs/sql_security_report.txt`

### Performance

- **Database Optimization Guide**: `docs/performance_optimization_recommendations.sql`
- **Performance Analysis Tools**: `scripts/security_analysis/tenant_performance_analysis.py`

## Key Features

- **Banking Processor**: Upload and process bank statements
- **STR Processor**: Generate STR reports
- **Invoice Management**: Track and manage invoices
- **Pattern Analysis**: Automatic transaction categorization
- **AWS Notifications**: Email alerts via AWS SNS
- **Google Drive Integration**: Backup invoices to Google Drive

## Tech Stack

- **Framework**: Flask 2.3.3
- **Database**: MySQL/MariaDB
- **Cloud**: AWS SNS
- **Storage**: Google Drive API
- **Testing**: pytest
- **Server**: Waitress (production)

## Environment Variables

| Variable                     | Description                           | Example              | Required |
| ---------------------------- | ------------------------------------- | -------------------- | -------- |
| `DB_HOST`                    | Database host                         | `localhost`          | Yes      |
| `DB_USER`                    | Database user                         | `peter`              | Yes      |
| `DB_PASSWORD`                | Database password                     | `your_password`      | Yes      |
| `DB_NAME`                    | Database name                         | `finance`            | Yes      |
| `SNS_TOPIC_ARN`              | AWS SNS topic ARN                     | `arn:aws:sns:...`    | Yes      |
| `AWS_REGION`                 | AWS region                            | `eu-west-1`          | Yes      |
| `OPENROUTER_API_KEY`         | OpenRouter API key for AI features    | `sk-or-v1-...`       | Optional |
| `CREDENTIALS_ENCRYPTION_KEY` | Encryption key for tenant credentials | `64-char-hex-string` | Yes      |

### OpenRouter API Key

The `OPENROUTER_API_KEY` enables AI-powered features in the application:

- **Template Validation Assistance**: AI helps fix template errors and suggests improvements
- **Smart Error Analysis**: Provides context-aware suggestions for template issues
- **Auto-Fix Capabilities**: Can automatically fix common template problems

**How to obtain:**

1. Visit [OpenRouter.ai](https://openrouter.ai/)
2. Sign up for an account
3. Generate an API key from your dashboard
4. Add the key to your `.env` file

**Cost**: OpenRouter charges per API call based on the model used. Monitor usage in the `ai_usage_log` table.

## Troubleshooting

### Database Connection Issues

Check your `.env` file and ensure MySQL is running:

```powershell
mysql -u peter -p
```

### Import Errors

Make sure you're in the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

### AWS Notifications Not Working

Test the notification service:

```powershell
python tests/api/test_sns_notification.py
```

Check `docs/guides/AWS_SNS_SETUP_COMPLETE.md` for setup instructions.

## Contributing

1. Create a feature branch
2. Make your changes
3. Run tests: `pytest`
4. Submit a pull request

## License

Private project - All rights reserved
