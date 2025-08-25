# Fees Configuration API Implementation

## Overview
Added comprehensive fees configuration management to the TradeTracker backend API to support accurate P&L calculations with trading fees.

## New Backend Components

### 1. Pydantic Model (FeesConfig)

```python
class FeesConfig(BaseModel):
    id: Optional[str] = None
    user_id: Optional[str] = None
    brokerage_percentage: float = 0.25          # 0.25% per transaction
    brokerage_max_usd: float = 25.0             # Max $25 cap
    exchange_transaction_charges_percentage: float = 0.12    # 0.12%
    ifsca_turnover_fees_percentage: float = 0.0001          # 0.0001%
    platform_fee_usd: float = 0.0              # $0 platform fee
    withdrawal_fee_usd: float = 0.0             # $0 withdrawal fee
    amc_yearly_usd: float = 0.0                 # $0 AMC
    account_opening_fee_usd: float = 0.0        # $0 account opening
    tracking_charges_usd: float = 0.0           # $0 tracking charges
    profile_verification_fee_usd: float = 0.0   # $0 KYC fee
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
```

### 2. API Endpoints

#### GET `/fees-config/{user_id}`
- **Purpose**: Retrieve fees configuration for a user
- **Authentication**: Required (Firebase ID token)
- **Authorization**: Users can only access their own fees config
- **Response**: Returns saved config or default values
- **Firestore Collection**: `fees_configs`

#### POST `/fees-config`
- **Purpose**: Save or update fees configuration
- **Authentication**: Required (Firebase ID token)
- **Validation**: 
  - Brokerage percentage: 0-10%
  - All fee amounts: ≥ 0
  - Required fields validation
- **Behavior**: Creates new or updates existing config

### 3. Database Structure

**Firestore Collection**: `fees_configs`
**Document ID**: `{user_id}` (one config per user)

```json
{
  "user_id": "firebase_user_id",
  "brokerage_percentage": 0.25,
  "brokerage_max_usd": 25.0,
  "exchange_transaction_charges_percentage": 0.12,
  "ifsca_turnover_fees_percentage": 0.0001,
  "platform_fee_usd": 0.0,
  "withdrawal_fee_usd": 0.0,
  "amc_yearly_usd": 0.0,
  "account_opening_fee_usd": 0.0,
  "tracking_charges_usd": 0.0,
  "profile_verification_fee_usd": 0.0,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

## Default Fees Configuration

Based on your broker information:
- **Brokerage**: 0.25% per transaction (max $25 excl GST)
- **Exchange charges**: 0.12%
- **IFSCA fees**: 0.0001%
- **All other fees**: $0 (as per your zero-fee broker)

## Frontend Integration

The frontend components now include:
- **Profile Page**: Fees Configuration tab
- **Dashboard**: Gross vs Net P&L toggle
- **Fee calculations**: Real-time preview and totals
- **MonthlyReturns**: Fees information banner

## Security Features

1. **Authentication**: All endpoints require valid Firebase ID tokens
2. **Authorization**: Users can only access/modify their own fees config
3. **Validation**: Server-side validation for all fee parameters
4. **Error Handling**: Comprehensive error responses with descriptive messages

## Testing

Use the provided test script:
```bash
cd backend
python test_fees_api.py
```

## Mock Data Support

Both endpoints support mock data fallback when Firebase is unavailable, ensuring development continuity.

## Error Handling

- **401**: Invalid or missing authentication
- **403**: Access denied (trying to access another user's config)
- **422**: Validation errors (invalid fee values)
- **500**: Server errors with detailed logging

## Usage Examples

### Get Fees Config
```bash
curl -X GET "http://localhost:8000/fees-config/user123" \
  -H "Authorization: Bearer your_firebase_token"
```

### Save Fees Config
```bash
curl -X POST "http://localhost:8000/fees-config" \
  -H "Authorization: Bearer your_firebase_token" \
  -H "Content-Type: application/json" \
  -d '{
    "brokerage_percentage": 0.25,
    "brokerage_max_usd": 25.0,
    "exchange_transaction_charges_percentage": 0.12,
    "ifsca_turnover_fees_percentage": 0.0001,
    "platform_fee_usd": 0.0
  }'
```

## Integration Status

✅ **Backend API**: Complete
✅ **Frontend Components**: Complete
✅ **Database Schema**: Ready
✅ **Authentication**: Integrated
✅ **Validation**: Implemented
✅ **Error Handling**: Complete
✅ **Mock Data Support**: Available

The fees system is now fully integrated and ready for production use!
