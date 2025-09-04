#!/usr/bin/env python3
"""
Test script to send a single TradeBud update email
"""

import os
import sys
from dotenv import load_dotenv

# Add the backend directory to Python path so we can import our modules
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(backend_dir)

# Load environment variables
load_dotenv()

from send_update_emails import UpdateEmailSender

def test_single_email():
    """Send a test email to verify the setup"""
    
    # Test recipient
    test_email = input("Enter test email address: ").strip()
    test_name = input("Enter test recipient name (or press Enter for default): ").strip() or "Test User"
    
    if not test_email:
        print("❌ No email address provided. Exiting.")
        return
    
    print(f"📧 Sending test update email to: {test_email}")
    print(f"👤 Recipient name: {test_name}")
    print()
    
    # Create email sender
    sender = UpdateEmailSender()
    
    # Send test email
    try:
        test_user_data = {
            'uid': 'test',
            'email': test_email,
            'display_name': test_name
        }
        
        success = sender.send_update_email(test_user_data, dry_run=False)
        
        if success:
            print("✅ Test update email sent successfully!")
            print("📬 Check the recipient's inbox (and spam folder)")
        else:
            print("❌ Failed to send test email")
            print("🔍 Check your Brevo configuration and credentials")
            
    except Exception as e:
        print(f"❌ Error sending test email: {str(e)}")
        print("🔍 Common issues:")
        print("   - Incorrect Brevo API key")
        print("   - Firebase credentials not configured")
        print("   - Network connectivity")

if __name__ == "__main__":
    test_single_email()
