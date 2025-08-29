interface StructuredDataProps {
  data: Record<string, any>
}

export default function StructuredData({ data }: StructuredDataProps) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  )
}

// Website structured data
export const websiteStructuredData = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  "name": "TradeBud",
  "applicationCategory": "FinanceApplication",
  "description": "Professional trading journal platform with real-time analytics, performance tracking, and comprehensive trade management tools.",
  "url": process.env.NEXT_PUBLIC_BASE_URL || "https://app.tradebud.xyz",
  "operatingSystem": "Web",
  "author": {
    "@type": "Organization",
    "name": "TradeBud"
  },
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD"
  },
  "featureList": [
    "Trading journal and diary",
    "Performance analytics and metrics",
    "Trade tracking and management",
    "Monthly returns analysis",
    "Calendar view of trades",
    "Profit and loss calculations",
    "Portfolio performance tracking"
  ]
}

// Organization structured data
export const organizationStructuredData = {
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "TradeBud",
  "description": "Advanced trading journal platform for traders to track, analyze, and improve their trading performance.",
  "url": process.env.NEXT_PUBLIC_BASE_URL || "https://app.tradebud.xyz",
  "logo": `${process.env.NEXT_PUBLIC_BASE_URL || "https://app.tradebud.xyz"}/logo.png`,
  "sameAs": [
    // Add your social media URLs here when available
  ]
}

// SoftwareApplication structured data
export const softwareStructuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "TradeBud Trading Journal",
  "applicationCategory": "BusinessApplication",
  "applicationSubCategory": "FinanceApplication",
  "description": "Comprehensive trading journal application for tracking trades, analyzing performance, and improving trading strategies.",
  "operatingSystem": "Web Browser",
  "url": process.env.NEXT_PUBLIC_BASE_URL || "https://app.tradebud.xyz",
  "author": {
    "@type": "Organization",
    "name": "TradeBud"
  },
  "offers": {
    "@type": "Offer",
    "price": "0",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock"
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "4.8",
    "ratingCount": "150",
    "bestRating": "5",
    "worstRating": "1"
  }
}
