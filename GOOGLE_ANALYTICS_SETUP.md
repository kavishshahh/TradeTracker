# Google Analytics Setup Guide

This guide will help you set up Google Analytics 4 (GA4) for your TradeBud application.

## Step 1: Create a Google Analytics Account

1. Go to [Google Analytics](https://analytics.google.com/)
2. Click "Start measuring"
3. Follow the setup wizard to create your account and property
4. Choose "Web" as your platform
5. Enter your website details (TradeBud trading journal)

## Step 2: Get Your Measurement ID

1. After creating your property, you'll get a Measurement ID
2. It will look like: `G-XXXXXXXXXX`
3. Copy this ID - you'll need it for the next step

## Step 3: Configure Environment Variables

1. Copy `.env.local.example` to `.env.local`
2. Add your Google Analytics Measurement ID:
   ```
   NEXT_PUBLIC_GA_MEASUREMENT_ID=G-XXXXXXXXXX
   ```
3. Replace `G-XXXXXXXXXX` with your actual Measurement ID

## Step 4: Verify Installation

1. Start your development server
2. Open your browser's Developer Tools
3. Go to the Network tab
4. Look for requests to `googletagmanager.com`
5. You should see the Google Analytics script loading

## Step 5: Test Tracking

1. Open your application
2. Navigate between different pages
3. Check your Google Analytics Real-Time reports
4. You should see page views and user activity

## Available Tracking Functions

The application includes several tracking functions you can use:

### Basic Event Tracking
```typescript
import { trackEvent } from '@/lib/analytics';

// Track a custom event
trackEvent('button_click', 'ui_interaction', 'add_trade_button');
```

### Trading-Specific Events
```typescript
import { trackTradeEvent } from '@/lib/analytics';

// Track trade actions
trackTradeEvent('add', 'AAPL');
trackTradeEvent('exit', 'TSLA', 150.50); // With P&L
```

### Form Tracking
```typescript
import { trackFormSubmission } from '@/lib/analytics';

// Track form submissions
trackFormSubmission('trade_form', true); // Success
trackFormSubmission('login_form', false); // Error
```

### User Engagement
```typescript
import { trackUserEngagement } from '@/lib/analytics';

// Track user actions
trackUserEngagement('calendar_open', 'date_range_selector');
trackUserEngagement('chart_view', 'equity_curve');
```

## What Gets Tracked Automatically

- **Page Views**: All page navigation is automatically tracked
- **User Sessions**: Session duration and engagement
- **Traffic Sources**: Where users come from
- **Device Information**: Browser, device type, etc.
- **Geographic Data**: User location (country/region level)

## Privacy Considerations

- No personally identifiable information (PII) is collected
- IP addresses are anonymized by Google
- Users can opt-out using browser extensions or ad blockers
- Complies with GDPR and other privacy regulations

## Troubleshooting

### Analytics Not Working?
1. Check your Measurement ID is correct
2. Verify the environment variable is set
3. Check browser console for errors
4. Ensure no ad blockers are interfering

### No Data in Reports?
1. Wait 24-48 hours for data to appear
2. Check Real-Time reports for immediate feedback
3. Verify your property settings in Google Analytics
4. Check if your website is receiving traffic

## Additional Configuration

### Custom Dimensions (Optional)
You can add custom dimensions in Google Analytics for:
- User trading experience level
- Account size ranges
- Trading strategy types
- Risk tolerance levels

### Enhanced Ecommerce (Optional)
For advanced trading analytics, consider setting up:
- Trade entry/exit tracking
- Position sizing metrics
- Risk management tracking
- Performance attribution

## Support

If you need help with Google Analytics setup:
1. Check [Google Analytics Help Center](https://support.google.com/analytics/)
2. Review [GA4 Implementation Guide](https://developers.google.com/analytics/devguides/collection/ga4)
3. Contact your development team for technical issues
