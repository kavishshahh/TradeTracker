@echo off
echo 🚀 Starting Render build...

REM Upgrade pip and install build tools
echo 📦 Upgrading pip and build tools...
pip install --upgrade pip setuptools wheel

REM Install dependencies with prebuilt wheels only
echo 🔧 Installing Python dependencies (prebuilt wheels only)...
pip install --only-binary=:all: -r requirements.txt

echo ✅ Build completed successfully!
pause
