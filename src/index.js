require('dotenv').config();

const { setup, getDb, saveDb } = require('./db');
const PropertyScraper = require('./scraper');
const PropertyScanner = require('./scanner');
const { scoreListing } = require('./scorer');
const Reporter = require('./reporter');

async function scan() {
  console.log('🏠 PropertyFinder — Starting scan...\n');
  await setup();

  // Use scraper (no API key needed)
  const scraper = new PropertyScraper();
  const listings = await scraper.scanAll();

  if (listings.length === 0) {
    console.log('No listings found.');
    return;
  }

  // Score each listing
  const scored = listings.map(l => ({
    ...l,
    score: scoreListing(l)
  }));

  // Save to DB using the scanner's save logic
  const apiKey = process.env.DOMAIN_API_KEY || 'unused';
  const scanner = new PropertyScanner(apiKey);
  await scanner.init();
  const result = scanner.saveListings(scored);
  console.log(`\n💾 Saved: ${result.total} total | ${result.new} new | ${result.priceChanges} price changes`);

  // Show top 5
  console.log('\n⭐ Top 5 Listings:\n');
  const top5 = scored.sort((a, b) => b.score - a.score).slice(0, 5);
  for (const [i, l] of top5.entries()) {
    console.log(`${i + 1}. [${l.score}/100] ${l.address}`);
    console.log(`   ${l.price_display} | ${l.bedrooms}bed ${l.bathrooms}bath | ${l.land_size_sqm || '?'}m²`);
    if (l.distance_to_school_km) {
      console.log(`   📍 ${l.distance_to_school_km}km to Al Zahra College`);
    }
    console.log(`   ${l.url}\n`);
  }

  if (result.new > 0) {
    console.log(`🆕 ${result.new} new listings found this scan!`);
  }

  console.log('\n✅ Scan complete!');
  return { scored, result };
}

async function report() {
  await setup();
  const reporter = new Reporter();
  await reporter.init();
  const whatsappReport = reporter.generateWhatsAppReport();
  console.log(whatsappReport);
}

// CLI
const command = process.argv[2] || 'scan';

switch (command) {
  case 'scan':
    scan().catch(console.error);
    break;
  case 'report':
    report().catch(console.error);
    break;
  case 'setup':
    setup().then(() => console.log('Done')).catch(console.error);
    break;
  default:
    console.log('Usage: node src/index.js [scan|report|setup]');
}
