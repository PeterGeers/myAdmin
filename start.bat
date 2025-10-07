@echo off
echo Starting PDF Transaction Processor...
echo.

echo Installing Backend Dependencies...
cd backend
pip install -r requirements.txt
echo.

echo Starting Backend Server...
start "Backend" cmd /k "python app.py"
cd ..

echo Waiting for backend to initialize...
timeout /t 3 /nobreak > nul

echo Starting Frontend Server...
start "Frontend" cmd /k "cd frontend && npm start"

echo.
echo Both servers are starting...
echo Backend: http://localhost:5000
echo Frontend: http://localhost:3000
echo.
echo Press any key to exit this window...
pause > nul