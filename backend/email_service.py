"""
Email service for TradeTracker using Brevo (formerly Sendinblue)
"""
import os
import sib_api_v3_sdk
from sib_api_v3_sdk.rest import ApiException
from typing import List, Optional
import logging
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        # Debug: Check if .env file exists and load it manually if needed
        env_path = os.path.join(os.path.dirname(__file__), '.env')
        
        # Load environment variables again to be safe
        from dotenv import load_dotenv
        load_dotenv(env_path)
        
        self.api_key = os.getenv('BREVO_API_KEY')
        self.from_email = os.getenv('FROM_EMAIL', 'noreply@tradebud.xyz')
        self.from_name = os.getenv('FROM_NAME', 'TradeTracker')
        
        # Debug output
        if self.api_key:
            logger.info(f"API key starts with: {self.api_key[:10]}...")
        
        if not self.api_key or self.api_key == 'your_brevo_api_key_here':
            logger.error("❌ BREVO_API_KEY not configured properly")
            self.api_instance = None
        else:
            try:
                # Configure Brevo API client
                configuration = sib_api_v3_sdk.Configuration()
                configuration.api_key['api-key'] = self.api_key
                self.api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
                    sib_api_v3_sdk.ApiClient(configuration)
                )
                
                # Test API key validity by getting account info
                account_api = sib_api_v3_sdk.AccountApi(sib_api_v3_sdk.ApiClient(configuration))
                try:
                    account_info = account_api.get_account()
                    logger.info(f"✅ Brevo API key valid - Account: {account_info.email}")
                    logger.info("✅ Brevo API initialized successfully")
                except Exception as test_error:
                    logger.error(f"❌ API key validation failed: {test_error}")
                    logger.error("🔑 Please check your BREVO_API_KEY in the .env file")
                    logger.error("📋 Steps to fix:")
                    logger.error("   1. Go to app.brevo.com → Settings → API Keys")
                    logger.error("   2. Create a new API key with 'Send transactional emails' permission")
                    logger.error("   3. Copy the FULL key (starts with xkeysib-)")
                    logger.error("   4. Update your .env file")
                    self.api_instance = None
                    return
                    
            except Exception as e:
                logger.error(f"❌ Failed to initialize Brevo API: {e}")
                self.api_instance = None
    
    def send_email(self, to_email: str, subject: str, html_content: str, plain_content: str = None) -> bool:
        """Send an email using Brevo"""
        if not self.api_instance:
            logger.error("Brevo not initialized. Cannot send email.")
            return False
        
        try:
            if not plain_content:
                # Generate plain text from HTML if not provided
                plain_content = re.sub('<[^<]+?>', '', html_content)
                # Clean up extra whitespace
                plain_content = re.sub(r'\s+', ' ', plain_content).strip()
            
            # Create email object
            send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
                to=[{"email": to_email}],
                sender={"name": self.from_name, "email": self.from_email},
                subject=subject,
                html_content=html_content,
                text_content=plain_content
            )
            
            # Send the email
            api_response = self.api_instance.send_transac_email(send_smtp_email)
            logger.info(f"Email sent successfully to {to_email}. Message ID: {api_response.message_id}")
            return True
            
        except ApiException as e:
            logger.error(f"Brevo API error when sending email to {to_email}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {str(e)}")
            return False
    
    def send_welcome_email(self, user_email: str, user_name: str = None) -> bool:
        """Send welcome email to new users"""
        display_name = user_name or user_email.split('@')[0]
        
        subject = "🎉 Welcome to TradeTracker!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Welcome to TradeTracker</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f8fafc; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 40px 30px; }}
                .footer {{ background-color: #f8fafc; padding: 20px 30px; text-align: center; border-radius: 0 0 8px 8px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 6px; font-weight: bold; }}
                .stats {{ background-color: #f8fafc; padding: 20px; border-radius: 6px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">📈 Welcome to TradeTracker!</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Your trading journey starts here</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2d3748; margin-top: 0;">Hey {display_name}! 👋</h2>
                    
                    <p style="color: #4a5568; line-height: 1.6;">
                        Welcome to TradeTracker - your personal trading companion! We're excited to help you track, analyze, and improve your trading performance.
                    </p>
                    
                    <div class="stats">
                        <h3 style="color: #2d3748; margin-top: 0;">🚀 What you can do with TradeTracker:</h3>
                        <ul style="color: #4a5568; line-height: 1.8;">
                            <li>📊 Track all your trades in one place</li>
                            <li>📈 Analyze your performance with detailed charts</li>
                            <li>💡 Get insights into your trading patterns</li>
                            <li>📱 Access your portfolio anywhere, anytime</li>
                            <li>🎯 Set and monitor your trading goals</li>
                        </ul>
                    </div>
                    
                    <p style="color: #4a5568; line-height: 1.6;">
                        Ready to get started? Log your first trade and begin building your trading history!
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://app.tradebud.xyz/add-trade" class="button">Add Your First Trade</a>
                    </div>
                    
                    <p style="color: #718096; font-size: 14px; line-height: 1.6;">
                        <strong>Pro tip:</strong> The more consistently you track your trades, the better insights you'll get about your trading performance!
                    </p>
                </div>
                
                <div class="footer">
                    <p style="color: #718096; font-size: 12px; margin: 0;">
                        Happy Trading! 🎯<br>
                        The TradeTracker Team
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(user_email, subject, html_content)
    
    def send_trade_reminder(self, user_email: str, user_name: str = None, days_inactive: int = 7) -> bool:
        """Send reminder to add trades"""
        display_name = user_name or user_email.split('@')[0]
        
        subject = f"📈 Don't forget to track your trades!"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Track Your Trades</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f8fafc; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #48bb78 0%, #38a169 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 40px 30px; }}
                .footer {{ background-color: #f8fafc; padding: 20px 30px; text-align: center; border-radius: 0 0 8px 8px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #48bb78 0%, #38a169 100%); color: white; text-decoration: none; border-radius: 6px; font-weight: bold; }}
                .highlight {{ background-color: #edf2f7; padding: 20px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #48bb78; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">📊 Time to Update Your Portfolio!</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Stay on top of your trading game</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2d3748; margin-top: 0;">Hey {display_name}! 👋</h2>
                    
                    <p style="color: #4a5568; line-height: 1.6;">
                        We noticed it's been a while since you last updated your trading portfolio. Consistent tracking is key to understanding your performance and improving your trading strategy!
                    </p>
                    
                    <div class="highlight">
                        <h3 style="color: #2d3748; margin-top: 0;">⏰ Quick Reminder:</h3>
                        <p style="color: #4a5568; margin-bottom: 0;">
                            It's been <strong>{days_inactive} days</strong> since your last trade entry. Even if you haven't made any new trades, logging your current positions helps maintain accurate portfolio tracking.
                        </p>
                    </div>
                    
                    <p style="color: #4a5568; line-height: 1.6;">
                        <strong>Why consistent tracking matters:</strong>
                    </p>
                    <ul style="color: #4a5568; line-height: 1.8;">
                        <li>📈 Better insights into your trading patterns</li>
                        <li>💰 Accurate profit/loss calculations</li>
                        <li>🎯 Track progress toward your goals</li>
                        <li>📊 Identify what strategies work best</li>
                    </ul>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://app.tradebud.xyz/add-trade" class="button">Add Trade Now</a>
                    </div>
                    
                    <p style="color: #718096; font-size: 14px; line-height: 1.6;">
                        <strong>Tip:</strong> Set aside 5 minutes each day to update your trades. Your future self will thank you!
                    </p>
                </div>
                
                <div class="footer">
                    <p style="color: #718096; font-size: 12px; margin: 0;">
                        Keep trading smart! 💪<br>
                        The TradeTracker Team
                    </p>
                    <p style="color: #a0aec0; font-size: 10px; margin: 10px 0 0 0;">
                        Don't want these reminders? <a href="#" style="color: #a0aec0;">Unsubscribe here</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(user_email, subject, html_content)
    
    def send_weekly_summary(self, user_email: str, user_name: str = None, summary_data: dict = None) -> bool:
        """Send weekly trading summary"""
        display_name = user_name or user_email.split('@')[0]
        
        # Default summary data if none provided
        if not summary_data:
            summary_data = {
                'total_trades': 0,
                'profit_loss': 0,
                'win_rate': 0,
                'best_trade': 0,
                'worst_trade': 0
            }
        
        subject = f"📊 Your Weekly Trading Summary"
        
        profit_color = "#48bb78" if summary_data.get('profit_loss', 0) >= 0 else "#f56565"
        profit_symbol = "+" if summary_data.get('profit_loss', 0) >= 0 else ""
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Weekly Trading Summary</title>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 0; background-color: #f8fafc; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ padding: 40px 30px; }}
                .footer {{ background-color: #f8fafc; padding: 20px 30px; text-align: center; border-radius: 0 0 8px 8px; }}
                .button {{ display: inline-block; padding: 12px 24px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 6px; font-weight: bold; }}
                .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
                .stat-card {{ background-color: #f8fafc; padding: 20px; border-radius: 6px; text-align: center; }}
                .stat-value {{ font-size: 24px; font-weight: bold; margin-bottom: 5px; }}
                .stat-label {{ color: #718096; font-size: 14px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin: 0; font-size: 28px;">📊 Your Weekly Summary</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Week of {datetime.now().strftime('%B %d, %Y')}</p>
                </div>
                
                <div class="content">
                    <h2 style="color: #2d3748; margin-top: 0;">Hey {display_name}! 👋</h2>
                    
                    <p style="color: #4a5568; line-height: 1.6;">
                        Here's your trading summary for this week. Keep up the great work!
                    </p>
                    
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value" style="color: #2d3748;">{summary_data.get('total_trades', 0)}</div>
                            <div class="stat-label">Total Trades</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" style="color: {profit_color};">{profit_symbol}${summary_data.get('profit_loss', 0):,.2f}</div>
                            <div class="stat-label">P&L</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" style="color: #2d3748;">{summary_data.get('win_rate', 0):.1f}%</div>
                            <div class="stat-label">Win Rate</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value" style="color: #48bb78;">${summary_data.get('best_trade', 0):,.2f}</div>
                            <div class="stat-label">Best Trade</div>
                        </div>
                    </div>
                    
                    <p style="color: #4a5568; line-height: 1.6;">
                        Want to dive deeper into your performance? Check out your full dashboard for detailed analytics and insights.
                    </p>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://app.tradebud.xyz/" class="button">View Full Dashboard</a>
                    </div>
                    
                    <p style="color: #718096; font-size: 14px; line-height: 1.6;">
                        <strong>Keep it up!</strong> Consistent tracking and analysis are the keys to trading success. 📈
                    </p>
                </div>
                
                <div class="footer">
                    <p style="color: #718096; font-size: 12px; margin: 0;">
                        Happy Trading! 🎯<br>
                        The TradeTracker Team
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return self.send_email(user_email, subject, html_content)

# Global email service instance
email_service = EmailService()
