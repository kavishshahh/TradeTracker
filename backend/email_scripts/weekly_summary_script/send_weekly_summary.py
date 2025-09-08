#!/usr/bin/env python3
"""
TradeTracker Weekly Summary Email Script

This script generates and sends personalized weekly trading summaries to users
with their performance metrics, recent trades, and insights.

Usage:
    python send_weekly_summary.py [--all-users] [--active-only] [--dry-run] [--test-email=user@example.com]

Options:
    --all-users     : Send to all users regardless of activity
    --active-only   : Send only to users who logged in this week (default)
    --dry-run       : Show what would be sent without actually sending emails
    --test-email    : Send test summary to specific address only
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

class WeeklySummaryEmailer:
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

    def get_weekly_trades(self, user_id: str) -> List[Dict]:
        """Get trades from the last 7 days for a user"""
        if not self.db:
            return []
        
        week_ago = datetime.now() - timedelta(days=7)
        week_ago_str = week_ago.strftime('%Y-%m-%d')  # Convert to string format for Firestore comparison
        
        try:
            trades_ref = self.db.collection('trades')
            recent_trades = trades_ref.where('user_id', '==', user_id)\
                                    .where('date', '>=', week_ago_str)\
                                    .order_by('date', direction=firestore.Query.DESCENDING)\
                                    .stream()
            
            trades_list = []
            for trade in recent_trades:
                trade_data = trade.to_dict()
                trade_data['id'] = trade.id
                trades_list.append(trade_data)
            
            return trades_list
            
        except Exception as e:
            print(f"⚠️ Error fetching trades for user {user_id}: {e}")
            return []

    def calculate_user_summary(self, user_id: str, user_email: str) -> Optional[Dict]:
        """Calculate weekly summary statistics for a user"""
        trades = self.get_weekly_trades(user_id)
        
        if not trades:
            return None
        
        # Debug: Print trade details for first user
        if user_email == "kavishshah30@gmail.com":
            print(f"🔍 Debug: Found {len(trades)} trades for {user_email}")
            for i, trade in enumerate(trades[:3]):  # Show first 3 trades
                print(f"  Trade {i+1}: status={trade.get('status')}, buy_price={trade.get('buy_price')}, sell_price={trade.get('sell_price')}, shares={trade.get('shares')}")
        
        # Calculate basic stats
        total_trades = len(trades)
        
        # Calculate P&L for each trade (only for closed trades with both buy and sell prices)
        trade_pnls = []
        for trade in trades:
            if (trade.get('status') == 'closed' and 
                trade.get('buy_price') is not None and 
                trade.get('sell_price') is not None and
                trade.get('shares') is not None):
                pnl = (trade['sell_price'] - trade['buy_price']) * trade['shares']
                trade_pnls.append(pnl)
            else:
                trade_pnls.append(0)
        
        total_pnl = sum(trade_pnls)
        
        # Separate winning and losing trades
        winning_trades = [t for t, pnl in zip(trades, trade_pnls) if pnl > 0]
        losing_trades = [t for t, pnl in zip(trades, trade_pnls) if pnl < 0]
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        # Best and worst trades
        best_trade = max(trade_pnls, default=0)
        worst_trade = min(trade_pnls, default=0)
        
        # Average trade size
        avg_trade_size = total_pnl / total_trades if total_trades > 0 else 0
        
        # Most traded symbols
        symbols = {}
        for trade in trades:
            symbol = trade.get('ticker', 'Unknown')
            symbols[symbol] = symbols.get(symbol, 0) + 1
        
        most_traded = sorted(symbols.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Trading days
        trade_dates = set()
        for trade in trades:
            if 'date' in trade:
                if hasattr(trade['date'], 'date'):
                    trade_dates.add(trade['date'].date())
                else:
                    # Handle different date formats
                    try:
                        if isinstance(trade['date'], str):
                            date_obj = datetime.fromisoformat(trade['date'].replace('Z', '+00:00'))
                            trade_dates.add(date_obj.date())
                    except:
                        pass
        
        trading_days = len(trade_dates)
        
        # Risk metrics
        if len(winning_trades) > 0 and len(losing_trades) > 0:
            winning_pnls = [pnl for t, pnl in zip(trades, trade_pnls) if pnl > 0]
            losing_pnls = [pnl for t, pnl in zip(trades, trade_pnls) if pnl < 0]
            avg_win = sum(winning_pnls) / len(winning_pnls)
            avg_loss = abs(sum(losing_pnls) / len(losing_pnls))
            risk_reward_ratio = avg_win / avg_loss if avg_loss > 0 else 0
        else:
            risk_reward_ratio = 0
        
        return {
            'user_id': user_id,
            'email': user_email,
            'total_trades': total_trades,
            'profit_loss': total_pnl,
            'win_rate': win_rate,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_trade_size': avg_trade_size,
            'winning_trades_count': len(winning_trades),
            'losing_trades_count': len(losing_trades),
            'most_traded_symbols': most_traded,
            'trading_days': trading_days,
            'risk_reward_ratio': risk_reward_ratio,
            'week_start': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
            'week_end': datetime.now().strftime('%Y-%m-%d')
        }

    def get_eligible_users(self, active_only: bool = True) -> List[Dict]:
        """Get users eligible for weekly summary emails"""
        if not self.db:
            print("❌ Database not available")
            return []
        
        try:
            # Get all users from Firebase Auth
            print(f"🔍 Getting users for weekly summary...")
            
            page = auth.list_users()
            all_users = []
            
            while page:
                all_users.extend(page.users)
                page = page.get_next_page()
            
            print(f"📊 Found {len(all_users)} total users in Firebase Auth")
            
            eligible_users = []
            week_ago = datetime.now() - timedelta(days=7)
            
            for user in all_users:
                if not user.email:
                    continue
                
                # Check if user was active this week (if active_only is True)
                if active_only:
                    last_sign_in = user.user_metadata.last_sign_in_timestamp
                    if not last_sign_in:
                        continue
                    
                    last_sign_in_date = datetime.fromtimestamp(last_sign_in / 1000)
                    if last_sign_in_date < week_ago:
                        continue
                
                # Check if user has any trades this week
                summary = self.calculate_user_summary(user.uid, user.email)
                if summary and summary['total_trades'] > 0:
                    summary['display_name'] = user.display_name
                    summary['last_sign_in'] = datetime.fromtimestamp(user.user_metadata.last_sign_in_timestamp / 1000) if user.user_metadata.last_sign_in_timestamp else None
                    eligible_users.append(summary)
            
            print(f"📈 Found {len(eligible_users)} users with trading activity this week")
            return eligible_users
            
        except Exception as e:
            print(f"❌ Error getting eligible users: {e}")
            return []

    def send_weekly_summary_email(self, user_summary: Dict, dry_run: bool = False) -> bool:
        """Send weekly summary email to a specific user"""
        email = user_summary['email']
        name = user_summary.get('display_name') or email.split('@')[0]
        
        if dry_run:
            print(f"🔥 [DRY RUN] Would send weekly summary to: {email}")
            print(f"    📊 {user_summary['total_trades']} trades, P&L: ${user_summary['profit_loss']:.2f}")
            return True
        
        try:
            success = email_service.send_weekly_summary(email, name, user_summary)
            
            if success:
                # Mark weekly summary as sent in Firestore
                if self.db:
                    try:
                        user_ref = self.db.collection('users').document(user_summary['user_id'])
                        user_ref.set({
                            'weekly_summary_sent': True,
                            'weekly_summary_sent_at': datetime.now(),
                            'last_summary_week': user_summary['week_end']
                        }, merge=True)
                        print(f"✅ Weekly summary sent to {email} and marked in database")
                    except Exception as e:
                        print(f"⚠️ Email sent but could not update database for {email}: {e}")
                else:
                    print(f"✅ Weekly summary sent to {email}")
                
                return True
            else:
                print(f"❌ Failed to send weekly summary to {email}")
                return False
                
        except Exception as e:
            print(f"❌ Error sending weekly summary to {email}: {e}")
            return False

    def run_weekly_summary_campaign(self, active_only: bool = True, dry_run: bool = False, test_email: Optional[str] = None):
        """Run the complete weekly summary email campaign"""
        print("🚀 Starting TradeTracker Weekly Summary Campaign")
        print("=" * 50)
        
        if test_email:
            print(f"🧪 TEST MODE: Sending to {test_email} only")
            # Create fake summary data for test
            test_summary = {
                'user_id': 'test',
                'email': test_email,
                'display_name': 'Test User',
                'total_trades': 12,
                'profit_loss': 485.50,
                'win_rate': 66.7,
                'best_trade': 125.00,
                'worst_trade': -45.00,
                'avg_trade_size': 40.46,
                'winning_trades_count': 8,
                'losing_trades_count': 4,
                'most_traded_symbols': [('AAPL', 4), ('TSLA', 3), ('MSFT', 2)],
                'trading_days': 5,
                'risk_reward_ratio': 2.1,
                'week_start': (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'week_end': datetime.now().strftime('%Y-%m-%d')
            }
            
            success = self.send_weekly_summary_email(test_summary, dry_run)
            if success:
                print(f"✅ Test weekly summary sent successfully to {test_email}")
            else:
                print(f"❌ Test weekly summary failed for {test_email}")
            return
        
        # Get eligible users
        eligible_users = self.get_eligible_users(active_only)
        
        if not eligible_users:
            if active_only:
                print("📭 No active users with trades found this week.")
                print("💡 Try --all-users to include inactive users, or users may not have traded this week.")
            else:
                print("📭 No users with trades found this week.")
            return
        
        print(f"\n📊 Weekly Summary Report:")
        print("-" * 40)
        
        for user in eligible_users:
            status = "Active" if active_only else "All Users"
            print(f"📧 {user['email']}")
            print(f"   📊 {user['total_trades']} trades | P&L: ${user['profit_loss']:.2f} | Win Rate: {user['win_rate']:.1f}%")
            print(f"   🎯 Best: ${user['best_trade']:.2f} | Worst: ${user['worst_trade']:.2f}")
        
        print(f"\n📤 Will send weekly summaries to {len(eligible_users)} users")
        
        if dry_run:
            print("\n🔥 DRY RUN MODE - No emails will actually be sent")
        else:
            print("\n⚠️  LIVE MODE - Emails will be sent!")
            confirm = input("Do you want to continue? (y/N): ")
            if confirm.lower() != 'y':
                print("❌ Cancelled by user")
                return
        
        # Send emails
        print(f"\n📨 Sending weekly summary emails...")
        print("-" * 40)
        
        sent_count = 0
        failed_count = 0
        
        for user in eligible_users:
            success = self.send_weekly_summary_email(user, dry_run)
            if success:
                sent_count += 1
            else:
                failed_count += 1
        
        # Summary
        print(f"\n📊 Weekly Summary Campaign Complete!")
        print("=" * 50)
        print(f"✅ Successfully sent: {sent_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"📧 Total processed: {len(eligible_users)}")
        
        if sent_count > 0:
            avg_trades = sum(u['total_trades'] for u in eligible_users) / len(eligible_users)
            total_pnl = sum(u['profit_loss'] for u in eligible_users)
            print(f"\n📈 Community Stats This Week:")
            print(f"   📊 Average trades per user: {avg_trades:.1f}")
            print(f"   💰 Community total P&L: ${total_pnl:.2f}")
            print(f"   🎯 Most active traders got their summaries!")
        
        if dry_run:
            print("\n💡 This was a dry run. Use --live to actually send emails.")


def main():
    parser = argparse.ArgumentParser(
        description="Send weekly trading summary emails to TradeTracker users",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--all-users', 
        action='store_true', 
        help='Send to all users with trades, regardless of recent activity'
    )
    
    parser.add_argument(
        '--active-only', 
        action='store_true', 
        help='Send only to users who logged in this week (default behavior)'
    )
    
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Show what would be sent without actually sending emails'
    )
    
    parser.add_argument(
        '--test-email',
        type=str,
        help='Send test weekly summary to specific address only'
    )
    
    parser.add_argument(
        '--live',
        action='store_true',
        help='Actually send emails (opposite of --dry-run)'
    )
    
    args = parser.parse_args()
    
    # Default to dry run unless --live is specified
    dry_run = not args.live if not args.dry_run else True
    
    # Default to active users only
    active_only = not args.all_users
    
    try:
        emailer = WeeklySummaryEmailer()
        emailer.run_weekly_summary_campaign(
            active_only=active_only,
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
