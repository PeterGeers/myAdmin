#!/bin/bash

echo "Starting PDF Transaction Processor..."
echo

echo "Starting Backend Server..."
cd backend
python app.py &
BACKEND_PID=$!

echo "Waiting for backend to initialize..."
sleep 3

echo "Starting Frontend Server..."
cd ../frontend
npm start &
FRONTEND_PID=$!

echo
echo "Both servers are running:"
echo "Backend: http://localhost:5000 (PID: $BACKEND_PID)"
echo "Frontend: http://localhost:3000 (PID: $FRONTEND_PID)"
echo
echo "Press Ctrl+C to stop both servers"

# Wait for user interrupt
trap 'echo "Stopping servers..."; kill $BACKEND_PID $FRONTEND_PID; exit' INT
wait