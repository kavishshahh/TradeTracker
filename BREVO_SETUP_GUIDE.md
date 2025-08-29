# 📧 Brevo Email Setup Guide for TradeTracker

## Why Brevo?
- **Free Tier**: 300 emails/day (vs SendGrid's 100/day)
- **Great Deliverability**: Professional email infrastructure
- **Easy Setup**: Simple API integration
- **No Credit Card Required**: For free tier

## Step-by-Step Setup

### 1. Create Brevo Account
1. Go to [brevo.com](https://www.brevo.com)
2. Click "Sign up free"
3. Fill in your details and verify your email

### 2. Get Your API Key
1. Log into your Brevo dashboard
2. Go to **Settings** → **API Keys**
3. Click **Generate a new API key**
4. Name it "TradeTracker API" 
5. Copy the API key (keep it safe!)

### 3. Verify Your Sender Email
1. In Brevo dashboard, go to **Settings** → **Senders & IP**
2. Click **Add a sender**
3. Add your email (e.g., `noreply@yourdomain.com`)
4. Verify it via the confirmation email

### 4. Configure Your Backend

#### Update your `.env` file in the backend folder:
```bash
# Brevo Email Configuration
BREVO_API_KEY=xkeysib-your-actual-api-key-here
FROM_EMAIL=noreply@yourdomain.com
FROM_NAME=TradeTracker
```

#### Install Dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### 5. Test the Email Functionality

1. Start your backend server:
   ```bash
   cd backend
   python main_firebase.py
   ```

2. Start your frontend:
   ```bash
   npm run dev
   ```

3. Go to your app → Profile → Email Notifications tab
4. Test sending emails to yourself!

## Email Templates Included

### 📧 Welcome Email
- Beautiful onboarding message
- Feature overview and quick start guide
- Call-to-action buttons

### 📈 Trade Reminder
- Motivational message to stay active
- Direct links to add trades
- Performance tracking benefits

### 📊 Weekly Summary
- Personalized trading statistics
- Profit/loss breakdown
- Performance insights

## Usage Examples

### Manual Emails
Users can send test emails from the Profile page to see how they look.

### Automated Emails (Future Enhancement)
You can set up automated triggers:
- Welcome email on user registration
- Weekly summaries every Sunday
- Reminder emails for inactive users

## Troubleshooting

### Common Issues:
1. **"Email not sent"**: Check if BREVO_API_KEY is correctly set
2. **"Invalid sender"**: Verify your FROM_EMAIL in Brevo dashboard
3. **Rate limits**: Free tier allows 300 emails/day

### Need Help?
- Check the Brevo documentation: [developers.brevo.com](https://developers.brevo.com)
- Contact support through your Brevo dashboard

## Next Steps

Once emails are working:
1. **Customize templates**: Edit the HTML in `backend/email_service.py`
2. **Add automation**: Set up scheduled emails using cron jobs
3. **Track engagement**: Use Brevo's analytics to monitor email performance
4. **Upgrade if needed**: Paid plans start at $25/month for higher volumes

---

🎉 **That's it!** Your users can now receive beautiful, professional emails from your TradeTracker app!
