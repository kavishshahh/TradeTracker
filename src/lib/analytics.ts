// Google Analytics utility functions

declare global {
  interface Window {
    gtag: (
      command: 'config' | 'event' | 'js',
      targetId: string,
      config?: Record<string, any>
    ) => void;
  }
}

// Track page views
export const trackPageView = (url: string) => {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('config', process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID!, {
      page_path: url,
    });
  }
};

// Track custom events
export const trackEvent = (
  action: string,
  category: string,
  label?: string,
  value?: number
) => {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', action, {
      event_category: category,
      event_label: label,
      value: value,
    });
  }
};

// Track trading-specific events
export const trackTradeEvent = (action: 'add' | 'edit' | 'delete' | 'exit', ticker: string, pnl?: number) => {
  trackEvent(action, 'trading', ticker, pnl);
};

// Track user engagement events
export const trackUserEngagement = (action: string, label?: string) => {
  trackEvent(action, 'user_engagement', label);
};

// Track form submissions
export const trackFormSubmission = (formName: string, success: boolean) => {
  trackEvent('form_submit', 'form_interaction', `${formName}_${success ? 'success' : 'error'}`);
};

// Track navigation events
export const trackNavigation = (from: string, to: string) => {
  trackEvent('navigation', 'page_navigation', `${from}_to_${to}`);
};
