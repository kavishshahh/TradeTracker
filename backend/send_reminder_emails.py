#!/usr/bin/env python3
"""
TradeTracker Reminder Email Script

This script checks for users who haven't logged in for the last 7 days
and sends them a reminder email to encourage them to track their trades.

Usage:
    python send_reminder_emails.py [--days=7] [--dry-run] [--test-email=user@example.com]

Options:
    --days=N        : Check for users inactive for N days (default: 7)
    --dry-run       : Show what would be sent without actually sending emails
    --test-email    : Send test email to specific address only
    --help          : Show this help message
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import argparse
from dotenv import load_dotenv

# Add the current directory to Python path so we can import our modules
sys.path.append(os.path.dirname(__file__))

# Load environment variables
load_dotenv()

# Import after loading env vars
from email_service import email_service
import firebase_admin
from firebase_admin import credentials, firestore, auth

class InactiveUserEmailer:
    def __init__(self):
        self.db = self._initialize_firebase()
        
    def _initialize_firebase(self):
        """Initialize Firebase Admin SDK"""
        try:
            if not firebase_admin._apps:
                # Try to get service account from environment variable first
                service_account_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_JSON')
                
                if service_account_json:
                    try:
                        import json
                        service_account_info = json.loads(service_account_json)
                        cred = credentials.Certificate(service_account_info)
                        firebase_admin.initialize_app(cred)
                        print("✅ Firebase Admin SDK initialized from environment variable")
                    except Exception as e:
                        print(f"❌ Error with environment variable, trying file: {e}")
                        return self._initialize_from_file()
                else:
                    return self._initialize_from_file()
            
            return firestore.client()
            
        except Exception as e:
            print(f"❌ Firebase initialization error: {e}")
            print("📝 Make sure your Firebase credentials are configured properly")
            return None
    
    def _initialize_from_file(self):
        """Initialize Firebase from service account file"""
        try:
            service_account_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH', './firebase-service-account.json')
            
            if os.path.exists(service_account_path):
                cred = credentials.Certificate(service_account_path)
                firebase_admin.initialize_app(cred)
                print("✅ Firebase Admin SDK initialized from file")
                return firestore.client()
            else:
                print(f"❌ Service account file not found: {service_account_path}")
                return None
        except Exception as e:
            print(f"❌ File-based initialization error: {e}")
            return None

    def get_inactive_users(self, days_inactive: int = 7) -> List[Dict]:
        """Get users who haven't logged in for the specified number of days"""
        if not self.db:
            print("❌ Database not available")
            return []
        
        cutoff_date = datetime.now() - timedelta(days=days_inactive)
        inactive_users = []
        
        try:
            # Get all users from Firebase Auth
            print(f"🔍 Checking for users inactive for {days_inactive}+ days...")
            
            # List all users from Firebase Auth
            page = auth.list_users()
            all_users = []
            
            while page:
                all_users.extend(page.users)
                page = page.get_next_page()
            
            print(f"📊 Found {len(all_users)} total users in Firebase Auth")
            
            for user in all_users:
                # Check last sign in time
                last_sign_in = user.user_metadata.last_sign_in_timestamp
                
                if last_sign_in:
                    last_sign_in_date = datetime.fromtimestamp(last_sign_in / 1000)  # Convert from milliseconds
                    
                    if last_sign_in_date < cutoff_date:
                        # Check if user has email
                        if user.email:
                            # Get additional user data from Firestore if available
                            user_data = {
                                'uid': user.uid,
                                'email': user.email,
                                'display_name': user.display_name,
                                'last_sign_in': last_sign_in_date,
                                'days_inactive': (datetime.now() - last_sign_in_date).days,
                                'created_at': datetime.fromtimestamp(user.user_metadata.creation_timestamp / 1000) if user.user_metadata.creation_timestamp else None
                            }
                            
                            # Try to get additional info from Firestore
                            try:
                                user_doc = self.db.collection('users').document(user.uid).get()
                                if user_doc.exists:
                                    firestore_data = user_doc.to_dict()
                                    user_data.update({
                                        'reminder_email_sent': firestore_data.get('reminder_email_sent', False),
                                        'reminder_email_sent_at': firestore_data.get('reminder_email_sent_at'),
                                        'total_trades': firestore_data.get('total_trades', 0)
                                    })
                            except Exception as e:
                                print(f"⚠️ Could not fetch Firestore data for {user.email}: {e}")
                            
                            inactive_users.append(user_data)
                else:
                    # User has never signed in (shouldn't happen for existing users)
                    if user.email:
                        user_data = {
                            'uid': user.uid,
                            'email': user.email,
                            'display_name': user.display_name,
                            'last_sign_in': None,
                            'days_inactive': float('inf'),
                            'created_at': datetime.fromtimestamp(user.user_metadata.creation_timestamp / 1000) if user.user_metadata.creation_timestamp else None,
                            'reminder_email_sent': False
                        }
                        inactive_users.append(user_data)
            
            print(f"📈 Found {len(inactive_users)} users inactive for {days_inactive}+ days")
            return inactive_users
            
        except Exception as e:
            print(f"❌ Error getting inactive users: {e}")
            return []

    def send_reminder_email(self, user_data: Dict, dry_run: bool = False) -> bool:
        """Send reminder email to a specific user"""
        email = user_data['email']
        name = user_data.get('display_name') or email.split('@')[0]
        days_inactive = user_data.get('days_inactive', 7)
        
        if dry_run:
            print(f"🔥 [DRY RUN] Would send reminder email to: {email} ({days_inactive} days inactive)")
            return True
        
        try:
            success = email_service.send_trade_reminder(email, name, days_inactive)
            
            if success:
                # Mark reminder email as sent in Firestore
                if self.db:
                    try:
                        user_ref = self.db.collection('users').document(user_data['uid'])
                        user_ref.set({
                            'reminder_email_sent': True,
                            'reminder_email_sent_at': datetime.now(),
                            'last_reminder_days_inactive': days_inactive
                        }, merge=True)
                        print(f"✅ Reminder email sent to {email} and marked in database")
                    except Exception as e:
                        print(f"⚠️ Email sent but could not update database for {email}: {e}")
                else:
                    print(f"✅ Reminder email sent to {email}")
                
                return True
            else:
                print(f"❌ Failed to send reminder email to {email}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending reminder email to {email}: {e}")
            return False

    def run_reminder_campaign(self, days_inactive: int = 7, dry_run: bool = False, test_email: Optional[str] = None):
        """Run the complete reminder email campaign"""
        print("🚀 Starting TradeTracker Reminder Email Campaign")
        print("=" * 50)
        
        if test_email:
            print(f"🧪 TEST MODE: Sending to {test_email} only")
            # Create fake user data for test
            test_user_data = {
                'uid': 'test',
                'email': test_email,
                'display_name': 'Test User',
                'days_inactive': days_inactive
            }
            
            success = self.send_reminder_email(test_user_data, dry_run)
            if success:
                print(f"✅ Test email sent successfully to {test_email}")
            else:
                print(f"❌ Test email failed for {test_email}")
            return
        
        # Get inactive users
        inactive_users = self.get_inactive_users(days_inactive)
        
        if not inactive_users:
            print("🎉 No inactive users found! Everyone is actively using TradeTracker.")
            return
        
        print(f"\n📊 Summary of inactive users:")
        print("-" * 30)
        
        # Filter users who haven't received reminder emails recently
        users_to_email = []
        for user in inactive_users:
            # Skip if reminder was sent in the last 7 days
            last_reminder = user.get('reminder_email_sent_at')
            if last_reminder:
                if isinstance(last_reminder, str):
                    try:
                        last_reminder = datetime.fromisoformat(last_reminder.replace('Z', '+00:00'))
                    except:
                        last_reminder = None
                
                if last_reminder and (datetime.now() - last_reminder).days < 7:
                    print(f"⏭️  Skipping {user['email']} - reminder sent recently")
                    continue
            
            users_to_email.append(user)
            days = user.get('days_inactive', 'unknown')
            last_sign_in = user.get('last_sign_in', 'Never')
            if isinstance(last_sign_in, datetime):
                last_sign_in = last_sign_in.strftime('%Y-%m-%d')
            
            print(f"📧 {user['email']} - {days} days inactive (last: {last_sign_in})")
        
        if not users_to_email:
            print("\n🎯 All inactive users have received recent reminders. No emails to send.")
            return
        
        print(f"\n📤 Will send reminder emails to {len(users_to_email)} users")
        
        if dry_run:
            print("\n🔥 DRY RUN MODE - No emails will actually be sent")
        else:
            print("\n⚠️  LIVE MODE - Emails will be sent!")
            confirm = input("Do you want to continue? (y/N): ")
            if confirm.lower() != 'y':
                print("❌ Cancelled by user")
                return
        
        # Send emails
        print(f"\n📨 Sending reminder emails...")
        print("-" * 30)
        
        sent_count = 0
        failed_count = 0
        
        for user in users_to_email:
            success = self.send_reminder_email(user, dry_run)
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        # Summary
        print(f"\n📊 Campaign Complete!")
        print("=" * 50)
        print(f"✅ Successfully sent: {sent_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"📧 Total processed: {len(users_to_email)}")
        
        if dry_run:
            print("\n💡 This was a dry run. Use --live to actually send emails.")


def main():
    parser = argparse.ArgumentParser(
        description="Send reminder emails to inactive TradeTracker users",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--days', 
        type=int, 
        default=7, 
        help='Number of days of inactivity to trigger reminder (default: 7)'
    )
    
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Show what would be sent without actually sending emails'
    )
    
    parser.add_argument(
        '--test-email',
        type=str,
        help='Send test email to specific address only'
    )
    
    parser.add_argument(
        '--live',
        action='store_true',
        help='Actually send emails (opposite of --dry-run)'
    )
    
    args = parser.parse_args()
    
    # Default to dry run unless --live is specified
    dry_run = not args.live if not args.dry_run else True
    
    try:
        emailer = InactiveUserEmailer()
        emailer.run_reminder_campaign(
            days_inactive=args.days,
            dry_run=dry_run,
            test_email=args.test_email
        )
        
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
