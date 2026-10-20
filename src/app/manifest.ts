import { MetadataRoute } from 'next'
 
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: 'TradeBud — Free Trading Journal',
    short_name: 'TradeBud',
    description: 'A completely free trading journal for recording decisions and analyzing performance.',
    start_url: '/',
    display: 'standalone',
    background_color: '#f6f7f9',
    theme_color: '#0c9b63',
    orientation: 'portrait',
    categories: ['finance', 'business', 'productivity'],
    lang: 'en',
  }
}
