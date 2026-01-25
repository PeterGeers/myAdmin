@echo off
REM Create testfinance database as a copy of finance database
REM Simple batch file for Windows users

echo ========================================
echo Create testfinance Database
echo ========================================
echo.

REM Check if mysql is available
where mysql >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: mysql command not found in PATH
    echo Please install MySQL client or add it to your PATH
    pause
    exit /b 1
)

REM Get database credentials
set DB_HOST=localhost
set DB_USER=root
set /p DB_PASSWORD="Enter MySQL password for root: "

echo.
echo Step 1: Creating testfinance database...
echo CREATE DATABASE IF NOT EXISTS testfinance; | mysql -h %DB_HOST% -u %DB_USER% -p%DB_PASSWORD% 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create testfinance database
    pause
    exit /b 1
)
echo SUCCESS: testfinance database created

echo.
echo Step 2: Exporting finance database...
mysqldump -h %DB_HOST% -u %DB_USER% -p%DB_PASSWORD% --databases finance --add-drop-table --routines --triggers > finance_temp_dump.sql 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to export finance database
    del finance_temp_dump.sql 2>nul
    pause
    exit /b 1
)
echo SUCCESS: finance database exported

echo.
echo Step 3: Modifying dump file for testfinance...
powershell -Command "(Get-Content finance_temp_dump.sql -Raw) -replace 'CREATE DATABASE.*finance', 'CREATE DATABASE IF NOT EXISTS testfinance' -replace 'USE ``finance``', 'USE ``testfinance``' | Set-Content finance_temp_dump_modified.sql"
echo SUCCESS: dump file modified

echo.
echo Step 4: Importing into testfinance database...
mysql -h %DB_HOST% -u %DB_USER% -p%DB_PASSWORD% < finance_temp_dump_modified.sql 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to import into testfinance database
    del finance_temp_dump.sql 2>nul
    del finance_temp_dump_modified.sql 2>nul
    pause
    exit /b 1
)
echo SUCCESS: data imported into testfinance

echo.
echo Step 5: Cleaning up temporary files...
del finance_temp_dump.sql 2>nul
del finance_temp_dump_modified.sql 2>nul
echo SUCCESS: cleanup complete

echo.
echo Step 6: Verifying the copy...
echo SELECT 'finance' as db, COUNT(*) as tables FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'finance' AND TABLE_TYPE = 'BASE TABLE' UNION ALL SELECT 'testfinance' as db, COUNT(*) as tables FROM information_schema.TABLES WHERE TABLE_SCHEMA = 'testfinance' AND TABLE_TYPE = 'BASE TABLE'; | mysql -h %DB_HOST% -u %DB_USER% -p%DB_PASSWORD% -t

echo.
echo ========================================
echo SUCCESS: testfinance database created!
echo ========================================
echo.
echo You can now run integration tests with:
echo   python -m pytest tests/integration/test_multitenant_phase5.py -v
echo.
pause
