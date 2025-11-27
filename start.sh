#!/bin/bash
# myAdmin Startup Script for Linux
# Usage: ./start.sh [dev|prod|containers]

MODE=${1:-dev}

case $MODE in
    dev)
        echo "Starting myAdmin Development Mode..."
        
        # Sync .env files
        if [ -f backend/.env ]; then
            cp backend/.env .env
            cp backend/.env frontend/.env
            echo "✅ Synced .env files"
        else
            echo "❌ backend/.env not found!"
            exit 1
        fi
        
        # Start containers
        docker-compose up -d
        sleep 2
        
        # Start frontend dev server
        cd frontend && npm start &
        
        echo "✅ Development ready!"
        echo "Backend: http://localhost:5000"
        echo "Frontend: http://localhost:3000"
        ;;
        
    prod)
        echo "Building for Production..."
        
        # Sync .env
        cp backend/.env .env
        cp backend/.env frontend/.env
        
        # Start containers
        docker-compose up -d
        
        # Build frontend
        cd frontend
        npm run build
        cd ..
        
        # Restart backend
        docker-compose restart backend
        
        echo "✅ Production ready at http://localhost:5000"
        ;;
        
    containers)
        echo "Managing containers..."
        
        # Sync .env and fix DB_HOST for Docker
        cp backend/.env .env
        sed -i 's/DB_HOST=localhost/DB_HOST=mysql/g' .env
        
        docker-compose up -d
        
        echo "✅ Containers running!"
        ;;
        
    *)
        echo "Usage: ./start.sh [dev|prod|containers]"
        ;;
esac
