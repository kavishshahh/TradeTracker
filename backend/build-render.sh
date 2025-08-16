#!/bin/bash
set -e

echo "🚀 Starting Render build..."

# Upgrade pip and install build tools
echo "📦 Upgrading pip and build tools..."
pip install --upgrade pip setuptools wheel

# Install dependencies with prebuilt wheels only
echo "🔧 Installing Python dependencies (prebuilt wheels only)..."
pip install --only-binary=:all: -r requirements.txt

echo "✅ Build completed successfully!"
