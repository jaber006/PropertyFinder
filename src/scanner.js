const axios = require('axios');
const { getDb, saveDb } = require('./db');
const { getDistance } = require('geolib');
const criteria = require('../config/criteria.json');

const DOMAIN_API_BASE = 'https://api.domain.com.au/v1';

class PropertyScanner {
  constructor(apiKey) {
    this.apiKey = apiKey;
    this.client = axios.create({
      baseURL: DOMAIN_API_BASE,
      headers: {
        'X-Api-Key': apiKey,
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      }
    });
    this.db = null;
  }

  async init() {
    this.db = await getDb();
  }

  /**
   * Search Domain API for residential listings
   */
  async searchListings() {
    const { search } = criteria;

    const payload = {
      listingType: 'Sale',
      propertyTypes: search.propertyTypes.map(t => t.charAt(0).toUpperCase() + t.slice(1)),
      minBedrooms: search.bedrooms.min,
      minBathrooms: search.bathrooms?.min || 1,
      minPrice: search.budget.min,
      maxPrice: search.budget.max,
      locations: search.suburbs.map(suburb => ({
        state: search.state,
        suburb: suburb
      })),
      pageSize: 100,
      sort: {
        sortKey: 'DateUpdated',
        direction: 'Descending'
      }
    };

    console.log(`🔍 Searching Domain API for ${search.suburbs.length} suburbs...`);
    console.log(`   Budget: $${(search.budget.min / 1e6).toFixed(1)}M - $${(search.budget.max / 1e6).toFixed(1)}M`);
    console.log(`   Type: ${search.propertyTypes.join(', ')} | Beds: ${search.bedrooms.min}+`);

    try {
      const response = await this.client.post('/residential/search/listing', payload);
      const listings = response.data || [];
      console.log(`   Found ${listings.length} listings from Domain API`);
      return listings;
    } catch (error) {
      if (error.response?.status === 401) {
        console.error('❌ Domain API key invalid or expired. Check .env');
      } else if (error.response?.status === 429) {
        console.error('❌ Rate limited. Try again later.');
      } else {
        console.error(`❌ Domain API error: ${error.response?.status} ${error.message}`);
      }
      return [];
    }
  }

  /**
   * Parse and normalize a Domain listing
   */
  parseListing(raw) {
    const listing = raw.listing || raw;
    const address = listing.propertyDetails?.displayableAddress ||
                    listing.propertyDetails?.address?.displayAddress || 
                    'Unknown';
    
    const suburb = listing.propertyDetails?.address?.suburb || '';
    const postcode = listing.propertyDetails?.address?.postcode || '';
    const lat = listing.propertyDetails?.latitude || null;
    const lng = listing.propertyDetails?.longitude || null;

    const priceDisplay = listing.priceDetails?.displayPrice || 'Contact Agent';
    const { low, high } = this.parsePrice(priceDisplay);

    let distanceToSchool = null;
    if (lat && lng) {
      const school = criteria.keyLocations[0];
      distanceToSchool = getDistance(
        { latitude: lat, longitude: lng },
        { latitude: school.lat, longitude: school.lng }
      ) / 1000;
    }

    return {
      id: `domain-${listing.id}`,
      source: 'domain',
      url: `https://www.domain.com.au/${listing.listingSlug || listing.id}`,
      address,
      suburb,
      postcode,
      price_display: priceDisplay,
      price_low: low,
      price_high: high,
      property_type: listing.propertyDetails?.propertyType?.toLowerCase() || 'house',
      bedrooms: listing.propertyDetails?.bedrooms || 0,
      bathrooms: listing.propertyDetails?.bathrooms || 0,
      parking: listing.propertyDetails?.carSpaces || 0,
      land_size_sqm: listing.propertyDetails?.landArea || null,
      building_size_sqm: listing.propertyDetails?.buildingArea || null,
      headline: listing.headline || '',
      description: listing.summaryDescription || listing.description || '',
      agent_name: listing.advertiser?.contacts?.[0]?.name || '',
      agent_phone: listing.advertiser?.contacts?.[0]?.phoneNumbers?.[0]?.number || '',
      agency: listing.advertiser?.name || '',
      lat,
      lng,
      distance_to_school_km: distanceToSchool ? Math.round(distanceToSchool * 100) / 100 : null,
      listing_date: listing.dateListed || listing.dateUpdated || null,
      auction_date: listing.auctionSchedule?.time || null,
      raw_json: JSON.stringify(raw)
    };
  }

  /**
   * Extract numeric price from display string
   */
  parsePrice(display) {
    if (!display) return { low: null, high: null };
    const cleaned = display.replace(/[$,]/g, '');

    const rangeMatch = cleaned.match(/([\d.]+)\s*[mM]?\s*[-–to]+\s*([\d.]+)\s*[mM]?/);
    if (rangeMatch) {
      let low = parseFloat(rangeMatch[1]);
      let high = parseFloat(rangeMatch[2]);
      if (low < 1000) low *= 1e6;
      if (high < 1000) high *= 1e6;
      return { low: Math.round(low), high: Math.round(high) };
    }

    const singleMatch = cleaned.match(/([\d.]+)\s*[mM]?/);
    if (singleMatch) {
      let val = parseFloat(singleMatch[1]);
      if (val < 1000) val *= 1e6;
      return { low: Math.round(val), high: Math.round(val) };
    }

    return { low: null, high: null };
  }

  /**
   * Save listings to DB, track price changes
   */
  saveListings(listings) {
    let newCount = 0;
    let priceChangeCount = 0;

    for (const item of listings) {
      // Check if exists
      const existing = this.db.exec('SELECT id, price_low, price_high FROM listings WHERE id = ?', [item.id]);
      
      if (existing.length === 0 || existing[0].values.length === 0) {
        // New listing
        this.db.run(`
          INSERT INTO listings (
            id, source, url, address, suburb, postcode,
            price_display, price_low, price_high,
            property_type, bedrooms, bathrooms, parking,
            land_size_sqm, building_size_sqm,
            headline, description, agent_name, agent_phone, agency,
            lat, lng, distance_to_school_km, score,
            listing_date, auction_date, raw_json
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        `, [
          item.id, item.source, item.url, item.address, item.suburb, item.postcode,
          item.price_display, item.price_low, item.price_high,
          item.property_type, item.bedrooms, item.bathrooms, item.parking,
          item.land_size_sqm, item.building_size_sqm,
          item.headline, item.description, item.agent_name, item.agent_phone, item.agency,
          item.lat, item.lng, item.distance_to_school_km, item.score || 0,
          item.listing_date, item.auction_date, item.raw_json
        ]);
        newCount++;
      } else {
        // Update existing
        const row = existing[0].values[0];
        const oldPriceLow = row[1];
        const oldPriceHigh = row[2];

        if (oldPriceLow !== item.price_low || oldPriceHigh !== item.price_high) {
          this.db.run(
            'INSERT INTO price_history (listing_id, price_display, price_low, price_high) VALUES (?, ?, ?, ?)',
            [item.id, item.price_display, item.price_low, item.price_high]
          );
          priceChangeCount++;
        }

        this.db.run(`
          UPDATE listings SET
            price_display = ?, price_low = ?, price_high = ?,
            score = ?, last_seen = datetime('now'), raw_json = ?
          WHERE id = ?
        `, [item.price_display, item.price_low, item.price_high, item.score || 0, item.raw_json, item.id]);
      }
    }

    saveDb(this.db);
    return { total: listings.length, new: newCount, priceChanges: priceChangeCount };
  }
}

module.exports = PropertyScanner;
