# Analytics Events Implementation Summary

This document outlines all the analytics events that have been implemented across the TradeBud trading application.

## Analytics Library

All events are tracked using the Google Analytics utilities in `src/lib/analytics.ts`:

- `trackPageView(url)` - Track page visits
- `trackEvent(action, category, label?, value?)` - Track custom events  
- `trackTradeEvent(action, ticker, pnl?)` - Track trading-specific events
- `trackUserEngagement(action, label?)` - Track user interaction events
- `trackFormSubmission(formName, success)` - Track form completions
- `trackNavigation(from, to)` - Track page navigation

## Events by Page/Component

### 1. Dashboard (`src/components/Dashboard.tsx`)
**Page Views:**
- `trackPageView('/dashboard')` - When dashboard loads
- `trackUserEngagement('dashboard_view')` - Dashboard engagement

**Interactions:**
- `trackEvent('date_filter_applied', 'dashboard', dateRange)` - When date filter applied
- `trackEvent('date_shortcut_used', 'dashboard', shortcutLabel)` - When quick date shortcuts used
- `trackEvent('date_filter_cleared', 'dashboard', 'all_time')` - When filter cleared
- `trackEvent('profit_toggle', 'dashboard', 'gross_pnl|net_pnl')` - When toggling P&L view

### 2. Add Trade Form (`src/components/TradeForm.tsx`)
**Page Views:**
- `trackPageView('/add-trade')` - When form loads

**Form Interactions:**
- `trackEvent('trade_type_toggle', 'trading', 'entry|exit')` - When switching trade types
- `trackEvent('trade_status_toggle', 'trading', 'open|closed')` - When changing trade status

**Form Submissions:**
- `trackTradeEvent('add|exit', ticker, pnl)` - Successful trade submission
- `trackFormSubmission('trade_form', true|false)` - Form completion status
- `trackEvent('trade_submission', 'trading', type_status, shares)` - Detailed submission info
- `trackEvent('trade_submission_error', 'trading', 'form_error')` - Form errors

### 3. Navigation (`src/components/Layout.tsx`)
**Navigation:**
- `trackNavigation(previousPage, currentPage)` - Page-to-page navigation
- `trackUserEngagement('page_navigation', pageName)` - Page access tracking

**UI Interactions:**
- `trackUserEngagement('sidebar_toggle', 'collapse|expand')` - Sidebar state changes
- `trackUserEngagement('logout', 'sidebar')` - Logout action

### 4. Calendar View (`src/components/CalendarView.tsx`)
**Page Views:**
- `trackPageView('/calendar')` - When calendar loads
- `trackUserEngagement('calendar_view')` - Calendar engagement

**Interactions:**
- `trackEvent('calendar_day_click', 'calendar', date, tradeCount)` - Clicking on calendar days
- `trackEvent('calendar_navigation', 'calendar', 'previous_month|next_month')` - Month navigation
- `trackUserEngagement('day_interaction', trades_count)` - Day interaction details

### 5. Journal (`src/components/Journal.tsx`)
**Page Views:**
- `trackPageView('/journal')` - When journal loads
- `trackUserEngagement('journal_view', trades_count)` - Journal access with context

**Interactions:**
- `trackEvent('journal_filter', 'journal', filterType)` - Status filtering
- `trackEvent('journal_edit', 'journal', ticker)` - Edit trade action
- `trackUserEngagement('trade_edit', tradeStatus)` - Edit interaction context

### 6. Profile (`src/components/Profile.tsx`)
**Page Views:**
- `trackPageView('/profile')` - When profile loads

**Form Submissions:**
- `trackFormSubmission('profile_form', true|false)` - Profile update results
- `trackEvent('profile_update', 'profile', 'success|error')` - Update status

### 7. Monthly Returns (`src/components/MonthlyReturns.tsx`)
**Page Views:**
- `trackPageView('/monthly-returns')` - When page loads
- `trackUserEngagement('monthly_returns_view', returns_count)` - Page access with context

### 8. Trades View (`src/components/TradesView.tsx`)
**Page Views:**
- `trackPageView('/trades')` - When trades page loads
- `trackUserEngagement('trades_view', trades_count)` - Page access with context

**Filtering & Search:**
- `trackEvent('trades_search', 'trades', searchLength)` - Search usage
- `trackEvent('trades_filter', 'trades', filterType)` - Status filtering
- `trackUserEngagement('search_usage', 'trades')` - Search engagement
- `trackUserEngagement('filter_change', filter_context)` - Filter usage

**Trade Interactions:**
- `trackEvent('trade_detail_view', 'trades', ticker)` - Viewing trade details
- `trackEvent('trade_edit', 'trades', ticker)` - Editing trades
- `trackUserEngagement('trade_interaction', tradeStatus)` - Trade engagement context
- `trackUserEngagement('edit_action', tradeStatus)` - Edit action context

## Event Categories

### Main Categories:
- **trading** - All trade-related actions (submissions, edits, etc.)
- **dashboard** - Dashboard-specific interactions
- **calendar** - Calendar navigation and interactions  
- **journal** - Journal filtering and editing
- **trades** - Trades page interactions
- **profile** - Profile management
- **user_engagement** - General user interaction patterns
- **form_interaction** - Form submissions and validation

### Event Types:
- **Page Views** - Track which pages users visit most
- **Navigation** - Track user journey through the app
- **Filtering** - Track how users filter and search data
- **Form Usage** - Track form completions and errors
- **Feature Usage** - Track specific feature adoption
- **User Interactions** - Track engagement patterns

## Testing the Events

To test that events are firing correctly:

1. **Browser Console:** Open Developer Tools and check the Network tab for gtag calls
2. **Google Analytics:** Events should appear in real-time reporting
3. **Console Logging:** Add `console.log()` statements in analytics functions temporarily

## Event Data Structure

All events follow this structure:
```javascript
gtag('event', action, {
  event_category: category,
  event_label: label,
  value: value
});
```

## Usage Examples

```javascript
// Page view
trackPageView('/dashboard');

// User interaction
trackUserEngagement('filter_usage', 'date_range');

// Trade action
trackTradeEvent('add', 'AAPL', 150.75);

// Form submission
trackFormSubmission('trade_form', true);

// Custom event
trackEvent('feature_usage', 'dashboard', 'profit_toggle');
```

## Benefits

This analytics implementation provides insights into:
- Most popular pages and features
- User journey and navigation patterns  
- Form completion rates and errors
- Feature adoption and usage patterns
- Trading behavior and patterns
- User engagement and retention metrics
