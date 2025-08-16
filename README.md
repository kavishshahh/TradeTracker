# TradeTracker - Trading Journal Dashboard

A comprehensive trading journal application built with Next.js, FastAPI, and Firebase Firestore. Track your trades, analyze performance, and improve your trading strategy with detailed analytics.

## 🚀 Features

### Core Functionality
- **Trade Management**: Add, edit, and track trades with detailed information
- **Performance Analytics**: Real-time metrics including P&L, win rate, expectancy, and profit factor
- **Visual Dashboard**: Interactive charts showing equity curve, performance breakdown, and trading statistics
- **Calendar View**: Month-by-month trading activity with daily P&L visualization
- **Progress Tracking**: Weekly/monthly performance trends and account balance tracking
- **Trading Journal**: Rich text notes for each trade with filtering and search capabilities

### Analytics & Metrics
- Net P&L calculation
- Trade Expectancy: (Win% × AvgWin) – (Loss% × AvgLoss)
- Profit Factor: Gross Profit / Gross Loss
- Win percentage and ratio analysis
- Risk management tracking
- Trading score radar chart

### Charts & Visualizations
- Equity curve over time
- Win/Loss distribution pie chart
- Performance radar chart (Win%, Risk, Discipline, Resilience)
- Weekly/Monthly P&L bar charts
- Account balance trend lines
- Trading activity heatmaps

## 🛠️ Tech Stack

### Frontend
- **Next.js 15** - React framework
- **TailwindCSS 4** - Styling
- **Recharts** - Data visualization
- **Lucide React** - Icons
- **React Hook Form** - Form management
- **TypeScript** - Type safety

### Backend
- **FastAPI** - Python web framework
- **Firebase Admin SDK** - Database operations
- **Pydantic** - Data validation
- **Uvicorn** - ASGI server

### Database
- **Firebase Firestore** - NoSQL database for trade storage

## 📦 Installation

### Prerequisites
- Node.js 18+ 
- Python 3.8+
- Firebase project (optional for development)

### Frontend Setup

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm run dev
```

The frontend will be available at [http://localhost:3000](http://localhost:3000)

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. (Optional) Configure Firebase:
   - Create a Firebase project
   - Generate a service account key
   - Copy `env.example` to `.env` and add your Firebase credentials

5. Start the FastAPI server:
```bash
python main.py
```

The API will be available at [http://localhost:8000](http://localhost:8000)

## 🔥 Firebase Setup (Optional)

For production or to use real Firebase Firestore:

1. Create a Firebase project at [https://console.firebase.google.com](https://console.firebase.google.com)
2. Enable Firestore Database
3. Generate a service account key:
   - Go to Project Settings > Service Accounts
   - Generate a new private key (JSON)
4. Set up environment variables in `backend/.env`:
```
FIREBASE_SERVICE_ACCOUNT_PATH=path/to/your/service-account.json
```

For development, the app includes mock data and will work without Firebase configuration.

## 🎯 Usage

### Adding Trades
1. Navigate to "Add Trade" in the sidebar
2. Fill in trade details:
   - Date, ticker symbol
   - Buy/sell prices and share count
   - Risk percentage
   - Trade notes
3. Select open or closed position status
4. Submit to save the trade

### Viewing Analytics
- **Dashboard**: Overview of key metrics and recent performance
- **Calendar**: Day-by-day trading activity with P&L visualization
- **Progress**: Weekly/monthly trends and account balance tracking
- **Journal**: Detailed trade notes with search and filtering

### Key Metrics Explained
- **Net P&L**: Total profit/loss across all closed trades
- **Trade Expectancy**: Expected value per trade
- **Profit Factor**: Ratio of gross profits to gross losses
- **Win Rate**: Percentage of profitable trades

## 🗂️ Project Structure

```
tradetracker/
├── src/
│   ├── app/                 # Next.js app router pages
│   ├── components/          # React components
│   ├── lib/                 # Utilities and API functions
│   └── types/               # TypeScript type definitions
├── backend/
│   ├── main.py             # FastAPI application
│   ├── requirements.txt    # Python dependencies
│   └── env.example         # Environment variables template
└── public/                 # Static assets
```

## 🔧 API Endpoints

- `POST /add-trade` - Add a new trade
- `GET /trades/{userId}` - Retrieve trades for a user
- `GET /metrics/{userId}` - Get performance metrics
- `GET /` - Health check

## 🎨 Mock Data

The application includes sample trades for demonstration:
- AAPL: $1,500 profit
- TSLA: $750 loss  
- MSFT: $375 profit
- NVDA: Open position

This allows you to see the dashboard and analytics in action immediately.

## 🚀 Deployment

### Frontend (Vercel)
1. Push your code to GitHub
2. Connect your repository to Vercel
3. Deploy with default settings

### Backend (Railway/Heroku)
1. Set environment variables for Firebase
2. Deploy the `backend/` directory
3. Update the frontend `API_BASE_URL` environment variable

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🙏 Acknowledgments

- Inspired by TradeZella's trading journal interface
- Built with modern web technologies
- Designed for traders who want to improve their performance through data analysis
