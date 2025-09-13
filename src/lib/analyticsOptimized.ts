// Optimized Google Analytics utility functions with batching

declare global {
  interface Window {
    gtag: (
      command: 'config' | 'event' | 'js',
      targetId: string,
      config?: Record<string, any>
    ) => void;
  }
}

// Batch analytics events to reduce calls
class AnalyticsBatcher {
  private batch: Array<() => void> = [];
  private timeoutId: NodeJS.Timeout | null = null;
  private readonly BATCH_DELAY = 100; // 100ms delay

  addEvent(eventFn: () => void) {
    this.batch.push(eventFn);
    
    if (this.timeoutId) {
      clearTimeout(this.timeoutId);
    }
    
    this.timeoutId = setTimeout(() => {
      this.flush();
    }, this.BATCH_DELAY);
  }

  private flush() {
    this.batch.forEach(eventFn => eventFn());
    this.batch = [];
    this.timeoutId = null;
  }
}

const batcher = new AnalyticsBatcher();

// Track page views (optimized)
export const trackPageView = (url: string) => {
  if (typeof window !== 'undefined' && window.gtag) {
    batcher.addEvent(() => {
      window.gtag('config', process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID!, {
        page_path: url,
      });
    });
  }
};

// Track custom events (optimized)
export const trackEvent = (
  action: string,
  category: string,
  label?: string,
  value?: number
) => {
  if (typeof window !== 'undefined' && window.gtag) {
    batcher.addEvent(() => {
      window.gtag('event', action, {
        event_category: category,
        event_label: label,
        value: value,
      });
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
