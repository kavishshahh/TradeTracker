#!/bin/bash

# Docker Build Script for TradeTracker API
# This script handles building with fallback options

set -e

echo "🐳 Building TradeTracker API Docker image..."

# Try the main Dockerfile first
echo "📋 Attempting build with main Dockerfile..."
if docker build -t tradetracker-api .; then
    echo "✅ Build successful with main Dockerfile!"
    echo "🚀 Image 'tradetracker-api' created successfully"
    echo ""
    echo "To run locally:"
    echo "  docker run -p 8000:8000 tradetracker-api"
    echo ""
    echo "To test with docker-compose:"
    echo "  docker-compose up --build"
    exit 0
else
    echo "⚠️  Main Dockerfile build failed, trying alternative..."
    
    # Try alternative Dockerfile
    if docker build -f Dockerfile.alternative -t tradetracker-api .; then
        echo "✅ Build successful with alternative Dockerfile!"
        echo "🚀 Image 'tradetracker-api' created successfully"
        echo ""
        echo "Note: Using alternative Dockerfile (pre-compiled wheels)"
        echo ""
        echo "To run locally:"
        echo "  docker run -p 8000:8000 tradetracker-api"
        echo ""
        echo "To test with docker-compose:"
        echo "  docker-compose up --build"
        exit 0
    else
        echo "❌ Both Dockerfile builds failed!"
        echo ""
        echo "🔍 Troubleshooting steps:"
        echo "1. Check if Docker is running"
        echo "2. Ensure you have sufficient disk space"
        echo "3. Try clearing Docker cache: docker system prune -a"
        echo "4. Check the error messages above"
        echo ""
        echo "💡 Alternative: Use the deployment scripts directly"
        echo "  ./deploy-gcp.sh  # or deploy-gcp.bat on Windows"
        exit 1
    fi
fi
