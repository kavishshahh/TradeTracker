# 🔐 Firebase Authentication Setup Guide

This guide will help you set up Firebase Authentication for your TradeTracker app to secure user data and provide proper user isolation.

## 🚀 **Step 1: Enable Firebase Authentication**

### **1.1 Go to Firebase Console**
1. Visit [Firebase Console](https://console.firebase.google.com/)
2. Select your project (`rico-ab911`)

### **1.2 Enable Authentication**
1. In the left sidebar, click **"Authentication"**
2. Click **"Get started"**
3. Click **"Sign-in method"** tab
4. Click **"Email/Password"**
5. **Enable** Email/Password authentication
6. Click **"Save"**

### **1.3 Configure Authentication Settings**
1. Go to **"Settings"** tab
2. Add your **Authorized domains**:
   - `localhost` (for development)
   - Your production domain (when deployed)
3. Click **"Save"**

## 🔑 **Step 2: Update Environment Variables**

### **2.1 Frontend Environment**
Create/update `.env.local` with your Firebase config:

```bash
# Firebase Configuration
NEXT_PUBLIC_FIREBASE_API_KEY=your_api_key_here
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=rico-ab911.firebaseapp.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=rico-ab911
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=rico-ab911.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=your_sender_id_here
NEXT_PUBLIC_FIREBASE_APP_ID=your_app_id_here

# Backend API URL
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

### **2.2 Backend Environment**
Update `backend/.env` with your Firebase service account:

```bash
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
```

## 🔧 **Step 3: Get Firebase Service Account Key**

### **3.1 Generate Service Account Key**
1. In Firebase Console, go to **"Project Settings"**
2. Click **"Service accounts"** tab
3. Click **"Generate new private key"**
4. Download the JSON file
5. Rename it to `firebase-service-account.json`
6. Place it in the `backend/` folder

### **3.2 Service Account File Structure**
The file should look like this:
```json
{
  "type": "service_account",
  "project_id": "rico-ab911",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-...@rico-ab911.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/..."
}
```

## 🏗️ **Step 4: Security Rules for Firestore**

### **4.1 Update Firestore Rules**
In Firebase Console, go to **"Firestore Database"** → **"Rules"** and update with:

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Users can only access their own data
    match /trades/{tradeId} {
      allow read, write: if request.auth != null && request.auth.uid == resource.data.user_id;
      allow create: if request.auth != null && request.auth.uid == request.resource.data.user_id;
    }
    
    match /user_profiles/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

## 🧪 **Step 5: Test the Authentication**

### **5.1 Start the Application**
1. **Frontend**: `npm run dev`
2. **Backend**: `cd backend && python main_firebase.py`

### **5.2 Test User Flow**
1. Visit `http://localhost:3000`
2. You'll be redirected to `/login`
3. **Create Account**:
   - Click "Don't have an account? Sign up"
   - Enter email and password
   - Click "Create Account"
4. **Sign In**:
   - Use your credentials to sign in
   - You'll be redirected to the dashboard

### **5.3 Verify User Isolation**
1. Create a trade while signed in
2. Check Firestore - the trade should have your `user_id`
3. Sign out and create another account
4. The second user should only see their own trades

## 🔍 **Step 6: Authentication Features**

### **6.1 What's Protected**
- ✅ **Dashboard** - Shows only user's trades and metrics
- ✅ **Add Trade** - Automatically links to authenticated user
- ✅ **Calendar View** - Shows only user's trades
- ✅ **Progress Tracker** - User-specific analytics
- ✅ **Journal** - User's trading notes
- ✅ **Profile** - User's account settings

### **6.2 Security Features**
- 🔐 **JWT Token Validation** - Backend verifies Firebase ID tokens
- 🚫 **User Isolation** - Users can only access their own data
- 🛡️ **API Protection** - All endpoints require authentication
- 🔒 **Route Protection** - Unauthenticated users redirected to login

## 🚨 **Troubleshooting**

### **Common Issues**

#### **1. "Firebase: Error (auth/invalid-api-key)"**
- Check your `NEXT_PUBLIC_FIREBASE_API_KEY` in `.env.local`
- Ensure the key matches your Firebase project

#### **2. "Firebase: Error (auth/operation-not-allowed)"**
- Go to Firebase Console → Authentication → Sign-in methods
- Enable Email/Password authentication

#### **3. Backend 401 "Authorization header required"**
- Ensure you're signed in to the frontend
- Check that the backend is running
- Verify Firebase service account key is correct

#### **4. "The database (default) does not exist"**
- Go to Firebase Console → Firestore Database
- Click "Create database"
- Choose "Start in test mode" for development

### **Debug Steps**
1. **Check Browser Console** for frontend errors
2. **Check Backend Terminal** for authentication logs
3. **Verify Environment Variables** are loaded correctly
4. **Check Firebase Console** for authentication attempts

## 📱 **Production Deployment**

### **1. Update Authorized Domains**
1. Go to Firebase Console → Authentication → Settings
2. Add your production domain to authorized domains

### **2. Update Environment Variables**
- Set production Firebase config
- Update `NEXT_PUBLIC_API_BASE_URL` to your production backend

### **3. Security Rules**
- Update Firestore rules for production
- Consider additional security measures

## 🎯 **Next Steps**

After setting up authentication:

1. **Test User Registration/Login** ✅
2. **Verify Data Isolation** ✅
3. **Test All Protected Routes** ✅
4. **Add Password Reset** (optional)
5. **Add Email Verification** (optional)
6. **Add Social Login** (optional)

## 🔗 **Useful Links**

- [Firebase Authentication Docs](https://firebase.google.com/docs/auth)
- [Firebase Admin SDK](https://firebase.google.com/docs/admin)
- [Firestore Security Rules](https://firebase.google.com/docs/firestore/security/get-started)

---

**🎉 Congratulations!** Your TradeTracker app now has secure, user-isolated authentication! 🎉
