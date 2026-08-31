from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
from typing import List, Optional, Union
from datetime import datetime, date
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
import json
from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Now import email service after env vars are loaded
from email_service import email_service

app = FastAPI(title="TradeTracker API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://tradebud.vercel.app", "https://app.tradebud.xyz"],  # Next.js dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Firebase Admin SDK
def initialize_firebase():
    try:
        if not firebase_admin._apps:
            # Try to get service account from environment variable first (stringified JSON)
            service_account_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
            
            if service_account_json:
                try:
                    # Parse the stringified JSON from environment variable
                    service_account_info = json.loads(service_account_json)
                    cred = credentials.Certificate(service_account_info)
                    firebase_admin.initialize_app(cred)
                    print("✅ Firebase Admin SDK initialized successfully from environment variable")
                except json.JSONDecodeError:
                    print("❌ Invalid FIREBASE_SERVICE_ACCOUNT_JSON")
                    print("📝 Falling back to file path approach")
                    return _initialize_from_file()
                except Exception:
                    print("❌ Error initializing Firebase from environment variable")
                    print("📝 Falling back to file path approach")
                    return _initialize_from_file()
            else:
                # Fall back to file path approach
                return _initialize_from_file()
        
        return firestore.client()
    except Exception:
        print("❌ Firebase initialization error")
        print("📝 Using mock data instead")
        return None

def _initialize_from_file():
    """Initialize Firebase from service account file"""
    try:
        service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', './firebase-service-account.json')
        
        if os.path.exists(service_account_path):
            cred = credentials.Certificate(service_account_path)
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Admin SDK initialized successfully from file")
            return firestore.client()
        else:
            print("❌ Firebase service account file not found")
            print("📝 Using mock data instead")
            return None
    except Exception:
        print("❌ File-based Firebase initialization error")
        print("📝 Using mock data instead")
        return None

# Initialize Firestore
db = initialize_firebase()


def _parse_query_date(value: Optional[str], field_name: str) -> Optional[str]:
    """Validate an API date filter and return its canonical ISO representation."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{field_name} must use YYYY-MM-DD format")


def _trade_date_for_metrics(trade: dict) -> Optional[str]:
    """Return the date used for filtering a trade without exposing raw values."""
    value = trade.get("exit_date") if trade.get("status") == "closed" and trade.get("exit_date") else trade.get("date")
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    value_text = str(value)
    # Firestore timestamps and legacy strings can include a time component.
    return value_text[:10] if len(value_text) >= 10 else None

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
        return user_id
    except Exception as e:
        print("❌ Authentication failed")
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
    shares_to_exit: Union[float, str]
    sell_price: Union[float, str]
    notes: Optional[str] = ""
    
    @validator('shares_to_exit', pre=True)
    def parse_shares_to_exit(cls, v):
        return float(v) if v is not None else 0.0
    
    @validator('sell_price', pre=True)
    def parse_sell_price(cls, v):
        return float(v) if v is not None else 0.0

class UpdateTradeRequest(BaseModel):
    trade_id: str
    date: Optional[date] = None
    ticker: Optional[str] = None
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    shares: Optional[float] = None
    risk: Optional[float] = None
    risk_dollars: Optional[float] = None
    account_balance: Optional[float] = None
    notes: Optional[str] = None
    status: Optional[str] = None  # "open" or "closed"

class UserProfile(BaseModel):
    user_id: Optional[str] = None
    account_balance: float
    currency: Optional[str] = "USD"
    risk_tolerance: Optional[float] = 2.0  # Default 2% risk
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class MonthlyReturn(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None  # Set by the endpoint based on auth
    month: str  # Format: "Month YYYY" (e.g., "December 2024")
    start_cap: float
    close_cap: Optional[float] = None
    percentage_return: Optional[float] = None
    dollar_return: Optional[float] = None
    inr_return: Optional[float] = None
    comments: Optional[str] = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class FeesConfig(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None  # Set by the endpoint based on auth
    brokerage_percentage: float = 0.25  # Per transaction percentage
    brokerage_max_usd: float = 25.0  # Maximum brokerage fee in USD
    exchange_transaction_charges_percentage: float = 0.12  # Exchange transaction charges %
    ifsca_turnover_fees_percentage: float = 0.0001  # IFSCA turnover fees %
    platform_fee_usd: float = 0.0  # Platform fees per transaction
    withdrawal_fee_usd: float = 0.0  # Withdrawal fees
    amc_yearly_usd: float = 0.0  # Annual maintenance charges
    account_opening_fee_usd: float = 0.0  # One-time account opening fee
    tracking_charges_usd: float = 0.0  # Monthly tracking charges
    profile_verification_fee_usd: float = 0.0  # One-time KYC fee
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# Mock data fallback (same as main_simple.py)
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
]

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
        print("🔍 Add trade request received")
        
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
            except Exception:
                print("⚠️ Could not fetch account balance")
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
        print("🔐 Associating trade with authenticated account")
        
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
        print("❌ Error adding trade")
        raise HTTPException(status_code=500, detail="Unable to add trade")

@app.post("/exit-trade/{user_id}")
async def exit_trade(user_id: str, exit_request: ExitTradeRequest, current_user: str = Depends(get_current_user)):
    try:
        print("🔍 Exit trade request received")
        
        # Ensure user can only exit their own trades
        if user_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            
            # Find the open trade for this ticker and user
            query = trades_ref.where("user_id", "==", user_id).where("ticker", "==", exit_request.ticker).where("status", "==", "open")
            docs = query.get()
            print("🎯 Searched open trades")
            
            if not docs:
                # Check if there are any trades for this ticker (regardless of status)
                ticker_query = trades_ref.where("user_id", "==", user_id).where("ticker", "==", exit_request.ticker)
                ticker_docs = ticker_query.get()
                print("📈 No open trade matched the exit request")
                
                raise HTTPException(status_code=404, detail=f"No open trade found for {exit_request.ticker}. Found {len(ticker_docs)} total trades for this ticker.")
            
            # Get the first matching open trade
            trade_doc = docs[0]
            trade_data = trade_doc.to_dict()
            current_shares = trade_data.get('shares', 0)
            print("✅ Found an open trade for exit")
            
            # Validate exit shares
            if exit_request.shares_to_exit > current_shares:
                raise HTTPException(status_code=400, detail=f"Cannot exit {exit_request.shares_to_exit} shares. Only {current_shares} shares available.")
            
            # Calculate remaining shares
            remaining_shares = current_shares - exit_request.shares_to_exit
            
            # Handle floating-point precision issues - consider very small numbers as zero
            if abs(remaining_shares) < 1e-10:
                remaining_shares = 0
                
            if remaining_shares == 0:
                # Full exit - update the trade as closed
                update_data = {
                    'sell_price': exit_request.sell_price,
                    'status': 'closed',
                    'exit_date': datetime.now().strftime('%Y-%m-%d'),  # Store exit date
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
                    'exit_date': datetime.now().strftime('%Y-%m-%d'),  # Store exit date
                    'ticker': exit_request.ticker,
                    'buy_price': trade_data['buy_price'],
                    'sell_price': exit_request.sell_price,
                    'shares': exit_request.shares_to_exit,
                    'risk': trade_data.get('risk'),
                    'risk_dollars': trade_data.get('risk_dollars'),
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
                trade['exit_date'] = datetime.now().strftime('%Y-%m-%d')  # Store exit date
                trade['updated_at'] = datetime.now().isoformat()
                if exit_request.notes:
                    trade['notes'] = f"{trade.get('notes', '')} | Exit: {exit_request.notes}".strip(' |')
            else:
                # Partial exit - create new closed trade and update original
                exit_trade = {
                    "id": str(len(MOCK_TRADES) + 1),
                    "user_id": user_id,
                    "date": trade['date'],
                    "exit_date": datetime.now().strftime('%Y-%m-%d'),  # Store exit date
                    "ticker": exit_request.ticker,
                    "buy_price": trade['buy_price'],
                    "sell_price": exit_request.sell_price,
                    "shares": exit_request.shares_to_exit,
                    "risk": trade.get('risk'),
                    "risk_dollars": trade.get('risk_dollars'),
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
        print("❌ Error exiting trade")
        raise HTTPException(status_code=500, detail="Unable to exit trade")

@app.put("/trades/{trade_id}")
async def update_trade(trade_id: str, update_request: UpdateTradeRequest, current_user: str = Depends(get_current_user)):
    try:
        print("🔍 Update trade request received")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            trade_doc_ref = trades_ref.document(trade_id)
            trade_doc = trade_doc_ref.get()
            
            if not trade_doc.exists:
                print("❌ Trade not found")
                raise HTTPException(status_code=404, detail="Trade not found")
            
            trade_data = trade_doc.to_dict()
            
            # Ensure user can only update their own trades
            if trade_data.get('user_id') != current_user:
                print("❌ Unauthorized trade update attempt")
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Prepare update data - only include fields that are provided
            update_data = {}
            
            # Basic trade fields
            if update_request.date is not None:
                update_data['date'] = update_request.date.isoformat()
            if update_request.ticker is not None:
                update_data['ticker'] = update_request.ticker.upper()
            if update_request.buy_price is not None:
                update_data['buy_price'] = update_request.buy_price
            if update_request.sell_price is not None:
                update_data['sell_price'] = update_request.sell_price
            if update_request.shares is not None:
                update_data['shares'] = update_request.shares
            if update_request.risk is not None:
                update_data['risk'] = update_request.risk
            if update_request.risk_dollars is not None:
                update_data['risk_dollars'] = update_request.risk_dollars
            if update_request.account_balance is not None:
                update_data['account_balance'] = update_request.account_balance
            if update_request.notes is not None:
                update_data['notes'] = update_request.notes
            if update_request.status is not None:
                update_data['status'] = update_request.status
            
            # Validation based on status
            final_status = update_request.status or trade_data.get('status')
            final_buy_price = update_request.buy_price if update_request.buy_price is not None else trade_data.get('buy_price')
            final_sell_price = update_request.sell_price if update_request.sell_price is not None else trade_data.get('sell_price')
            
            if final_status == "open" and not final_buy_price:
                print(f"❌ Validation error: Buy price required for open trade")
                raise HTTPException(status_code=422, detail="Buy price is required for open trades")
            elif final_status == "closed" and not final_sell_price:
                print(f"❌ Validation error: Sell price required for closed trade")
                raise HTTPException(status_code=422, detail="Sell price is required for closed trades")
            
            # Risk validation - ensure at least one risk field exists after update
            final_risk = update_request.risk if update_request.risk is not None else trade_data.get('risk')
            final_risk_dollars = update_request.risk_dollars if update_request.risk_dollars is not None else trade_data.get('risk_dollars')
            
            if not final_risk and not final_risk_dollars:
                print(f"❌ Validation error: No risk information provided")
                raise HTTPException(status_code=422, detail="Either risk percentage or risk in dollars must be provided")
            
            # Calculate missing risk field if account balance is available
            account_balance = update_request.account_balance if update_request.account_balance is not None else trade_data.get('account_balance')
            if account_balance and account_balance > 0:
                if final_risk and not final_risk_dollars:
                    update_data['risk_dollars'] = (final_risk / 100) * account_balance
                elif final_risk_dollars and not final_risk:
                    update_data['risk'] = (final_risk_dollars / account_balance) * 100
            
            # Always update the timestamp
            update_data['updated_at'] = datetime.now()
            
            # Perform the update
            trade_doc_ref.update(update_data)
            
            print("✅ Trade updated successfully")
            return {"message": "Trade updated successfully", "trade_id": trade_id}
        
        else:
            # Fallback to mock data
            trade_found = False
            for trade in MOCK_TRADES:
                if trade['id'] == trade_id and trade['user_id'] == current_user:
                    trade_found = True
                    
                    # Update fields that are provided
                    if update_request.date is not None:
                        trade['date'] = update_request.date.isoformat()
                    if update_request.ticker is not None:
                        trade['ticker'] = update_request.ticker.upper()
                    if update_request.buy_price is not None:
                        trade['buy_price'] = update_request.buy_price
                    if update_request.sell_price is not None:
                        trade['sell_price'] = update_request.sell_price
                    if update_request.shares is not None:
                        trade['shares'] = update_request.shares
                    if update_request.risk is not None:
                        trade['risk'] = update_request.risk
                    if update_request.risk_dollars is not None:
                        trade['risk_dollars'] = update_request.risk_dollars
                    if update_request.account_balance is not None:
                        trade['account_balance'] = update_request.account_balance
                    if update_request.notes is not None:
                        trade['notes'] = update_request.notes
                    if update_request.status is not None:
                        trade['status'] = update_request.status
                    
                    trade['updated_at'] = datetime.now().isoformat()
                    break
            
            if not trade_found:
                raise HTTPException(status_code=404, detail="Trade not found or access denied")
            
            return {"message": "Trade updated successfully (mock)", "trade_id": trade_id}
    
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error updating trade")
        raise HTTPException(status_code=500, detail="Unable to update trade")

@app.delete("/trades/{trade_id}")
async def delete_trade(trade_id: str, current_user: str = Depends(get_current_user)):
    try:
        print("🔍 Delete trade request received")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            trade_doc_ref = trades_ref.document(trade_id)
            trade_doc = trade_doc_ref.get()
            
            if not trade_doc.exists:
                print("❌ Trade not found")
                raise HTTPException(status_code=404, detail="Trade not found")
            
            trade_data = trade_doc.to_dict()
            
            # Ensure user can only delete their own trades
            if trade_data.get('user_id') != current_user:
                print("❌ Unauthorized trade deletion attempt")
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Delete the trade document
            trade_doc_ref.delete()
            print("✅ Trade deleted successfully")
            
            return {"message": "Trade deleted successfully", "trade_id": trade_id}
        else:
            # Mock data - simulate deletion
            print("✅ Trade deleted successfully (mock)")
            return {"message": "Trade deleted successfully (mock)", "trade_id": trade_id}
    
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error deleting trade")
        raise HTTPException(status_code=500, detail="Unable to delete trade")

@app.get("/trades/{user_id}")
async def get_trades(user_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, current_user: str = Depends(get_current_user)):
    try:
        from_date = _parse_query_date(from_date, "from_date")
        to_date = _parse_query_date(to_date, "to_date")
        if from_date and to_date and from_date > to_date:
            raise HTTPException(status_code=422, detail="from_date must be on or before to_date")
        
        # Ensure user can only access their own trades
        if user_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            trades_ref = db.collection('trades')
            # Get all trades for the user first (no date filtering at DB level)
            query = trades_ref.where("user_id", "==", user_id)
            
            docs = query.get()
            all_trades = []
            for doc in docs:
                trade_data = doc.to_dict()
                trade_data['id'] = doc.id
                
                # Ensure date is a string
                if trade_data.get('date'):
                    if isinstance(trade_data['date'], datetime):
                        trade_data['date'] = trade_data['date'].isoformat()
                    elif hasattr(trade_data['date'], 'strftime'):
                        trade_data['date'] = trade_data['date'].strftime('%Y-%m-%d')
                    # If it's already a string, keep it as is
                
                # Ensure exit_date is a string if it exists
                if trade_data.get('exit_date'):
                    if isinstance(trade_data['exit_date'], datetime):
                        trade_data['exit_date'] = trade_data['exit_date'].isoformat()
                    elif hasattr(trade_data['exit_date'], 'strftime'):
                        trade_data['exit_date'] = trade_data['exit_date'].strftime('%Y-%m-%d')
                
                # Convert datetime objects to strings
                for field in ['created_at', 'updated_at']:
                    if isinstance(trade_data.get(field), datetime):
                        trade_data[field] = trade_data[field].isoformat()
                
                all_trades.append(trade_data)
            
            # Filter once using exit_date for closed trades and entry date otherwise.
            trades = all_trades
            if from_date or to_date:
                trades = [
                    trade for trade in all_trades
                    if (trade_date := _trade_date_for_metrics(trade)) is not None
                    and (not from_date or trade_date >= from_date)
                    and (not to_date or trade_date <= to_date)
                ]
            return {"trades": trades}
        else:
            # Fallback to mock data
            trades = [trade for trade in MOCK_TRADES if trade['user_id'] == user_id]
            if from_date or to_date:
                trades = [
                    trade for trade in trades
                    if (trade_date := _trade_date_for_metrics(trade)) is not None
                    and (not from_date or trade_date >= from_date)
                    and (not to_date or trade_date <= to_date)
                ]
            return {"trades": trades}
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error fetching trades")
        raise HTTPException(status_code=500, detail="Unable to fetch trades")

@app.get("/metrics/{user_id}")
async def get_metrics(user_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, current_user: str = Depends(get_current_user)):
    try:
        from_date = _parse_query_date(from_date, "from_date")
        to_date = _parse_query_date(to_date, "to_date")
        if from_date and to_date and from_date > to_date:
            raise HTTPException(status_code=422, detail="from_date must be on or before to_date")

        # Ensure user can only access their own metrics
        if user_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")

        if db:
            docs = db.collection("trades").where("user_id", "==", user_id).get()
            all_trades = [doc.to_dict() for doc in docs]
        else:
            all_trades = [trade for trade in MOCK_TRADES if trade['user_id'] == user_id]

        trades = all_trades
        if from_date or to_date:
            trades = [
                trade for trade in all_trades
                if (trade_date := _trade_date_for_metrics(trade)) is not None
                and (not from_date or trade_date >= from_date)
                and (not to_date or trade_date <= to_date)
            ]

        closed_trades = [
            trade for trade in trades
            if trade.get("status") == "closed" and trade.get("sell_price") is not None and trade.get("buy_price") is not None
        ]

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
        gross_loss = abs(sum(losing_trades)) if losing_trades else 0
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
        
    except HTTPException:
        raise
    except Exception:
        print("❌ Error calculating metrics")
        raise HTTPException(status_code=500, detail="Unable to calculate metrics")

@app.get("/profile/{user_id}")
async def get_user_profile(user_id: str, current_user: str = Depends(get_current_user)):
    try:
        # Ensure user can only access their own profile
        if user_id != current_user:
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
    except HTTPException:
        raise
    except Exception:
        print("❌ Error fetching profile")
        raise HTTPException(status_code=500, detail="Unable to fetch profile")

@app.put("/profile/{user_id}")
async def update_user_profile(user_id: str, profile_data: dict, current_user: str = Depends(get_current_user)):
    try:
        print("🔍 Profile update request received")
        
        # Ensure user can only update their own profile
        if user_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Validate required fields
        if 'account_balance' not in profile_data:
            print(f"❌ Missing account_balance in request")
            raise HTTPException(status_code=422, detail="account_balance is required")
        
        # Convert and validate account_balance (handle string input from frontend)
        try:
            account_balance = float(profile_data['account_balance'])
            if account_balance <= 0:
                print("❌ Account balance must be positive")
                raise HTTPException(status_code=422, detail="account_balance must be a positive number")
        except (ValueError, TypeError):
            print("❌ Invalid account_balance format")
            raise HTTPException(status_code=422, detail="account_balance must be a valid number")
        
        # Convert and validate risk_tolerance (handle string input from frontend)
        try:
            risk_tolerance = float(profile_data.get('risk_tolerance', 2.0))
            if risk_tolerance < 0 or risk_tolerance > 100:
                print("❌ Risk tolerance out of range")
                raise HTTPException(status_code=422, detail="risk_tolerance must be between 0 and 100")
        except (ValueError, TypeError):
            print("❌ Invalid risk_tolerance format")
            raise HTTPException(status_code=422, detail="risk_tolerance must be a valid number")
        
        # Create profile object with defaults
        profile_obj = {
            'account_balance': account_balance,
            'currency': profile_data.get('currency', 'USD'),
            'risk_tolerance': risk_tolerance,
            'updated_at': datetime.now()
        }
        
        print("📋 Profile validation passed")
        
        if db:
            # Use Firebase Firestore
            profiles_ref = db.collection('user_profiles')
            doc_ref = profiles_ref.document(user_id)
            
            # Check if profile exists
            profile_exists = doc_ref.get().exists
            print("📋 Profile lookup completed")
            
            if not profile_exists:
                profile_obj['created_at'] = datetime.now()
                print("🆕 Creating new profile")
            
            # Update profile
            print(f"💾 Saving profile data to Firestore")
            doc_ref.set(profile_obj, merge=True)
            print("✅ Profile saved successfully")
            
            return {"message": "Profile updated successfully", "user_id": user_id}
        else:
            # Mock data fallback
            print("📝 Using mock data for profile update")
            return {"message": "Profile updated successfully (mock)", "user_id": user_id}
            
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error updating profile")
        raise HTTPException(status_code=500, detail="Unable to update profile")

@app.get("/profile/{user_id}/account-balance")
async def get_account_balance(user_id: str, current_user: str = Depends(get_current_user)):
    """Quick endpoint to get just the account balance for risk calculations"""
    try:
        # Ensure user can only access their own account balance
        if user_id != current_user:
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
    except HTTPException:
        raise
    except Exception:
        print("❌ Error fetching account balance")
        raise HTTPException(status_code=500, detail="Unable to fetch account balance")

# Monthly Returns Management Endpoints

@app.get("/monthly-returns/{user_id}")
async def get_monthly_returns(user_id: str, current_user: str = Depends(get_current_user)):
    """Get all monthly returns for a user"""
    try:
        # Ensure user can only access their own monthly returns
        if user_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            returns_ref = db.collection('monthly_returns')
            query = returns_ref.where("user_id", "==", user_id).order_by("created_at")
            
            docs = query.get()
            returns = []
            for doc in docs:
                return_data = doc.to_dict()
                return_data['id'] = doc.id
                
                # Convert datetime objects to strings
                for field in ['created_at', 'updated_at']:
                    if isinstance(return_data.get(field), datetime):
                        return_data[field] = return_data[field].isoformat()
                
                returns.append(return_data)
            
            return {"monthly_returns": returns}
        else:
            # Mock data fallback
            mock_returns = [
                {
                    "id": "1",
                    "user_id": user_id,
                    "month": "December 2024",
                    "start_cap": 705.81,
                    "close_cap": 1190.38,
                    "percentage_return": 68.65,
                    "dollar_return": 484.57,
                    "inr_return": 42157.59,
                    "comments": ""
                },
                {
                    "id": "2",
                    "user_id": user_id,
                    "month": "January 2025",
                    "start_cap": 1190.38,
                    "close_cap": 1154.54,
                    "percentage_return": -3.01,
                    "dollar_return": -35.84,
                    "inr_return": -3118.08,
                    "comments": ""
                }
            ]
            return {"monthly_returns": mock_returns}
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error fetching monthly returns")
        raise HTTPException(status_code=500, detail="Unable to fetch monthly returns")

@app.post("/monthly-returns")
async def create_or_update_monthly_return(monthly_return: MonthlyReturn, current_user: str = Depends(get_current_user)):
    """Create or update a monthly return"""
    try:
        print("🔍 Create/update monthly return request received")
        
        # Ensure user can only create/update their own monthly returns
        monthly_return.user_id = current_user
        
        # Validation
        if not monthly_return.month:
            raise HTTPException(status_code=422, detail="Month is required")
        
        if monthly_return.start_cap is None or monthly_return.start_cap <= 0:
            raise HTTPException(status_code=422, detail="Start capital must be a positive number")
        
        # Calculate returns if close_cap is provided
        if monthly_return.close_cap is not None:
            if monthly_return.percentage_return is None:
                monthly_return.percentage_return = ((monthly_return.close_cap - monthly_return.start_cap) / monthly_return.start_cap) * 100
            
            if monthly_return.dollar_return is None:
                monthly_return.dollar_return = monthly_return.close_cap - monthly_return.start_cap
        
        monthly_return.updated_at = datetime.now()
        
        if db:
            # Use Firebase Firestore
            returns_ref = db.collection('monthly_returns')
            
            # Check if monthly return already exists
            existing_query = returns_ref.where("user_id", "==", current_user).where("month", "==", monthly_return.month).limit(1)
            existing_docs = list(existing_query.get())
            
            if existing_docs:
                # Update existing
                doc_ref = existing_docs[0].reference
                update_data = monthly_return.model_dump(exclude={'id', 'created_at'})
                # Remove None values
                update_data = {k: v for k, v in update_data.items() if v is not None}
                doc_ref.update(update_data)
                return_id = existing_docs[0].id
                print("✅ Updated existing monthly return")
            else:
                # Create new
                monthly_return.created_at = datetime.now()
                doc_data = monthly_return.model_dump(exclude={'id'})
                # Remove None values
                doc_data = {k: v for k, v in doc_data.items() if v is not None}
                doc_ref = returns_ref.add(doc_data)
                return_id = doc_ref[1].id
                print("✅ Created new monthly return")
            
            return {
                "message": "Monthly return saved successfully",
                "return_id": return_id,
                "user_id": current_user
            }
        else:
            # Mock data fallback
            return {
                "message": "Monthly return saved successfully (mock)",
                "return_id": "mock_id",
                "user_id": current_user
            }
            
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error saving monthly return")
        raise HTTPException(status_code=500, detail="Unable to save monthly return")

@app.delete("/monthly-returns/{return_id}")
async def delete_monthly_return(return_id: str, current_user: str = Depends(get_current_user)):
    """Delete a monthly return"""
    try:
        print("🔍 Delete monthly return request received")
        
        if db:
            # Use Firebase Firestore
            returns_ref = db.collection('monthly_returns')
            doc_ref = returns_ref.document(return_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                raise HTTPException(status_code=404, detail="Monthly return not found")
            
            return_data = doc.to_dict()
            
            # Ensure user can only delete their own monthly returns
            if return_data.get('user_id') != current_user:
                raise HTTPException(status_code=403, detail="Access denied")
            
            doc_ref.delete()
            print("✅ Deleted monthly return")
            
            return {"message": "Monthly return deleted successfully"}
        else:
            # Mock data fallback
            return {"message": "Monthly return deleted successfully (mock)"}
            
    except HTTPException:
        raise
    except Exception as e:
        print("❌ Error deleting monthly return")
        raise HTTPException(status_code=500, detail="Unable to delete monthly return")

# Fees Configuration Management Endpoints

@app.get("/fees-config/{user_id}")
async def get_fees_config(user_id: str, current_user: str = Depends(get_current_user)):
    """Get fees configuration for a user"""
    try:
        # Ensure user can only access their own fees configuration
        if user_id != current_user:
            raise HTTPException(status_code=403, detail="Access denied")
        
        if db:
            # Use Firebase Firestore
            fees_ref = db.collection('fees_configs')
            doc = fees_ref.document(user_id).get()
            
            if doc.exists:
                fees_data = doc.to_dict()
                fees_data['user_id'] = user_id
                
                # Convert datetime objects to strings
                for field in ['created_at', 'updated_at']:
                    if isinstance(fees_data.get(field), datetime):
                        fees_data[field] = fees_data[field].isoformat()
                
                return {"fees_config": fees_data}
            else:
                # Return default fees configuration
                default_config = FeesConfig(user_id=user_id)
                return {"fees_config": default_config.model_dump(exclude={'id', 'created_at', 'updated_at'})}
        else:
            # Mock data fallback
            default_config = FeesConfig(user_id=user_id)
            return {"fees_config": default_config.model_dump(exclude={'id', 'created_at', 'updated_at'})}
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error fetching fees config")
        raise HTTPException(status_code=500, detail="Unable to fetch fees configuration")

@app.post("/fees-config")
async def save_fees_config(fees_config: FeesConfig, current_user: str = Depends(get_current_user)):
    """Save or update fees configuration"""
    try:
        print("🔍 Save fees config request received")
        
        # Ensure user can only save their own fees configuration
        fees_config.user_id = current_user
        
        # Validation
        if fees_config.brokerage_percentage < 0 or fees_config.brokerage_percentage > 10:
            raise HTTPException(status_code=422, detail="Brokerage percentage must be between 0% and 10%")
        
        if fees_config.brokerage_max_usd < 0:
            raise HTTPException(status_code=422, detail="Maximum brokerage fee cannot be negative")
        
        if fees_config.exchange_transaction_charges_percentage < 0:
            raise HTTPException(status_code=422, detail="Exchange charges percentage cannot be negative")
        
        if fees_config.ifsca_turnover_fees_percentage < 0:
            raise HTTPException(status_code=422, detail="IFSCA fees percentage cannot be negative")
        
        # Validate that all fee amounts are non-negative
        for field in ['platform_fee_usd', 'withdrawal_fee_usd', 'amc_yearly_usd', 
                     'account_opening_fee_usd', 'tracking_charges_usd', 'profile_verification_fee_usd']:
            if getattr(fees_config, field) < 0:
                raise HTTPException(status_code=422, detail=f"{field} cannot be negative")
        
        fees_config.updated_at = datetime.now()
        
        if db:
            # Use Firebase Firestore
            fees_ref = db.collection('fees_configs')
            doc_ref = fees_ref.document(current_user)
            
            # Check if fees config already exists
            fees_exists = doc_ref.get().exists
            print(f"📋 Fees config exists: {fees_exists}")
            
            if not fees_exists:
                fees_config.created_at = datetime.now()
                print(f"🆕 Creating new fees config with created_at: {fees_config.created_at}")
            
            # Prepare data for Firestore
            config_data = fees_config.model_dump(exclude={'id'})
            
            # Save fees configuration
            print("💾 Saving fees config data to Firestore")
            doc_ref.set(config_data, merge=True)
            print("✅ Fees config saved successfully")
            
            return {"message": "Fees configuration saved successfully", "user_id": current_user}
        else:
            # Mock data fallback
            print("📝 Using mock data for fees config save")
            return {"message": "Fees configuration saved successfully (mock)", "user_id": current_user}
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error saving fees config")
        raise HTTPException(status_code=500, detail="Unable to save fees configuration")

# Email-related models
class EmailRequest(BaseModel):
    email: str
    user_name: Optional[str] = None

class TriggerWelcomeEmailRequest(BaseModel):
    email: str
    user_name: Optional[str] = None
    is_new_user: Optional[bool] = False

class TradeReminderRequest(BaseModel):
    email: str
    user_name: Optional[str] = None
    days_inactive: Optional[int] = 7

class WeeklySummaryRequest(BaseModel):
    email: str
    user_name: Optional[str] = None
    summary_data: Optional[dict] = None

# Email endpoints
@app.post("/resubscribe-email")
async def resubscribe_email(request: EmailRequest, current_user: str = Depends(get_current_user)):
    """Re-subscribe user email that was previously unsubscribed"""
    try:
        print("📧 Re-subscribe email request received")
        
        # Verify the user is resubscribing their own email
        user_record = auth.get_user(current_user)
        if user_record.email != request.email:
            raise HTTPException(status_code=403, detail="You can only resubscribe your own email address")
        
        success = email_service.resubscribe_email(request.email)
        
        if success:
            print("✅ Email resubscribed successfully")
            return {"message": "Email resubscribed successfully", "email": request.email}
        else:
            print("❌ Failed to resubscribe email")
            raise HTTPException(status_code=500, detail="Failed to resubscribe email")
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error resubscribing email")
        raise HTTPException(status_code=500, detail="Unable to resubscribe email")

@app.post("/trigger-welcome-email")
async def trigger_welcome_email(request: TriggerWelcomeEmailRequest, current_user: str = Depends(get_current_user)):
    """Trigger welcome email on login/signup with user tracking"""
    try:
        print("📧 Welcome email request received")
        
        # Verify the user is triggering email for themselves
        user_record = auth.get_user(current_user)
        if user_record.email != request.email:
            raise HTTPException(status_code=403, detail="You can only trigger emails for your own email address")
        
        # Check if user has already received welcome email (for existing users)
        welcome_email_sent = False
        if db and not request.is_new_user:
            try:
                # Check if user has a "welcome_email_sent" flag in their profile
                user_doc = db.collection('users').document(current_user).get()
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    welcome_email_sent = user_data.get('welcome_email_sent', False)
                    
                if welcome_email_sent:
                    print("🔄 Welcome email already sent; skipping")
                    return {"message": "Welcome email already sent", "email": request.email, "skipped": True}
            except Exception:
                print("⚠️ Could not check welcome email status")
        
        # Send the welcome email
        success = email_service.send_welcome_email(request.email, request.user_name)
        
        if success:
            # Mark welcome email as sent in user profile
            if db:
                try:
                    user_ref = db.collection('users').document(current_user)
                    user_ref.set({
                        'welcome_email_sent': True,
                        'welcome_email_sent_at': datetime.now(),
                        'email': request.email
                    }, merge=True)
                    print("✅ Marked welcome email as sent")
                except Exception:
                    print("⚠️ Could not update user welcome email status")
            
            print("✅ Welcome email sent successfully")
            return {"message": "Welcome email sent successfully", "email": request.email, "triggered": True}
        else:
            print("❌ Failed to send welcome email")
            raise HTTPException(status_code=500, detail="Failed to send welcome email")
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error triggering welcome email")
        # Don't fail the login process if email fails
        return {"message": "Email service temporarily unavailable", "email": request.email}

@app.post("/send-welcome-email")
async def send_welcome_email(request: EmailRequest, current_user: str = Depends(get_current_user)):
    """Send welcome email to user"""
    try:
        print("📧 Send welcome email request received")
        
        # Verify the user is sending email to themselves or has permission
        user_record = auth.get_user(current_user)
        if user_record.email != request.email:
            raise HTTPException(status_code=403, detail="You can only send emails to your own email address")
        
        success = email_service.send_welcome_email(request.email, request.user_name)
        
        if success:
            print("✅ Welcome email sent successfully")
            return {"message": "Welcome email sent successfully", "email": request.email}
        else:
            print("❌ Failed to send welcome email")
            raise HTTPException(status_code=500, detail="Failed to send welcome email")
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error sending welcome email")
        raise HTTPException(status_code=500, detail="Unable to send welcome email")

@app.post("/send-trade-reminder")
async def send_trade_reminder(request: TradeReminderRequest, current_user: str = Depends(get_current_user)):
    """Send trade reminder email to user"""
    try:
        print("📧 Send trade reminder request received")
        
        # Verify the user is sending email to themselves
        user_record = auth.get_user(current_user)
        if user_record.email != request.email:
            raise HTTPException(status_code=403, detail="You can only send emails to your own email address")
        
        success = email_service.send_trade_reminder(
            request.email, 
            request.user_name, 
            request.days_inactive
        )
        
        if success:
            print("✅ Trade reminder sent successfully")
            return {"message": "Trade reminder sent successfully", "email": request.email}
        else:
            print("❌ Failed to send trade reminder")
            raise HTTPException(status_code=500, detail="Failed to send trade reminder")
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error sending trade reminder")
        raise HTTPException(status_code=500, detail="Unable to send trade reminder")

@app.post("/send-weekly-summary")
async def send_weekly_summary(request: WeeklySummaryRequest, current_user: str = Depends(get_current_user)):
    """Send weekly summary email to user"""
    try:
        print("📧 Send weekly summary request received")
        
        # Verify the user is sending email to themselves
        user_record = auth.get_user(current_user)
        if user_record.email != request.email:
            raise HTTPException(status_code=403, detail="You can only send emails to your own email address")
        
        # If no summary data provided, fetch user's actual trading data
        summary_data = request.summary_data
        if not summary_data and db:
            try:
                # Fetch user's trades for the past week
                from datetime import timedelta
                week_ago = datetime.now() - timedelta(days=7)
                
                trades_ref = db.collection('trades')
                recent_trades = trades_ref.where('user_id', '==', current_user)\
                                        .where('date', '>=', week_ago)\
                                        .stream()
                
                trades_list = []
                for trade in recent_trades:
                    trade_data = trade.to_dict()
                    trades_list.append(trade_data)
                
                # Calculate summary stats
                total_trades = len(trades_list)
                total_pnl = sum(trade.get('realized_pnl', 0) for trade in trades_list)
                winning_trades = [t for t in trades_list if t.get('realized_pnl', 0) > 0]
                win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
                best_trade = max([t.get('realized_pnl', 0) for t in trades_list], default=0)
                worst_trade = min([t.get('realized_pnl', 0) for t in trades_list], default=0)
                
                summary_data = {
                    'total_trades': total_trades,
                    'profit_loss': total_pnl,
                    'win_rate': win_rate,
                    'best_trade': best_trade,
                    'worst_trade': worst_trade
                }
                
                print("📊 Weekly summary data calculated")
                
            except Exception:
                print("⚠️ Could not fetch trading data; using defaults")
                summary_data = None
        
        success = email_service.send_weekly_summary(
            request.email, 
            request.user_name,
            summary_data
        )
        
        if success:
            print("✅ Weekly summary sent successfully")
            return {"message": "Weekly summary sent successfully", "email": request.email}
        else:
            print("❌ Failed to send weekly summary")
            raise HTTPException(status_code=500, detail="Failed to send weekly summary")
            
    except HTTPException:
        raise
    except Exception:
        print("❌ Error sending weekly summary")
        raise HTTPException(status_code=500, detail="Unable to send weekly summary")

@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
