# 📧 TradeTracker Reminder Email System

A manual script to send reminder emails to users who haven't logged in for a specified number of days.

## 🚀 Quick Start

### Windows Users:
```cmd
cd backend
send_reminders.bat dry
```

### Mac/Linux Users:
```bash
cd backend
./send_reminders.sh dry
```

### Direct Python:
```bash
cd backend
python send_reminder_emails.py --dry-run
```

## 📋 Available Commands

### 1. **Dry Run** (Safe - No Emails Sent)
See who would receive emails without actually sending them:

**Windows:**
```cmd
send_reminders.bat dry
```

**Mac/Linux:**
```bash
./send_reminders.sh dry
```

**Python:**
```bash
python send_reminder_emails.py --dry-run
```

### 2. **Test Email**
Send a test reminder email to yourself:

**Windows:**
```cmd
send_reminders.bat test your-email@example.com
```

**Mac/Linux:**
```bash
./send_reminders.sh test your-email@example.com
```

**Python:**
```bash
python send_reminder_emails.py --test-email=your-email@example.com --live
```

### 3. **Live Campaign**
Actually send reminder emails to inactive users:

**Windows:**
```cmd
send_reminders.bat live
```

**Mac/Linux:**
```bash
./send_reminders.sh live
```

**Python:**
```bash
python send_reminder_emails.py --live
```

### 4. **Custom Inactive Period**
Check for users inactive for different periods:

**7 days (default):**
```bash
python send_reminder_emails.py --dry-run --days=7
```

**14 days:**
```bash
python send_reminder_emails.py --dry-run --days=14
```

**30 days:**
```bash
python send_reminder_emails.py --dry-run --days=30
```

## 🔧 Advanced Options

### Command Line Arguments:
- `--days=N` - Check for users inactive for N days (default: 7)
- `--dry-run` - Show what would be sent without sending
- `--live` - Actually send emails
- `--test-email=email@example.com` - Send test email only

### Examples:

**Check 14-day inactive users:**
```bash
python send_reminder_emails.py --dry-run --days=14
```

**Send reminders to 30-day inactive users:**
```bash
python send_reminder_emails.py --live --days=30
```

## 📊 What the Script Does

### 1. **User Analysis**
- Connects to Firebase Auth to get all users
- Checks last sign-in timestamp for each user
- Identifies users inactive for specified days
- Excludes users who received reminders in the last 7 days

### 2. **Smart Filtering**
- ✅ Only emails users with valid email addresses
- ✅ Skips users who got reminders recently (prevents spam)
- ✅ Tracks email history in Firestore
- ✅ Handles users who never signed in

### 3. **Email Tracking**
- Records when reminder emails are sent
- Stores reminder frequency in user profiles
- Prevents duplicate emails to same user

## 📈 Sample Output

```
🚀 Starting TradeTracker Reminder Email Campaign
==================================================
🔍 Checking for users inactive for 7+ days...
📊 Found 156 total users in Firebase Auth
📈 Found 23 users inactive for 7+ days

📊 Summary of inactive users:
------------------------------
📧 john@example.com - 8 days inactive (last: 2024-01-15)
📧 mary@example.com - 12 days inactive (last: 2024-01-11)
⏭️  Skipping bob@example.com - reminder sent recently
📧 alice@example.com - 15 days inactive (last: 2024-01-08)

📤 Will send reminder emails to 3 users
🔥 DRY RUN MODE - No emails will actually be sent

📨 Sending reminder emails...
------------------------------
🔥 [DRY RUN] Would send reminder email to: john@example.com (8 days inactive)
🔥 [DRY RUN] Would send reminder email to: mary@example.com (12 days inactive)
🔥 [DRY RUN] Would send reminder email to: alice@example.com (15 days inactive)

📊 Campaign Complete!
==================================================
✅ Successfully sent: 3
❌ Failed: 0
📧 Total processed: 3

💡 This was a dry run. Use --live to actually send emails.
```

## 🛡️ Safety Features

### 1. **Dry Run by Default**
- Always run `--dry-run` first to see what would happen
- No accidental email blasts

### 2. **Confirmation Required**
- Live mode asks for confirmation before sending
- Easy to cancel if you change your mind

### 3. **Rate Limiting**
- Won't send reminders to users who got them recently
- Prevents spam complaints

### 4. **Error Handling**
- Continues if individual emails fail
- Reports success/failure counts
- Doesn't crash on Firebase connection issues

## 📅 Recommended Usage Schedule

### **Weekly Maintenance** (Recommended)
```bash
# Every Monday morning:
cd backend
python send_reminder_emails.py --dry-run --days=7    # Check who's inactive
python send_reminder_emails.py --live --days=7       # Send reminders
```

### **Monthly Deep Clean**
```bash
# First Monday of each month:
python send_reminder_emails.py --dry-run --days=30   # Check 30-day inactive
python send_reminder_emails.py --live --days=30      # Re-engage long-term inactive
```

### **Quarterly Win-Back**
```bash
# Every 3 months:
python send_reminder_emails.py --dry-run --days=90   # Find really inactive users
# Consider different email template for these
```

## 🔧 Troubleshooting

### **"Firebase not initialized"**
- Check your `.env` file has `BREVO_API_KEY` and Firebase config
- Ensure `firebase-service-account.json` exists

### **"No inactive users found"**
- Great! All your users are active
- Try different `--days` value (e.g., `--days=3`)

### **"Email failed"**
- Check Brevo API key is valid
- Verify sender email is verified in Brevo dashboard
- Check Brevo account isn't rate limited

### **"Permission denied"**
- Make sure you're in the `backend` directory
- Check Firebase service account has proper permissions

## 💡 Pro Tips

1. **Start with dry runs** - Always test before going live
2. **Use test emails** - Send to yourself first to see how they look  
3. **Monitor Brevo dashboard** - Check delivery rates and bounce rates
4. **Adjust frequency** - Don't send too often (weekly is good)
5. **Customize messages** - Edit the email templates for better engagement

## 🎯 Next Steps

Once you're comfortable with the script, you can:

1. **Customize email templates** in `email_service.py`
2. **Add different reminder types** (e.g., welcome series, win-back campaigns)
3. **Integrate with task scheduler** if you want automation
4. **Add analytics tracking** to measure email effectiveness
5. **Segment users** by activity level for targeted messaging

---

Happy emailing! 📧✨