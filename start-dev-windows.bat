@echo off
echo Starting TradeTracker Development Servers...
echo.

echo Starting FastAPI Backend on Port 8000...
cd backend
start cmd /k "venv\Scripts\activate && python main_simple.py"
cd ..

echo.
echo Waiting 3 seconds for backend to start...
timeout /t 3 /nobreak >nul

echo.
echo Starting Next.js Frontend on Port 3000...
start cmd /k "npm run dev"

echo.
echo Both servers are starting up:
echo - Frontend: http://localhost:3000
echo - Backend API: http://localhost:8000
echo - API Docs: http://localhost:8000/docs
echo.
echo Press any key to exit this script...
pause >nul
