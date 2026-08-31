declare global {
  interface Window {
    gtag?: (command: "event" | "config", target: string, parameters?: Record<string, string>) => void;
  }
}

/**
 * Public-site analytics deliberately accepts only action names and coarse
 * identifiers. Never pass prices, balances, symbols, notes, or calculator
 * inputs through this boundary.
 */
export function trackPublicEvent(action: string, resource?: string): void {
  if (typeof window === "undefined" || typeof window.gtag !== "function") return;

  const parameters: Record<string, string> = { event_category: "public_site" };
  if (resource) parameters.resource = resource;
  window.gtag("event", action, parameters);
}

export {};
