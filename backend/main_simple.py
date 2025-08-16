from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date

app = FastAPI(title="TradeTracker API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class Trade(BaseModel):
    id: Optional[str] = None
    user_id: str
    date: date
    ticker: str
    buy_price: float
    sell_price: Optional[float] = None
    shares: int
    risk: float
    notes: Optional[str] = ""
    status: str  # "open" or "closed"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class TradeMetrics(BaseModel):
    net_pnl: float
    trade_expectancy: float
    profit_factor: float
    win_percentage: float
    avg_win: float
    avg_loss: float
    total_trades: int
    winning_trades: int
    losing_trades: int

# Mock data store (in-memory)
MOCK_TRADES = [
    {
        "id": "1",
        "user_id": "user123",
        "date": "2024-01-15",
        "ticker": "AAPL",
        "buy_price": 150.00,
        "sell_price": 165.00,
        "shares": 100,
        "risk": 2.0,
        "notes": "Strong breakout pattern, good volume",
        "status": "closed",
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-16T15:45:00Z"
    },
    {
        "id": "2",
        "user_id": "user123",
        "date": "2024-01-18",
        "ticker": "TSLA",
        "buy_price": 240.00,
        "sell_price": 225.00,
        "shares": 50,
        "risk": 1.5,
        "notes": "Failed support level, quick exit",
        "status": "closed",
        "created_at": "2024-01-18T09:15:00Z",
        "updated_at": "2024-01-18T14:20:00Z"
    },
    {
        "id": "3",
        "user_id": "user123",
        "date": "2024-01-22",
        "ticker": "MSFT",
        "buy_price": 380.00,
        "sell_price": 395.00,
        "shares": 25,
        "risk": 1.8,
        "notes": "Earnings play, exceeded expectations",
        "status": "closed",
        "created_at": "2024-01-22T08:45:00Z",
        "updated_at": "2024-01-23T16:30:00Z"
    },
    {
        "id": "4",
        "user_id": "user123",
        "date": "2024-01-25",
        "ticker": "NVDA",
        "buy_price": 620.00,
        "sell_price": None,
        "shares": 10,
        "risk": 2.5,
        "notes": "AI sector momentum, holding for trend",
        "status": "open",
        "created_at": "2024-01-25T11:00:00Z",
        "updated_at": "2024-01-25T11:00:00Z"
    }
]

@app.get("/")
async def root():
    return {"message": "TradeTracker API is running", "status": "ok"}

@app.post("/add-trade")
async def add_trade(trade: Trade):
    try:
        trade.created_at = datetime.now()
        trade.updated_at = datetime.now()
        trade.id = str(len(MOCK_TRADES) + 1)
        
        # Add to in-memory store
        MOCK_TRADES.append(trade.dict())
        
        return {"message": "Trade added successfully", "trade_id": trade.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trades/{user_id}")
async def get_trades(user_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None):
    try:
        trades = [trade for trade in MOCK_TRADES if trade['user_id'] == user_id]
        return {"trades": trades}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/{user_id}")
async def get_metrics(user_id: str):
    try:
        trades = [trade for trade in MOCK_TRADES if trade['user_id'] == user_id]
        
        # Calculate metrics
        closed_trades = [t for t in trades if t['status'] == 'closed' and t['sell_price']]
        
        if not closed_trades:
            return TradeMetrics(
                net_pnl=0, trade_expectancy=0, profit_factor=0, win_percentage=0,
                avg_win=0, avg_loss=0, total_trades=0, winning_trades=0, losing_trades=0
            )
        
        # Calculate PnL for each trade
        pnl_values = []
        for trade in closed_trades:
            pnl = (trade['sell_price'] - trade['buy_price']) * trade['shares']
            pnl_values.append(pnl)
        
        net_pnl = sum(pnl_values)
        winning_trades = [pnl for pnl in pnl_values if pnl > 0]
        losing_trades = [pnl for pnl in pnl_values if pnl < 0]
        
        total_trades = len(closed_trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        win_percentage = (win_count / total_trades * 100) if total_trades > 0 else 0
        avg_win = sum(winning_trades) / win_count if win_count > 0 else 0
        avg_loss = abs(sum(losing_trades) / loss_count) if loss_count > 0 else 0
        
        # Trade Expectancy = (Win% × AvgWin) – (Loss% × AvgLoss)
        win_pct = win_percentage / 100
        loss_pct = (loss_count / total_trades) if total_trades > 0 else 0
        trade_expectancy = (win_pct * avg_win) - (loss_pct * avg_loss)
        
        # Profit Factor = Gross Profit / Gross Loss
        gross_profit = sum(winning_trades) if winning_trades else 0
        gross_loss = abs(sum(losing_trades)) if losing_trades else 1  # Avoid division by zero
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        return TradeMetrics(
            net_pnl=net_pnl,
            trade_expectancy=trade_expectancy,
            profit_factor=profit_factor,
            win_percentage=win_percentage,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=total_trades,
            winning_trades=win_count,
            losing_trades=loss_count
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
