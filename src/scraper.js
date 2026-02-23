const axios = require('axios');
const cheerio = require('cheerio');
const { getDistance } = require('geolib');
const criteria = require('../config/criteria.json');

const DOMAIN_SEARCH_URL = 'https://www.domain.com.au/sale/';

class PropertyScraper {
  constructor() {
    this.client = axios.create({
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-AU,en;q=0.9'
      },
      timeout: 90000
    });
  }

  /**
   * Build Domain search URL from criteria
   */
  buildSearchUrl(suburb, page = 1) {
    const { search } = criteria;
    // Domain URL format: /sale/arncliffe-nsw-2205/?bedrooms=3-any&price=1800000-2800000&ptype=house
    const suburbSlug = suburb.toLowerCase().replace(/\s+/g, '-');
    const state = search.state.toLowerCase();
    
    let url = `https://www.domain.com.au/sale/${suburbSlug}-${state}/`;
    const params = new URLSearchParams();
    
    params.set('bedrooms', `${search.bedrooms.min}-any`);
    params.set('bathrooms', `${search.bathrooms?.min || 1}-any`);
    params.set('price', `${search.budget.min}-${search.budget.max}`);
    
    // Property types
    const typeMap = { house: 'house', townhouse: 'town-house', duplex: 'duplex,semi-detached' };
    const ptypes = search.propertyTypes.map(t => typeMap[t] || t).join(',');
    params.set('ptype', ptypes);
    
    if (page > 1) params.set('page', page.toString());
    
    return `${url}?${params.toString()}`;
  }

  /**
   * Scrape listings from Domain search results page
   */
  async scrapeSuburb(suburb) {
    const url = this.buildSearchUrl(suburb);
    console.log(`   🔍 ${suburb}: ${url}`);
    
    try {
      const response = await this.client.get(url);
      const html = response.data;
      
      // Domain embeds listing data as JSON in a script tag
      const listings = this.extractListingsFromHtml(html, suburb);
      console.log(`   ✅ ${suburb}: ${listings.length} listings found`);
      return listings;
    } catch (error) {
      if (error.response?.status === 403) {
        console.error(`   ⚠️ ${suburb}: Blocked (403) — may need browser scraping`);
      } else if (error.response?.status === 404) {
        console.log(`   ℹ️ ${suburb}: No listings page (404)`);
      } else {
        console.error(`   ❌ ${suburb}: ${error.message}`);
      }
      return [];
    }
  }

  /**
   * Extract listing data from Domain HTML
   * Domain uses Next.js and embeds data in __NEXT_DATA__ script
   */
  extractListingsFromHtml(html, suburb) {
    const $ = cheerio.load(html);
    const listings = [];
    
    // Try __NEXT_DATA__ first (most reliable)
    const nextDataScript = $('script#__NEXT_DATA__').html();
    if (nextDataScript) {
      try {
        const nextData = JSON.parse(nextDataScript);
        const cp = nextData?.props?.pageProps?.componentProps;
        
        // Domain stores listings in componentProps.listingsMap
        const listingResults = cp?.listingsMap || {};
        const items = Object.values(listingResults);
        
        for (const item of items) {
          const listing = this.parseNextDataListing(item, suburb);
          if (listing) listings.push(listing);
        }
        
        if (listings.length > 0) return listings;
      } catch (e) {
        // Fall through to HTML parsing
      }
    }

    // Fallback: parse listing cards from HTML
    $('[data-testid="listing-card-wrapper-premiumplus"], [data-testid="listing-card-wrapper-premium"], [data-testid="listing-card-wrapper-standard"], li[data-testid^="listing-"]').each((_, el) => {
      const $el = $(el);
      const listing = this.parseHtmlListing($el, $, suburb);
      if (listing) listings.push(listing);
    });

    return listings;
  }

  /**
   * Parse listing from __NEXT_DATA__ JSON
   */
  parseNextDataListing(item, suburb) {
    if (!item || !item.listingModel) return null;
    const l = item.listingModel;
    
    const id = l.id || l.listingId;
    if (!id) return null;

    // Address: try multiple paths, fall back to URL slug
    let address = l.address?.displayAddress || l.address?.displayableAddress || l.address?.street || '';
    if (!address && l.url) {
      // Extract from URL: /64-princes-highway-arncliffe-nsw-2205-2019853254
      const slugMatch = l.url.match(/\/([^/]+)-\d{7,}$/);
      if (slugMatch) {
        address = slugMatch[1]
          .replace(/-nsw-\d{4}$/, '')
          .replace(/-/g, ' ')
          .replace(/\b\w/g, c => c.toUpperCase());
      }
    }
    if (!address) address = 'Unknown';
    const lat = l.address?.lat || null;
    const lng = l.address?.lng || null;

    let distanceToSchool = null;
    if (lat && lng) {
      const school = criteria.keyLocations[0];
      distanceToSchool = getDistance(
        { latitude: lat, longitude: lng },
        { latitude: school.lat, longitude: school.lng }
      ) / 1000;
    }

    return {
      id: `domain-${id}`,
      source: 'domain',
      url: l.url ? `https://www.domain.com.au${l.url}` : `https://www.domain.com.au/${id}`,
      address,
      suburb: l.address?.suburb || suburb,
      postcode: l.address?.postcode || '',
      price_display: l.price || 'Contact Agent',
      ...this.parsePrice(l.price),
      property_type: l.propertyType?.toLowerCase() || 'house',
      bedrooms: l.features?.beds || 0,
      bathrooms: l.features?.baths || 0,
      parking: l.features?.parking || 0,
      land_size_sqm: l.features?.landSize || null,
      building_size_sqm: l.features?.buildingSize || null,
      headline: l.headline || l.tags?.join(', ') || '',
      description: l.description || '',
      agent_name: l.branding?.agentNames || '',
      agent_phone: '',
      agency: l.branding?.agencyName || '',
      lat,
      lng,
      distance_to_school_km: distanceToSchool ? Math.round(distanceToSchool * 100) / 100 : null,
      listing_date: l.listingDate || null,
      auction_date: l.auctionDate || null,
      raw_json: JSON.stringify(item)
    };
  }

  /**
   * Parse listing from HTML card element
   */
  parseHtmlListing($el, $, suburb) {
    const link = $el.find('a[href*="/"]').first();
    const href = link.attr('href') || '';
    const idMatch = href.match(/(\d{6,})/);
    if (!idMatch) return null;

    const id = idMatch[1];
    const address = $el.find('[data-testid="listing-card-address"], [data-testid="address-line1"]').text().trim() ||
                   link.attr('aria-label') || 'Unknown';
    
    const priceText = $el.find('[data-testid="listing-card-price"]').text().trim() || 
                      $el.find('.listing-result__price').text().trim() || 'Contact Agent';
    
    const features = $el.find('[data-testid="property-features"]').text();
    const bedsMatch = features.match(/(\d+)\s*Bed/i);
    const bathsMatch = features.match(/(\d+)\s*Bath/i);
    const carsMatch = features.match(/(\d+)\s*Car/i);

    return {
      id: `domain-${id}`,
      source: 'domain',
      url: href.startsWith('http') ? href : `https://www.domain.com.au${href}`,
      address,
      suburb,
      postcode: '',
      price_display: priceText,
      ...this.parsePrice(priceText),
      property_type: 'house',
      bedrooms: bedsMatch ? parseInt(bedsMatch[1]) : 0,
      bathrooms: bathsMatch ? parseInt(bathsMatch[1]) : 0,
      parking: carsMatch ? parseInt(carsMatch[1]) : 0,
      land_size_sqm: null,
      building_size_sqm: null,
      headline: $el.find('[data-testid="listing-card-headline"]').text().trim() || '',
      description: '',
      agent_name: $el.find('[data-testid="listing-card-agent"]').text().trim() || '',
      agent_phone: '',
      agency: $el.find('[data-testid="listing-card-branding"]').text().trim() || '',
      lat: null,
      lng: null,
      distance_to_school_km: null,
      listing_date: null,
      auction_date: null,
      raw_json: ''
    };
  }

  /**
   * Extract numeric price from display string
   */
  parsePrice(display) {
    if (!display) return { price_low: null, price_high: null };
    const cleaned = display.replace(/[$,]/g, '');

    const rangeMatch = cleaned.match(/([\d.]+)\s*[mM]?\s*[-–to]+\s*([\d.]+)\s*[mM]?/);
    if (rangeMatch) {
      let low = parseFloat(rangeMatch[1]);
      let high = parseFloat(rangeMatch[2]);
      if (low < 1000) low *= 1e6;
      if (high < 1000) high *= 1e6;
      return { price_low: Math.round(low), price_high: Math.round(high) };
    }

    const singleMatch = cleaned.match(/([\d.]+)\s*[mM]?/);
    if (singleMatch) {
      let val = parseFloat(singleMatch[1]);
      if (val < 1000) val *= 1e6;
      return { price_low: Math.round(val), price_high: Math.round(val) };
    }

    return { price_low: null, price_high: null };
  }

  /**
   * Scan all suburbs
   */
  async scanAll() {
    const { search } = criteria;
    const allListings = [];

    console.log(`🏠 Scanning ${search.suburbs.length} suburbs on Domain.com.au...\n`);

    for (const suburb of search.suburbs) {
      const listings = await this.scrapeSuburb(suburb);
      allListings.push(...listings);
      
      // Be respectful — small delay between requests
      await new Promise(r => setTimeout(r, 1500));
    }

    // Deduplicate by listing ID
    const seen = new Set();
    const unique = allListings.filter(l => {
      if (seen.has(l.id)) return false;
      seen.add(l.id);
      return true;
    });

    console.log(`\n📋 Total: ${allListings.length} listings, ${unique.length} unique`);
    return unique;
  }
}

module.exports = PropertyScraper;
