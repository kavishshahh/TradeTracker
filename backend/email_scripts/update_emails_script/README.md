# TradeBud Email Scripts

This directory contains email automation scripts for TradeBud using Firebase and Brevo.

## Scripts

### 1. `send_update_emails.py`
Sends update notifications to all TradeBud users about new features and improvements.

**Features:**
- Reads users from Firebase Auth
- Uses existing Brevo email service
- Beautiful HTML email template
- Dry run mode for testing
- Rate limiting and error handling

**Usage:**
```bash
# Dry run (recommended first)
python send_update_emails.py --dry-run

# Send to all users (limit 100)
python send_update_emails.py --live --limit=100

# Send test email
python send_update_emails.py --test-email=user@example.com

# Send to more users
python send_update_emails.py --live --limit=500
```

### 2. `test_update_email.py`
Simple test script to send a single update email.

**Usage:**
```bash
python test_update_email.py
```

### 3. `send_reminder_emails.py`
Sends reminder emails to inactive users (existing script).

## Setup

### 1. Environment Variables
Make sure your `.env` file contains:

```env
# Brevo Configuration
BREVO_API_KEY=your_brevo_api_key_here
FROM_EMAIL=noreply@tradebud.xyz
FROM_NAME=TradeBud

# Firebase Configuration
FIREBASE_SERVICE_ACCOUNT_JSON={"type": "service_account", ...}
# OR
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
```

### 2. Dependencies
Install required packages:

```bash
pip install -r requirements.txt
```

### 3. Firebase Setup
- Ensure Firebase service account is configured
- Make sure Firebase Auth and Firestore are enabled
- Users should have email addresses in Firebase Auth

## Email Content

The update email includes information about these new TradeBud features:

### 🌙 Dark Mode Support
- Complete dark mode implementation
- Toggle from profile settings
- System preference detection

### 📊 Active Trades Management
- Dedicated active trades tab
- Quick exit functionality
- Better position management

### 🗑️ Enhanced Trade Management
- Delete trade functionality
- Improved trade modals
- Better user experience

### 📈 Monthly Returns Tracking
- Account balance tracking
- Enhanced monthly returns tab
- Better performance visualization

## Safety Features

### Dry Run Mode
Always test with dry run first:
```bash
python send_update_emails.py --dry-run
```

### Rate Limiting
- Built-in delays between emails
- Configurable user limits
- Error handling and retry logic

### Test Mode
Test with a single email before sending to all users:
```bash
python send_update_emails.py --test-email=your-email@example.com
```

## Monitoring

### Logs
The scripts provide detailed logging:
- ✅ Successful sends
- ❌ Failed sends
- 📊 Summary statistics
- ⚠️ Warnings and errors

### Brevo Dashboard
Monitor email delivery in your Brevo dashboard:
- Delivery rates
- Open rates
- Click rates
- Bounce handling

## Best Practices

### Before Sending
1. **Test First**: Always use `--test-email` first
2. **Dry Run**: Use `--dry-run` to preview recipients
3. **Small Batches**: Start with `--limit=10` for testing
4. **Check Brevo**: Verify your Brevo account has sufficient credits

### During Sending
1. **Monitor Logs**: Watch for errors and failures
2. **Check Brevo**: Monitor delivery in Brevo dashboard
3. **Rate Limits**: Respect Brevo's sending limits
4. **User Experience**: Consider sending during business hours

### After Sending
1. **Review Results**: Check success/failure rates
2. **Monitor Feedback**: Watch for user responses
3. **Update Database**: Track email delivery status if needed

## Troubleshooting

### Common Issues

1. **Firebase Authentication Error**
   - Check service account configuration
   - Verify Firebase project settings
   - Ensure proper permissions

2. **Brevo API Error**
   - Verify API key is correct
   - Check account credits/limits
   - Ensure sender email is verified

3. **No Users Found**
   - Check Firebase Auth has users
   - Verify users have email addresses
   - Check Firebase permissions

### Debug Mode
Enable detailed logging:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Production Deployment

### Environment
- Use production Firebase project
- Configure production Brevo account
- Set up proper monitoring

### Scaling
- Consider using Brevo's batch sending
- Implement proper queue system
- Add database tracking for delivery status

### Compliance
- Include unsubscribe links
- Follow CAN-SPAM regulations
- Respect user preferences
- Implement opt-out functionality

## Support

For issues or questions:
- Check the logs for detailed error messages
- Verify your Firebase and Brevo configuration
- Test with a single recipient first
- Contact the TradeBud development team
