import { initializeApp } from 'firebase/app';
import { getFirestore } from 'firebase/firestore';

const firebaseConfig = {
  // Add your Firebase config here
  // For now, we'll use mock data until you configure Firebase
  apiKey: "mock-api-key",
  authDomain: "tradetracker-mock.firebaseapp.com",
  projectId: "tradetracker-mock",
  storageBucket: "tradetracker-mock.appspot.com",
  messagingSenderId: "123456789",
  appId: "mock-app-id"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firestore
export const db = getFirestore(app);

export default app;
