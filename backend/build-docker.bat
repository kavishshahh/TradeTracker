@echo off
REM Docker Build Script for TradeTracker API (Windows)
REM This script handles building with fallback options

echo 🐳 Building TradeTracker API Docker image...

REM Try the main Dockerfile first
echo 📋 Attempting build with main Dockerfile...
docker build -t tradetracker-api .
if %errorlevel% equ 0 (
    echo ✅ Build successful with main Dockerfile!
    echo 🚀 Image 'tradetracker-api' created successfully
    echo.
    echo To run locally:
    echo   docker run -p 8000:8000 tradetracker-api
    echo.
    echo To test with docker-compose:
    echo   docker-compose up --build
    pause
    exit /b 0
) else (
    echo ⚠️  Main Dockerfile build failed, trying alternative...
    
    REM Try alternative Dockerfile
    docker build -f Dockerfile.alternative -t tradetracker-api .
    if %errorlevel% equ 0 (
        echo ✅ Build successful with alternative Dockerfile!
        echo 🚀 Image 'tradetracker-api' created successfully
        echo.
        echo Note: Using alternative Dockerfile (pre-compiled wheels)
        echo.
        echo To run locally:
        echo   docker run -p 8000:8000 tradetracker-api
        echo.
        echo To test with docker-compose:
        echo   docker-compose up --build
        pause
        exit /b 0
    ) else (
        echo ❌ Both Dockerfile builds failed!
        echo.
        echo 🔍 Troubleshooting steps:
        echo 1. Check if Docker is running
        echo 2. Ensure you have sufficient disk space
        echo 3. Try clearing Docker cache: docker system prune -a
        echo 4. Check the error messages above
        echo.
        echo 💡 Alternative: Use the deployment scripts directly
        echo   deploy-gcp.bat
        pause
        exit /b 1
    )
)
