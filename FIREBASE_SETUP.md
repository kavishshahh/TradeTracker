# 🔥 Firebase Database Setup Guide

This guide will help you connect your TradeTracker to Firebase Firestore database.

## Step 1: Create Firebase Project

1. **Go to Firebase Console**: https://console.firebase.google.com/
2. **Click "Create a project"**
3. **Project Setup**:
   - Project name: `TradeTracker` (or your preferred name)
   - Enable Google Analytics: Optional
   - Choose your analytics account if enabled

## Step 2: Enable Firestore Database

1. **In Firebase Console** → Build → Firestore Database
2. **Click "Create database"**
3. **Security rules**: Choose "Start in test mode" (for development)
4. **Location**: Select closest to your region
5. **Click "Done"**

## Step 3: Get Frontend Configuration

1. **Go to Project Settings** (gear icon)
2. **Scroll to "Your apps"** → Click Web app icon (`</>`)
3. **Register app**:
   - App nickname: `TradeTracker-Frontend`
   - Don't enable Firebase Hosting (for now)
4. **Copy the config object** - you'll need these values:

```javascript
const firebaseConfig = {
  apiKey: "your-api-key",
  authDomain: "your-project.firebaseapp.com", 
  projectId: "your-project-id",
  storageBucket: "your-project.appspot.com",
  messagingSenderId: "123456789",
  appId: "your-app-id"
};
```

## Step 4: Get Backend Service Account

1. **Go to Project Settings** → Service Accounts tab
2. **Click "Generate new private key"**
3. **Download the JSON file**
4. **Save it as `firebase-service-account.json` in the `backend/` folder**

⚠️ **Security Note**: Never commit this file to Git! It's already in .gitignore.

## Step 5: Configure Environment Variables

### Frontend (.env.local)

Create `.env.local` in the root directory:

```bash
# Copy from env.local.example and fill in your values
NEXT_PUBLIC_FIREBASE_API_KEY=your_api_key_here
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your_project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your_project_id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your_project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_sender_id
NEXT_PUBLIC_FIREBASE_APP_ID=your_app_id
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### Backend (.env)

Create `.env` in the `backend/` directory:

```bash
# Copy from backend/env.example and update
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
FIREBASE_PROJECT_ID=your_project_id
```

## Step 6: Install Dependencies

Make sure Firebase Admin SDK is installed:

```bash
cd backend
venv\Scripts\activate
pip install firebase-admin
```

## Step 7: Test Firebase Connection

1. **Start the Firebase backend**:
   ```bash
   # From project root
   ./start-firebase-dev.bat
   ```
   
   Or manually:
   ```bash
   # Terminal 1 - Backend
   cd backend
   venv\Scripts\activate
   python main_firebase.py
   
   # Terminal 2 - Frontend
   npm run dev
   ```

2. **Check the connection**:
   - Go to http://localhost:8000
   - Should show: `{"message": "TradeTracker API is running", "status": "ok", "firebase": "connected"}`

## Step 8: Test Adding Trades

1. **Go to your app**: http://localhost:3000
2. **Add a trade** via the Add Trade page
3. **Check Firebase Console**:
   - Go to Firestore Database
   - You should see a `trades` collection with your data

## Firestore Database Structure

Your trades will be stored in Firestore with this structure:

```
trades/ (collection)
  ├── [auto-generated-id]/ (document)
  │   ├── user_id: "user123"
  │   ├── date: "2024-01-15" 
  │   ├── ticker: "AAPL"
  │   ├── buy_price: 150.00
  │   ├── sell_price: 165.00
  │   ├── shares: 100
  │   ├── risk: 2.0
  │   ├── notes: "Strong breakout pattern"
  │   ├── status: "closed"
  │   ├── created_at: timestamp
  │   └── updated_at: timestamp
  └── [another-trade]/ (document)
      └── ...
```

## Security Rules (Production)

For production, update your Firestore security rules:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Only allow authenticated users to read/write their own trades
    match /trades/{document} {
      allow read, write: if request.auth != null && 
                        resource.data.user_id == request.auth.uid;
    }
  }
}
```

## Troubleshooting

### Common Issues:

1. **"Firebase not connected"**:
   - Check service account file path
   - Verify environment variables
   - Ensure service account JSON is valid

2. **"Permission denied"**:
   - Update Firestore security rules
   - Check if database is in test mode

3. **"Config not found"**:
   - Verify .env.local file exists
   - Check environment variable names (NEXT_PUBLIC_ prefix)
   - Restart development server after adding env vars

### Verification Steps:

1. ✅ Firebase project created
2. ✅ Firestore database enabled
3. ✅ Web app registered
4. ✅ Service account key downloaded
5. ✅ Environment variables configured
6. ✅ Backend shows "firebase": "connected"
7. ✅ Trades appear in Firestore console

## Migration from Mock Data

The Firebase backend (`main_firebase.py`) includes automatic fallback:
- If Firebase is configured: Uses Firestore database
- If Firebase fails: Falls back to mock data
- No data loss during transition

Once Firebase is working, you can:
1. Copy mock trades to Firestore (if needed)
2. Switch completely to Firebase backend
3. Remove mock data

## Need Help?

If you encounter issues:
1. Check the browser console for errors
2. Check backend logs for Firebase connection status
3. Verify all environment variables are set correctly
4. Ensure service account file is in the correct location
