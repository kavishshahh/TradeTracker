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
  ..._ignoredDetails: unknown[]
) => {
  void _ignoredDetails;
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', action, {
      event_category: category,
    });
  }
};

// Track trading-specific events
export const trackTradeEvent = (action: 'add' | 'edit' | 'delete' | 'exit', ..._ignoredDetails: unknown[]) => {
  void _ignoredDetails;
  trackEvent(action, 'trading');
};

// Track user engagement events
export const trackUserEngagement = (action: string, ..._ignoredDetails: unknown[]) => {
  void _ignoredDetails;
  trackEvent(action, 'user_engagement');
};

// Track form submissions
export const trackFormSubmission = (formName: string, success: boolean) => {
  void formName;
  trackEvent(success ? 'form_submit_success' : 'form_submit_error', 'form_interaction');
};

// Track navigation events
export const trackNavigation = (from: string, to: string) => {
  void from;
  void to;
  trackEvent('navigation', 'page_navigation');
};
