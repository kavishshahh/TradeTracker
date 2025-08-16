from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="TradeTracker API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        if not firebase_admin._apps:
            # Path to your service account key file
            service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', './firebase-service-account.json')
            
            if os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase Admin SDK initialized successfully")
            else:
                print(f"❌ Service account file not found: {service_account_path}")
                print("📝 Using mock data instead")
                return None
        
        return firestore.client()
    except Exception as e:
        print(f"❌ Firebase initialization error: {e}")
        print("📝 Using mock data instead")
        return None

# Initialize Firestore
db = initialize_firebase()

# Authentication dependency
async def get_current_user(authorization: str = Header(None)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    try:
        # Remove 'Bearer ' prefix
        token = authorization.replace('Bearer ', '')
        
        # Verify the Firebase ID token
        decoded_token = auth.verify_id_token(token)
        user_id = decoded_token['uid']
        print(f"🔐 Authenticated user: {user_id}")
        return user_id
    except Exception as e:
        print(f"❌ Authentication error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

# Pydantic models
class Trade(BaseModel):
    id: Optional[str] = None
    user_id: str
    date: date
    ticker: str
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    shares: float  # Allow decimal shares (e.g., 10.5 shares)
    risk: Optional[float] = None  # Risk percentage (0-100)
    risk_dollars: Optional[float] = None  # Risk in dollars
    account_balance: Optional[float] = None  # Account balance at time of trade
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

class ExitTradeRequest(BaseModel):
    ticker: str
    shares_to_exit: int
    sell_price: float
    notes: Optional[str] = ""

class UserProfile(BaseModel):
    user_id: Optional[str] = None
    account_balance: float
    currency: Optional[str] = "USD"
    risk_tolerance: Optional[float] = 2.0  # Default 2% risk
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

# Mock data fallback (same as main_simple.py)
# MOCK_TRADES = [
#     {
#         "id": "1",
#         "user_id": "user123",
#         "date": "2024-01-15",
#         "ticker": "AAPL",
#         "buy_price": 150.00,
#         "sell_price": 165.00,
#         "shares": 100,
#         "risk": 2.0,
#         "notes": "Strong breakout pattern, good volume",
#         "status": "closed",
#         "created_at": "2024-01-15T10:30:00Z",
#         "updated_at": "2024-01-16T15:45:00Z"
#     },
#     {
#         "id": "2",
#         "user_id": "user123",
#         "date": "2024-01-18",
#         "ticker": "TSLA",
#         "buy_price": 240.00,
#         "sell_price": 225.00,
#         "shares": 50,
#         "risk": 1.5,
#         "notes": "Failed support level, quick exit",
#         "status": "closed",
#         "created_at": "2024-01-18T09:15:00Z",
#         "updated_at": "2024-01-18T14:20:00Z"
#     },
#     {
#         "id": "3",
#         "user_id": "user123",
#         "date": "2024-01-22",
#         "ticker": "MSFT",
#         "buy_price": 380.00,
#         "sell_price": 395.00,
#         "shares": 25,
#         "risk": 1.8,
#         "notes": "Earnings play, exceeded expectations",
#         "status": "closed",
#         "created_at": "2024-01-22T08:45:00Z",
#         "updated_at": "2024-01-23T16:30:00Z"
#     },
#     {
#         "id": "4",
#         "user_id": "user123",
#         "date": "2024-01-25",
#         "ticker": "NVDA",
#         "buy_price": 620.00,
#         "sell_price": None,
#         "shares": 10,
#         "risk": 2.5,
#         "notes": "AI sector momentum, holding for trend",
#         "status": "open",
#         "created_at": "2024-01-25T11:00:00Z",
#         "updated_at": "2024-01-25T11:00:00Z"
#     }
# ]

@app.get("/")
async def root():
    firebase_status = "connected" if db else "using_mock_data"
    return {
        "message": "TradeTracker API is running", 
        "status": "ok",
        "firebase": firebase_status
    }

@app.post("/add-trade")
async def add_trade(trade: Trade, current_user: str = Depends(get_current_user)):
    try:
        print(f"🔍 Add trade request: user={current_user}")
        print(f"📊 Trade data received: {trade.model_dump()}")
        
        # Validation based on status
        if trade.status == "open":
            if not trade.buy_price:
                print(f"❌ Validation error: Buy price required for open trade")
                raise HTTPException(status_code=422, detail="Buy price is required for open trades")
        elif trade.status == "closed":
            if not trade.sell_price:
                print(f"❌ Validation error: Sell price required for closed trade")
                raise HTTPException(status_code=422, detail="Sell price is required for closed trades")
        
        # Risk validation - either risk percentage or risk dollars must be provided
        if not trade.risk and not trade.risk_dollars:
            print(f"❌ Validation error: No risk information provided")
            raise HTTPException(status_code=422, detail="Either risk percentage or risk in dollars must be provided")
        
        print(f"✅ Trade validation passed")
        
        # Fetch account balance from user profile for risk calculations
        account_balance = trade.account_balance  # Use provided balance if any
        if not account_balance:
            try:
                if db:
                    profiles_ref = db.collection('user_profiles')
                    profile_doc = profiles_ref.document(current_user).get()
                    if profile_doc.exists:
                        profile_data = profile_doc.to_dict()
                        account_balance = profile_data.get('account_balance', 10000.0)
                    else:
                        account_balance = 10000.0  # Default
                else:
                    account_balance = 10000.0  # Mock default
            except Exception as e:
                print(f"⚠️ Could not fetch account balance: {e}")
                account_balance = 10000.0  # Fallback default
        
        # Calculate missing risk field using account balance
        if account_balance and account_balance > 0:
            if trade.risk and not trade.risk_dollars:
                # Calculate risk_dollars from risk percentage
                trade.risk_dollars = (trade.risk / 100) * account_balance
            elif trade.risk_dollars and not trade.risk:
                # Calculate risk percentage from risk_dollars
                trade.risk = (trade.risk_dollars / account_balance) * 100
            
            # Store the account balance used for this trade
            trade.account_balance = account_balance
        
        # Ensure user_id matches authenticated user
        trade.user_id = current_user
        print(f"🔐 Setting trade user_id to authenticated user: {current_user}")
        
        trade.created_at = datetime.now()
        trade.updated_at = datetime.now()
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            
            # Prepare data for Firestore
            trade_data = trade.model_dump(exclude={'id'})
            # Convert date to string for Firestore
            if isinstance(trade_data['date'], date):
                trade_data['date'] = trade_data['date'].isoformat()
            
            # Add document to Firestore
            doc_ref = trades_ref.add(trade_data)
            trade_id = doc_ref[1].id
            
            return {"message": "Trade added successfully", "trade_id": trade_id}
        else:
            # Fallback to mock data
            trade.id = str(len(MOCK_TRADES) + 1)
            MOCK_TRADES.append(trade.model_dump())
            return {"message": "Trade added successfully (mock)", "trade_id": trade.id}
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error adding trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/exit-trade/{user_id}")
async def exit_trade(user_id: str, exit_request: ExitTradeRequest, current_user: str = Depends(get_current_user)):
    try:
        print(f"🔍 Exit trade request: user={user_id}, ticker={exit_request.ticker}, shares={exit_request.shares_to_exit}")
        
        # Ensure user can only exit their own trades
        if user_id != current_user:
            print(f"❌ Unauthorized access attempt: {current_user} trying to exit {user_id}'s trades")
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            
            # Debug: First get all trades for this user
            all_trades_query = trades_ref.where("user_id", "==", user_id)
            all_docs = all_trades_query.get()
            print(f"📊 Total trades for user {user_id}: {len(all_docs)}")
            
            for doc in all_docs:
                trade_data = doc.to_dict()
                print(f"   Trade: {trade_data.get('ticker')} - Status: {trade_data.get('status')} - Shares: {trade_data.get('shares')}")
            
            # Find the open trade for this ticker and user
            query = trades_ref.where("user_id", "==", user_id).where("ticker", "==", exit_request.ticker).where("status", "==", "open")
            docs = query.get()
            print(f"🎯 Open trades found for {exit_request.ticker}: {len(docs)}")
            
            if not docs:
                # Check if there are any trades for this ticker (regardless of status)
                ticker_query = trades_ref.where("user_id", "==", user_id).where("ticker", "==", exit_request.ticker)
                ticker_docs = ticker_query.get()
                print(f"📈 All trades for ticker {exit_request.ticker}: {len(ticker_docs)}")
                
                for doc in ticker_docs:
                    trade_data = doc.to_dict()
                    print(f"   {exit_request.ticker} Trade: Status={trade_data.get('status')}, Shares={trade_data.get('shares')}")
                
                raise HTTPException(status_code=404, detail=f"No open trade found for {exit_request.ticker}. Found {len(ticker_docs)} total trades for this ticker.")
            
            # Get the first matching open trade
            trade_doc = docs[0]
            trade_data = trade_doc.to_dict()
            current_shares = trade_data.get('shares', 0)
            print(f"✅ Found open trade: {current_shares} shares of {exit_request.ticker}")
            
            # Validate exit shares
            if exit_request.shares_to_exit > current_shares:
                raise HTTPException(status_code=400, detail=f"Cannot exit {exit_request.shares_to_exit} shares. Only {current_shares} shares available.")
            
            # Calculate remaining shares
            remaining_shares = current_shares - exit_request.shares_to_exit
            
            if remaining_shares == 0:
                # Full exit - update the trade as closed
                update_data = {
                    'sell_price': exit_request.sell_price,
                    'status': 'closed',
                    'updated_at': datetime.now(),
                    'shares': exit_request.shares_to_exit  # Set shares to exited amount
                }
                if exit_request.notes:
                    update_data['notes'] = f"{trade_data.get('notes', '')} | Exit: {exit_request.notes}".strip(' |')
                
                trade_doc.reference.update(update_data)
                return {"message": f"Trade fully exited: {exit_request.shares_to_exit} shares of {exit_request.ticker}", "trade_id": trade_doc.id}
            
            else:
                # Partial exit - create a new closed trade for exited portion and update original
                # Create closed trade for the exited portion
                exit_trade_data = {
                    'user_id': user_id,
                    'date': trade_data['date'],
                    'ticker': exit_request.ticker,
                    'buy_price': trade_data['buy_price'],
                    'sell_price': exit_request.sell_price,
                    'shares': exit_request.shares_to_exit,
                    'risk': trade_data['risk'],
                    'notes': f"{trade_data.get('notes', '')} | Partial exit: {exit_request.notes}".strip(' |'),
                    'status': 'closed',
                    'created_at': trade_data['created_at'],
                    'updated_at': datetime.now()
                }
                
                exit_doc_ref = trades_ref.add(exit_trade_data)
                
                # Update original trade with remaining shares
                trade_doc.reference.update({
                    'shares': remaining_shares,
                    'updated_at': datetime.now()
                })
                
                return {
                    "message": f"Partial exit successful: {exit_request.shares_to_exit} shares exited, {remaining_shares} shares remaining",
                    "exit_trade_id": exit_doc_ref[1].id,
                    "remaining_trade_id": trade_doc.id
                }
        
        else:
            # Fallback to mock data
            # Find open trade in mock data
            open_trades = [t for t in MOCK_TRADES if t['user_id'] == user_id and t['ticker'] == exit_request.ticker and t['status'] == 'open']
            
            if not open_trades:
                raise HTTPException(status_code=404, detail=f"No open trade found for {exit_request.ticker}")
            
            trade = open_trades[0]
            current_shares = trade['shares']
            
            if exit_request.shares_to_exit > current_shares:
                raise HTTPException(status_code=400, detail=f"Cannot exit {exit_request.shares_to_exit} shares. Only {current_shares} shares available.")
            
            if exit_request.shares_to_exit == current_shares:
                # Full exit
                trade['sell_price'] = exit_request.sell_price
                trade['status'] = 'closed'
                trade['updated_at'] = datetime.now().isoformat()
                if exit_request.notes:
                    trade['notes'] = f"{trade.get('notes', '')} | Exit: {exit_request.notes}".strip(' |')
            else:
                # Partial exit - create new closed trade and update original
                exit_trade = {
                    "id": str(len(MOCK_TRADES) + 1),
                    "user_id": user_id,
                    "date": trade['date'],
                    "ticker": exit_request.ticker,
                    "buy_price": trade['buy_price'],
                    "sell_price": exit_request.sell_price,
                    "shares": exit_request.shares_to_exit,
                    "risk": trade['risk'],
                    "notes": f"{trade.get('notes', '')} | Partial exit: {exit_request.notes}".strip(' |'),
                    "status": "closed",
                    "created_at": trade['created_at'],
                    "updated_at": datetime.now().isoformat()
                }
                MOCK_TRADES.append(exit_trade)
                
                # Update original trade
                trade['shares'] = current_shares - exit_request.shares_to_exit
                trade['updated_at'] = datetime.now().isoformat()
            
            return {"message": f"Trade exit successful (mock): {exit_request.shares_to_exit} shares of {exit_request.ticker}"}
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error exiting trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/trades/{user_id}")
async def get_trades(user_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, current_user: str = Depends(get_current_user)):
    try:
        print(f"🔍 Get trades request: user={user_id}, from={from_date}, to={to_date}")
        
        # Ensure user can only access their own trades
        if user_id != current_user:
            print(f"❌ Unauthorized access attempt: {current_user} trying to access {user_id}'s trades")
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            # Use the correct filter syntax for firebase-admin
            query = trades_ref.where("user_id", "==", user_id)
            
            # Add date filtering if provided
            if from_date:
                query = query.where("date", ">=", from_date)
            if to_date:
                query = query.where("date", "<=", to_date)
            
            docs = query.get()
            trades = []
            for doc in docs:
                trade_data = doc.to_dict()
                trade_data['id'] = doc.id
                
                # Ensure date is a string
                if trade_data.get('date'):
                    if isinstance(trade_data['date'], datetime):
                        trade_data['date'] = trade_data['date'].date().isoformat()
                    elif hasattr(trade_data['date'], 'strftime'):
                        trade_data['date'] = trade_data['date'].strftime('%Y-%m-%d')
                    # If it's already a string, keep it as is
                
                # Convert datetime objects to strings
                for field in ['created_at', 'updated_at']:
                    if isinstance(trade_data.get(field), datetime):
                        trade_data[field] = trade_data[field].isoformat()
                
                trades.append(trade_data)
            
            print(f"✅ Found {len(trades)} trades for user {user_id}")
            return {"trades": trades}
        else:
            # Fallback to mock data
            trades = [trade for trade in MOCK_TRADES if trade['user_id'] == user_id]
            print(f"📝 Mock data: Found {len(trades)} trades for user {user_id}")
            return {"trades": trades}
            
    except Exception as e:
        print(f"❌ Error fetching trades: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/{user_id}")
async def get_metrics(user_id: str, current_user: str = Depends(get_current_user)):
    try:
        print(f"🔍 Get metrics request: user={user_id}")
        
        # Ensure user can only access their own metrics
        if user_id != current_user:
            print(f"❌ Unauthorized access attempt: {current_user} trying to access {user_id}'s metrics")
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            docs = trades_ref.where("user_id", "==", user_id).get()
            trades = [doc.to_dict() for doc in docs]
        else:
            # Fallback to mock data
            trades = [trade for trade in MOCK_TRADES if trade['user_id'] == user_id]
        
        # Calculate metrics (same logic as before)
        closed_trades = [t for t in trades if t['status'] == 'closed' and t.get('sell_price') and t.get('buy_price')]
        
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
        print(f"❌ Error calculating metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: str = Depends(get_current_user)):
    try:
        print(f"🔍 Get profile request: user={user_id}")
        
        # Ensure user can only access their own profile
        if user_id != current_user:
            print(f"❌ Unauthorized access attempt: {current_user} trying to access {user_id}'s profile")
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            profiles_ref = db.collection('user_profiles')
            doc = profiles_ref.document(user_id).get()
            
            if doc.exists:
                profile_data = doc.to_dict()
                profile_data['user_id'] = user_id
                
                # Convert datetime objects to strings
                for field in ['created_at', 'updated_at']:
                    if isinstance(profile_data.get(field), datetime):
                        profile_data[field] = profile_data[field].isoformat()
                
                return {"profile": profile_data}
            else:
                # Return default profile if none exists
                return {
                    "profile": {
                        "user_id": user_id,
                        "account_balance": 10000.0,
                        "currency": "USD",
                        "risk_tolerance": 2.0
                    }
                }
        else:
            # Mock data fallback
            return {
                "profile": {
                    "user_id": user_id,
                    "account_balance": 10000.0,
                    "currency": "USD", 
                    "risk_tolerance": 2.0
                }
            }
    except Exception as e:
        print(f"❌ Error fetching profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/profile/{user_id}")
async def update_user_profile(user_id: str, profile_data: dict, current_user: str = Depends(get_current_user)):
    try:
        print(f"🔍 Profile update request: user={user_id}")
        print(f"📊 Raw profile data received: {profile_data}")
        
        # Ensure user can only update their own profile
        if user_id != current_user:
            print(f"❌ Unauthorized access attempt: {current_user} trying to update {user_id}'s profile")
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Validate required fields
        if 'account_balance' not in profile_data:
            print(f"❌ Missing account_balance in request")
            raise HTTPException(status_code=422, detail="account_balance is required")
        
        # Convert and validate account_balance (handle string input from frontend)
        try:
            account_balance = float(profile_data['account_balance'])
            if account_balance <= 0:
                print(f"❌ Account balance must be positive: {account_balance}")
                raise HTTPException(status_code=422, detail="account_balance must be a positive number")
        except (ValueError, TypeError):
            print(f"❌ Invalid account_balance format: {profile_data['account_balance']}")
            raise HTTPException(status_code=422, detail="account_balance must be a valid number")
        
        # Convert and validate risk_tolerance (handle string input from frontend)
        try:
            risk_tolerance = float(profile_data.get('risk_tolerance', 2.0))
            if risk_tolerance < 0 or risk_tolerance > 100:
                print(f"❌ Risk tolerance out of range: {risk_tolerance}")
                raise HTTPException(status_code=422, detail="risk_tolerance must be between 0 and 100")
        except (ValueError, TypeError):
            print(f"❌ Invalid risk_tolerance format: {profile_data.get('risk_tolerance')}")
            raise HTTPException(status_code=422, detail="risk_tolerance must be a valid number")
        
        # Create profile object with defaults
        profile_obj = {
            'account_balance': account_balance,
            'currency': profile_data.get('currency', 'USD'),
            'risk_tolerance': risk_tolerance,
            'updated_at': datetime.now()
        }
        
        print(f"✅ Profile validation passed")
        print(f"📋 Processed profile data: {profile_obj}")
        
        if db:
            # Use Firebase Firestore
            profiles_ref = db.collection('user_profiles')
            doc_ref = profiles_ref.document(user_id)
            
            # Check if profile exists
            profile_exists = doc_ref.get().exists
            print(f"📋 Profile exists: {profile_exists}")
            
            if not profile_exists:
                profile_obj['created_at'] = datetime.now()
                print(f"🆕 Creating new profile with created_at: {profile_obj['created_at']}")
            
            # Update profile
            print(f"💾 Saving profile data to Firestore")
            doc_ref.set(profile_obj, merge=True)
            print(f"✅ Profile saved successfully for user: {user_id}")
            
            return {"message": "Profile updated successfully", "user_id": user_id}
        else:
            # Mock data fallback
            print(f"📝 Using mock data for profile update: {user_id}")
            return {"message": "Profile updated successfully (mock)", "user_id": user_id}
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating profile: {e}")
        print(f"🔍 Raw data that caused error: {profile_data}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/profile/{user_id}/account-balance")
async def get_account_balance(user_id: str, current_user: str = Depends(get_current_user)):
    """Quick endpoint to get just the account balance for risk calculations"""
    try:
        # Ensure user can only access their own account balance
        if user_id != current_user:
            print(f"❌ Unauthorized access attempt: {current_user} trying to access {user_id}'s account balance")
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            profiles_ref = db.collection('user_profiles')
            doc = profiles_ref.document(user_id).get()
            
            if doc.exists:
                profile_data = doc.to_dict()
                return {"account_balance": profile_data.get('account_balance', 10000.0)}
            else:
                return {"account_balance": 10000.0}  # Default
        else:
            return {"account_balance": 10000.0}  # Mock default
    except Exception as e:
        print(f"❌ Error fetching account balance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
