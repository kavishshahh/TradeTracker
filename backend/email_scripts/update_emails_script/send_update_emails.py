#!/usr/bin/env python3
"""
TradeBud Update Email Script

This script reads users from Firebase and sends update notifications about new features
using the existing Brevo email service.

Usage:
    python send_update_emails.py [--dry-run] [--test-email=user@example.com] [--limit=100]

Options:
    --dry-run       : Show what would be sent without actually sending emails
    --test-email    : Send test email to specific address only
    --limit         : Limit number of users to process (default: 100)
    --help          : Show this help message
"""

import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
import argparse
from dotenv import load_dotenv

# Add the backend directory to Python path so we can import our modules
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(backend_dir)

# Load environment variables
load_dotenv()

# Import after loading env vars
from email_service import email_service
import firebase_admin
from firebase_admin import credentials, firestore, auth

class UpdateEmailSender:
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

    def get_all_users(self, limit: int = 100) -> List[Dict]:
        """Get all users from Firebase Auth"""
        if not self.db:
            print("❌ Database not available")
            return []
        
        users = []
        
        try:
            print(f"🔍 Fetching users from Firebase Auth (limit: {limit})...")
            
            # List all users from Firebase Auth
            page = auth.list_users()
            all_users = []
            
            while page and len(all_users) < limit:
                remaining = limit - len(all_users)
                users_to_add = page.users[:remaining]
                all_users.extend(users_to_add)
                page = page.get_next_page()
            
            print(f"📊 Found {len(all_users)} users in Firebase Auth")
            
            for user in all_users:
                if user.email:
                    # Get additional user data from Firestore if available
                    user_data = {
                        'uid': user.uid,
                        'email': user.email,
                        'display_name': user.display_name or user.email.split('@')[0],
                        'created_at': datetime.fromtimestamp(user.user_metadata.creation_timestamp / 1000) if user.user_metadata.creation_timestamp else None,
                        'last_sign_in': datetime.fromtimestamp(user.user_metadata.last_sign_in_timestamp / 1000) if user.user_metadata.last_sign_in_timestamp else None
                    }
                    
                    # Try to get additional info from Firestore
                    try:
                        user_doc = self.db.collection('users').document(user.uid).get()
                        if user_doc.exists:
                            firestore_data = user_doc.to_dict()
                            user_data.update({
                                'total_trades': firestore_data.get('total_trades', 0),
                                'last_activity': firestore_data.get('last_activity'),
                                'profile_data': firestore_data.get('profile', {})
                            })
                    except Exception as e:
                        print(f"⚠️ Could not fetch Firestore data for {user.email}: {e}")
                    
                    users.append(user_data)
            
            print(f"📈 Processed {len(users)} users with email addresses")
            return users
            
        except Exception as e:
            print(f"❌ Error getting users: {e}")
            return []

    def create_update_email_content(self, user_name: str) -> Dict[str, str]:
        """Create email content for TradeBud updates"""
        
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # HTML content
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>TradeBud Updates - {current_date}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                }}
                .container {{
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 28px;
                    font-weight: 300;
                }}
                .header p {{
                    margin: 10px 0 0 0;
                    opacity: 0.9;
                    font-size: 16px;
                }}
                .content {{
                    padding: 30px;
                }}
                .greeting {{
                    font-size: 18px;
                    margin-bottom: 20px;
                    color: #2c3e50;
                }}
                .update-section {{
                    margin-bottom: 30px;
                }}
                .update-title {{
                    font-size: 20px;
                    color: #2c3e50;
                    margin-bottom: 15px;
                    border-left: 4px solid #667eea;
                    padding-left: 15px;
                }}
                .feature-list {{
                    list-style: none;
                    padding: 0;
                }}
                .feature-item {{
                    background-color: #f8f9fa;
                    margin: 10px 0;
                    padding: 15px;
                    border-radius: 8px;
                    border-left: 4px solid #28a745;
                }}
                .feature-title {{
                    font-weight: bold;
                    color: #2c3e50;
                    margin-bottom: 5px;
                    font-size: 16px;
                }}
                .feature-description {{
                    color: #6c757d;
                    font-size: 14px;
                }}
                .highlight {{
                    background-color: #e3f2fd;
                    padding: 15px;
                    border-radius: 8px;
                    border-left: 4px solid #2196f3;
                    margin: 20px 0;
                }}
                .cta-button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 12px 30px;
                    text-decoration: none;
                    border-radius: 25px;
                    font-weight: bold;
                    margin: 20px 0;
                    transition: transform 0.2s;
                }}
                .cta-button:hover {{
                    transform: translateY(-2px);
                }}
                .footer {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    text-align: center;
                    color: #6c757d;
                    font-size: 14px;
                }}
                .version-badge {{
                    background-color: #28a745;
                    color: white;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: bold;
                    display: inline-block;
                    margin-left: 10px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 TradeBud Updates</h1>
                    <p>New features and improvements to enhance your trading experience</p>
                    <span class="version-badge">v2.0.0</span>
                </div>
                
                <div class="content">
                    <div class="greeting">
                        Hello {user_name}! 👋
                    </div>
                    
                    <p>We're excited to share some amazing new features and improvements that we've added to TradeBud. These updates will make your trading analysis more efficient and your experience more enjoyable.</p>
                    
                    <div class="highlight">
                        <strong>🎉 What's New in TradeBud v2.0.0</strong><br>
                        We've been working hard to bring you these exciting new features and improvements!
                    </div>
                    
                    <div class="update-section">
                        <h2 class="update-title">🌙 Dark Mode Support</h2>
                        <ul class="feature-list">
                            <li class="feature-item">
                                <div class="feature-title">Complete Dark Mode Implementation</div>
                                <div class="feature-description">
                                    Toggle between light and dark themes from your profile settings. 
                                    All components now support dark mode with carefully designed color schemes 
                                    that reduce eye strain during extended trading sessions.
                                </div>
                            </li>
                            <li class="feature-item">
                                <div class="feature-title">System Preference Detection</div>
                                <div class="feature-description">
                                    TradeBud automatically detects your system's theme preference 
                                    and applies it on first visit, with the option to override in settings.
                                </div>
                            </li>
                        </ul>
                    </div>
                    
                    <div class="update-section">
                        <h2 class="update-title">📊 Active Trades Management</h2>
                        <ul class="feature-list">
                            <li class="feature-item">
                                <div class="feature-title">Dedicated Active Trades Tab</div>
                                <div class="feature-description">
                                    View and manage all your open positions in a separate, 
                                    organized tab for better focus on current trading activity.
                                </div>
                            </li>
                            <li class="feature-item">
                                <div class="feature-title">Quick Exit Functionality</div>
                                <div class="feature-description">
                                    Easily exit trades with pre-configured percentage options 
                                    (25%, 50%, 75%, 100%) for quick position management.
                                </div>
                            </li>
                        </ul>
                    </div>
                    
                    <div class="update-section">
                        <h2 class="update-title">🗑️ Enhanced Trade Management</h2>
                        <ul class="feature-list">
                            <li class="feature-item">
                                <div class="feature-title">Delete Trade Functionality</div>
                                <div class="feature-description">
                                    Remove incorrect or duplicate trades from your portfolio 
                                    with a simple delete option and confirmation dialog.
                                </div>
                            </li>
                            <li class="feature-item">
                                <div class="feature-title">Improved Trade Modals</div>
                                <div class="feature-description">
                                    Enhanced edit and delete modals with better user experience 
                                    and dark mode support for all interactions.
                                </div>
                            </li>
                        </ul>
                    </div>
                    
                    <div class="update-section">
                        <h2 class="update-title">📈 Monthly Returns Tracking</h2>
                        <ul class="feature-list">
                            <li class="feature-item">
                                <div class="feature-title">Account Balance Tracking</div>
                                <div class="feature-description">
                                    Add your monthly account start and end balances in profile settings 
                                    to enable comprehensive monthly returns analysis.
                                </div>
                            </li>
                            <li class="feature-item">
                                <div class="feature-title">Enhanced Monthly Returns Tab</div>
                                <div class="feature-description">
                                    Visualize your monthly performance with improved charts, 
                                    detailed breakdowns, and better data organization.
                                </div>
                            </li>
                        </ul>
                    </div>
                    
                    <div class="highlight">
                        <strong>💡 Pro Tip:</strong> Make sure to update your profile settings with your 
                        monthly account balances to get the most out of the new monthly returns features!
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://app.tradebud.xyz" class="cta-button">
                            Explore New Features →
                        </a>
                    </div>
                    
                    <p>We hope you enjoy these new features! As always, we're committed to continuously 
                    improving TradeBud based on your feedback and needs.</p>
                    
                    <p>If you have any questions or suggestions, please don't hesitate to reach out to us at kavishshah30@gmail.com.</p>
                    
                    <p>Happy Trading! 📈</p>
                    
                    <p><strong>The TradeBud Team</strong></p>
                </div>
                
                <div class="footer">
                    <p>© 2024 TradeBud. All rights reserved.</p>
                    <p>You received this email because you're a registered TradeBud user.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text content
        text_content = f"""
TRADEBUD UPDATES - {current_date}
=====================================

Hello {user_name}!

We're excited to share some amazing new features and improvements that we've added to TradeBud. These updates will make your trading analysis more efficient and your experience more enjoyable.

WHAT'S NEW IN TRADEBUD V2.0.0
==============================

🌙 DARK MODE SUPPORT
- Complete Dark Mode Implementation: Toggle between light and dark themes from your profile settings. All components now support dark mode with carefully designed color schemes that reduce eye strain during extended trading sessions.
- System Preference Detection: TradeBud automatically detects your system's theme preference and applies it on first visit, with the option to override in settings.

📊 ACTIVE TRADES MANAGEMENT
- Dedicated Active Trades Tab: View and manage all your open positions in a separate, organized tab for better focus on current trading activity.
- Quick Exit Functionality: Easily exit trades with pre-configured percentage options (25%, 50%, 75%, 100%) for quick position management.

🗑️ ENHANCED TRADE MANAGEMENT
- Delete Trade Functionality: Remove incorrect or duplicate trades from your portfolio with a simple delete option and confirmation dialog.
- Improved Trade Modals: Enhanced edit and delete modals with better user experience and dark mode support for all interactions.

📈 MONTHLY RETURNS TRACKING
- Account Balance Tracking: Add your monthly account start and end balances in profile settings to enable comprehensive monthly returns analysis.
- Enhanced Monthly Returns Tab: Visualize your monthly performance with improved charts, detailed breakdowns, and better data organization.

💡 PRO TIP: Make sure to update your profile settings with your monthly account balances to get the most out of the new monthly returns features!

Explore the new features at: https://tradebud.xyz

We hope you enjoy these new features! As always, we're committed to continuously improving TradeBud based on your feedback and needs.

If you have any questions or suggestions, please don't hesitate to reach out to us.

Happy Trading! 📈

The TradeBud Team

---
© 2024 TradeBud. All rights reserved.
You received this email because you're a registered TradeBud user.
        """
        
        return {
            'html': html_content,
            'text': text_content
        }

    def send_update_email(self, user_data: Dict, dry_run: bool = False) -> bool:
        """Send update email to a specific user"""
        email = user_data['email']
        name = user_data.get('display_name', email.split('@')[0])
        
        if dry_run:
            print(f"🔥 [DRY RUN] Would send update email to: {email} ({name})")
            return True
        
        try:
            # Create email content
            content = self.create_update_email_content(name)
            
            # Send email using existing Brevo service
            success = email_service.send_email(
                to_email=email,
                subject=f"🚀 TradeBud Updates - {datetime.now().strftime('%B %d, %Y')}",
                html_content=content['html'],
                plain_content=content['text']
            )
            
            if success:
                print(f"✅ Update email sent to {email}")
                return True
            else:
                print(f"❌ Failed to send update email to {email}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending update email to {email}: {e}")
            return False

    def run_update_campaign(self, dry_run: bool = False, test_email: Optional[str] = None, limit: int = 100):
        """Run the complete update email campaign"""
        print("🚀 Starting TradeBud Update Email Campaign")
        print("=" * 50)
        
        if test_email:
            print(f"🧪 TEST MODE: Sending to {test_email} only")
            # Create fake user data for test
            test_user_data = {
                'uid': 'test',
                'email': test_email,
                'display_name': 'Test User'
            }
            
            success = self.send_update_email(test_user_data, dry_run)
            if success:
                print(f"✅ Test email sent successfully to {test_email}")
            else:
                print(f"❌ Test email failed for {test_email}")
            return
        
        # Get all users
        users = self.get_all_users(limit)
        
        if not users:
            print("🎉 No users found in Firebase!")
            return
        
        print(f"\n📊 Summary of users to email:")
        print("-" * 30)
        
        for user in users[:10]:  # Show first 10
            print(f"📧 {user['email']} - {user['display_name']}")
        
        if len(users) > 10:
            print(f"... and {len(users) - 10} more users")
        
        print(f"\n📤 Will send update emails to {len(users)} users")
        
        if dry_run:
            print("\n🔥 DRY RUN MODE - No emails will actually be sent")
        else:
            print("\n⚠️  LIVE MODE - Emails will be sent!")
            confirm = input("Do you want to continue? (y/N): ")
            if confirm.lower() != 'y':
                print("❌ Cancelled by user")
                return
        
        # Send emails
        print(f"\n📨 Sending update emails...")
        print("-" * 30)
        
        sent_count = 0
        failed_count = 0
        
        for i, user in enumerate(users, 1):
            print(f"[{i}/{len(users)}] Processing {user['email']}...")
            success = self.send_update_email(user, dry_run)
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        # Summary
        print(f"\n📊 Campaign Complete!")
        print("=" * 50)
        print(f"✅ Successfully sent: {sent_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"📧 Total processed: {len(users)}")
        
        if dry_run:
            print("\n💡 This was a dry run. Use --live to actually send emails.")


def main():
    parser = argparse.ArgumentParser(
        description="Send update emails to TradeBud users about new features",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
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
    
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Limit number of users to process (default: 100)'
    )
    
    args = parser.parse_args()
    
    # Default to dry run unless --live is specified
    dry_run = not args.live if not args.dry_run else True
    
    try:
        sender = UpdateEmailSender()
        sender.run_update_campaign(
            dry_run=dry_run,
            test_email=args.test_email,
            limit=args.limit
        )
        
    except KeyboardInterrupt:
        print("\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
