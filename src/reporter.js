const { getDb } = require('./db');

class Reporter {
  constructor() {
    this.db = null;
  }

  async init() {
    this.db = await getDb();
  }

  _query(sql, params = []) {
    const result = this.db.exec(sql, params);
    if (!result.length) return [];
    const cols = result[0].columns;
    return result[0].values.map(row => {
      const obj = {};
      cols.forEach((c, i) => obj[c] = row[i]);
      return obj;
    });
  }

  getTopListings(limit = 10) {
    return this._query(
      `SELECT * FROM listings WHERE status = 'active' ORDER BY score DESC LIMIT ?`,
      [limit]
    );
  }

  getNewListings(sinceHours = 24) {
    return this._query(
      `SELECT * FROM listings WHERE first_seen > datetime('now', '-' || ? || ' hours') AND status = 'active' ORDER BY score DESC`,
      [sinceHours]
    );
  }

  getMarketSummary() {
    const suburbs = this._query(`
      SELECT suburb, COUNT(*) as active_listings,
        ROUND(AVG(price_low)) as avg_price,
        MIN(price_low) as min_price, MAX(price_high) as max_price,
        ROUND(AVG(land_size_sqm)) as avg_land_sqm,
        ROUND(AVG(distance_to_school_km), 2) as avg_dist_school
      FROM listings WHERE status = 'active' AND price_low IS NOT NULL
      GROUP BY suburb ORDER BY avg_price ASC
    `);

    const totals = this._query(`
      SELECT COUNT(*) as total,
        COUNT(CASE WHEN first_seen > datetime('now', '-24 hours') THEN 1 END) as new_24h,
        ROUND(AVG(score), 1) as avg_score
      FROM listings WHERE status = 'active'
    `);

    return { suburbs, totals: totals[0] || { total: 0, new_24h: 0, avg_score: 0 } };
  }

  formatListingWhatsApp(listing) {
    const price = listing.price_display || 'Contact Agent';
    const dist = listing.distance_to_school_km
      ? `${listing.distance_to_school_km}km to Al Zahra`
      : '';
    const beds = listing.bedrooms ? `${listing.bedrooms}🛏` : '';
    const baths = listing.bathrooms ? `${listing.bathrooms}🚿` : '';
    const land = listing.land_size_sqm ? `${listing.land_size_sqm}m²` : '';
    const score = listing.score ? `Score: ${listing.score}/100` : '';

    return [
      `*${listing.address}*`,
      `${price} | ${beds} ${baths} ${land ? '| ' + land : ''}`,
      dist,
      score,
      listing.headline || '',
      listing.url || ''
    ].filter(Boolean).join('\n');
  }

  generateWhatsAppReport() {
    const top = this.getTopListings(5);
    const newOnes = this.getNewListings(24);
    const summary = this.getMarketSummary();

    let report = `🏠 *PropertyFinder Report*\n\n`;
    report += `📊 *${summary.totals.total}* active listings | *${summary.totals.new_24h}* new today\n`;
    report += `Avg score: ${summary.totals.avg_score}/100\n\n`;

    if (newOnes.length > 0) {
      report += `🆕 *New Listings (24h):*\n\n`;
      for (const l of newOnes.slice(0, 3)) {
        report += this.formatListingWhatsApp(l) + '\n\n';
      }
    }

    if (top.length > 0) {
      report += `⭐ *Top Picks:*\n\n`;
      for (const l of top.slice(0, 5)) {
        report += this.formatListingWhatsApp(l) + '\n\n';
      }
    }

    return report.trim();
  }
}

module.exports = Reporter;
