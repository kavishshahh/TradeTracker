# 📊 TradeTracker Weekly Summary Email System

A script to send personalized weekly trading performance summaries to your users with detailed analytics and insights.

## 🚀 Quick Start

### Windows Users:
```cmd
cd backend
.\venv\scripts\activate
weekly_summary.bat dry
```

### Mac/Linux Users:
```bash
cd backend
.\venv\scripts\activate
./weekly_summary.sh dry
```

### Direct Python:
```bash
cd backend
.\venv\scripts\activate
python send_weekly_summary.py --dry-run
```

## 📋 Available Commands

### 1. **Dry Run** (Safe - No Emails Sent)
See who would receive weekly summaries:

**Windows:**
```cmd
weekly_summary.bat dry
```

**Mac/Linux:**
```bash
./weekly_summary.sh dry
```

**Python:**
```bash
python send_weekly_summary.py --dry-run --active-only
```

### 2. **Test Email**
Send a test weekly summary to yourself:

**Windows:**
```cmd
weekly_summary.bat test your-email@example.com
```

**Mac/Linux:**
```bash
./weekly_summary.sh test your-email@example.com
```

**Python:**
```bash
python send_weekly_summary.py --test-email=your-email@example.com --live
```

### 3. **Send to Active Users**
Send summaries to users who logged in this week:

**Windows:**
```cmd
weekly_summary.bat live
```

**Mac/Linux:**
```bash
./weekly_summary.sh live
```

**Python:**
```bash
python send_weekly_summary.py --live --active-only
```

### 4. **Send to ALL Users**
Send summaries to all users with trades (regardless of recent activity):

**Windows:**
```cmd
weekly_summary.bat all
```

**Mac/Linux:**
```bash
./weekly_summary.sh all
```

**Python:**
```bash
python send_weekly_summary.py --live --all-users
```

## 📊 What's Included in the Summary

### **Performance Metrics**
- 📈 **Total Trades** this week
- 💰 **Profit & Loss** summary
- 🎯 **Win Rate** percentage
- 🏆 **Best Trade** of the week
- 📉 **Worst Trade** of the week
- 📊 **Average Trade Size**

### **Advanced Analytics**
- ⚖️ **Risk/Reward Ratio**
- 📅 **Trading Days** active
- 📈 **Winning vs Losing** trade counts
- 🏷️ **Most Traded Symbols** (top 3)
- 📊 **Week-over-week** comparison

### **Personalized Content**
- 👤 **Personalized greeting** with user's name
- 📈 **Visual performance** charts
- 💡 **Trading insights** and tips
- 🔗 **Direct links** back to the app

## 🎯 User Filtering Logic

### **Active Users Mode** (Default)
- ✅ Users who logged in within the last 7 days
- ✅ Users who made at least 1 trade this week
- ✅ Prevents sending to completely inactive users

### **All Users Mode**
- ✅ Any user with trades this week
- ✅ Includes users who haven't logged in recently
- ✅ Good for re-engagement campaigns

## 📈 Sample Output

```
🚀 Starting TradeTracker Weekly Summary Campaign
==================================================
🔍 Getting users for weekly summary...
📊 Found 156 total users in Firebase Auth
📈 Found 23 users with trading activity this week

📊 Weekly Summary Report:
----------------------------------------
📧 john@example.com
   📊 12 trades | P&L: $485.50 | Win Rate: 66.7%
   🎯 Best: $125.00 | Worst: -$45.00
📧 mary@example.com
   📊 8 trades | P&L: $234.20 | Win Rate: 75.0%
   🎯 Best: $89.50 | Worst: -$23.10
📧 alice@example.com
   📊 15 trades | P&L: -$156.30 | Win Rate: 40.0%
   🎯 Best: $67.80 | Worst: -$89.20

📤 Will send weekly summaries to 23 users
🔥 DRY RUN MODE - No emails will actually be sent

📨 Sending weekly summary emails...
----------------------------------------
🔥 [DRY RUN] Would send weekly summary to: john@example.com
    📊 12 trades, P&L: $485.50
🔥 [DRY RUN] Would send weekly summary to: mary@example.com
    📊 8 trades, P&L: $234.20

📊 Weekly Summary Campaign Complete!
==================================================
✅ Successfully sent: 23
❌ Failed: 0
📧 Total processed: 23

📈 Community Stats This Week:
   📊 Average trades per user: 11.7
   💰 Community total P&L: $3,245.80
   🎯 Most active traders got their summaries!

💡 This was a dry run. Use --live to actually send emails.
```

## 🔧 Advanced Options

### Command Line Arguments:
- `--active-only` - Send only to users who logged in this week (default)
- `--all-users` - Send to all users with trades, regardless of activity
- `--dry-run` - Show what would be sent without sending
- `--live` - Actually send emails
- `--test-email=email@example.com` - Send test summary only

### Examples:

**Dry run for active users:**
```bash
python send_weekly_summary.py --dry-run --active-only
```

**Send to all users with trades:**
```bash
python send_weekly_summary.py --live --all-users
```

**Test with fake data:**
```bash
python send_weekly_summary.py --test-email=me@example.com --live
```

## 📅 Recommended Schedule

### **Weekly Automation** (Recommended)
```bash
# Every Sunday evening or Monday morning:
cd backend
.\venv\scripts\activate
python send_weekly_summary.py --live --active-only
```

### **Monthly All-Users Campaign**
```bash
# First Sunday of each month:
python send_weekly_summary.py --live --all-users
```

### **Before Major Market Events**
```bash
# Before earnings season, FOMC meetings, etc:
python send_weekly_summary.py --live --active-only
```

## 🛡️ Safety Features

### 1. **Smart Filtering**
- ✅ Only sends to users with actual trades
- ✅ Excludes users without email addresses
- ✅ Handles users with no trading activity gracefully

### 2. **Data Validation**
- ✅ Calculates accurate P&L from real trade data
- ✅ Handles missing or corrupt trade data
- ✅ Provides fallback values for incomplete data

### 3. **Error Handling**
- ✅ Continues if individual emails fail
- ✅ Reports detailed success/failure counts
- ✅ Doesn't crash on database connectivity issues

### 4. **Anti-Spam Protection**
- ✅ Tracks when summaries are sent
- ✅ Won't send duplicates for the same week
- ✅ Respects user preferences (future feature)

## 📊 What Users See

### **Email Subject**
```
📊 Your Weekly Trading Summary - Week of Jan 15-22
```

### **Email Content**
- 🎨 **Beautiful HTML design** with charts and colors
- 📈 **Performance highlights** prominently displayed  
- 💡 **Actionable insights** based on their trading patterns
- 🔗 **Call-to-action** buttons to return to the app
- 📱 **Mobile-responsive** design

### **Key Sections**
1. **Personal Greeting** with their name
2. **This Week's Performance** with key metrics
3. **Trade Breakdown** with wins/losses
4. **Top Symbols** they traded
5. **Performance Tips** based on their patterns
6. **Call to Action** to continue trading

## 💡 Pro Tips

### **Timing**
- 📅 **Sunday evenings** work best (users plan their week)
- 🌅 **Monday mornings** are also good (week kickoff)
- ⏰ **Avoid Friday evenings** (users are winding down)

### **Frequency**
- 📆 **Weekly is optimal** for engagement without spam
- 🗓️ **Monthly for inactive users** to re-engage
- 🚫 **Don't send daily** (too frequent)

### **Content Strategy**
- 🎯 **Focus on positive metrics** first
- 💡 **Provide actionable insights** 
- 🏆 **Celebrate wins** prominently
- 📚 **Include learning opportunities**

### **Monitoring**
- 📊 Check **Brevo dashboard** for delivery rates
- 📈 Monitor **app engagement** after sending
- 📧 Track **unsubscribe rates** (should be low)
- 💬 Watch for **user feedback**

## 🔧 Troubleshooting

### **"No users with trading activity found"**
- ✅ Normal if it's been a quiet trading week
- 🔍 Check if users are actually making trades
- 📅 Verify date ranges are correct

### **"Firebase not initialized"**
- ✅ Check your `.env` file has Firebase config
- 📁 Ensure `firebase-service-account.json` exists
- 🔑 Verify Firebase permissions

### **"Email failed to send"**
- ✅ Check Brevo API key is valid
- 📧 Verify sender email is verified in Brevo
- 🔄 Check Brevo account isn't rate limited

### **"Incorrect trade data"**
- ✅ Verify trades collection structure in Firestore
- 🔍 Check trade date formats are consistent
- 💰 Ensure P&L calculations are correct

## 🎯 Customization Ideas

### **Email Templates**
- 🎨 Customize colors to match your brand
- 📊 Add more detailed charts
- 🏆 Include leaderboards or community stats
- 💡 Add educational content links

### **User Segmentation**
- 🥇 Different templates for top performers
- 📈 Special messages for improving traders
- 🆘 Encouragement for struggling traders
- 🆕 Welcome series for new users

### **Advanced Analytics**
- 📈 Week-over-week comparisons
- 🎯 Goal tracking and progress
- 📊 Portfolio allocation insights
- ⚖️ Risk management recommendations

## 🚀 Integration with Other Systems

### **Combine with Reminder Emails**
```bash
# Full weekly email campaign:
python send_weekly_summary.py --live --active-only
python send_reminder_emails.py --live --days=7
```

### **Dashboard Integration**
- 📊 Show summary data in user dashboard
- 🔄 Sync email status with UI
- 📧 Allow users to request summaries on-demand

### **Analytics Tracking**
- 📈 Track email open rates
- 🔗 Monitor click-through to app
- 📊 Measure engagement improvement

---

Ready to engage your users with personalized trading insights! 📊✨

**Quick Start:**
```bash
cd backend
.\venv\scripts\activate
python send_weekly_summary.py --test-email=your-email@example.com --live
```
