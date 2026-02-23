require('dotenv').config();

const { setup, getDb, saveDb } = require('./db');
const PropertyScanner = require('./scanner');
const { scoreListing } = require('./scorer');
const Reporter = require('./reporter');

async function scan() {
  const apiKey = process.env.DOMAIN_API_KEY;
  if (!apiKey || apiKey === 'your_domain_api_key_here') {
    console.error('❌ No Domain API key set. Get one from https://developer.domain.com.au');
    console.log('\nTo get started:');
    console.log('1. Sign up at https://developer.domain.com.au');
    console.log('2. Create a project (free tier = 500 calls/day)');
    console.log('3. Copy your API key to .env file');
    process.exit(1);
  }

  console.log('🏠 PropertyFinder — Starting scan...\n');
  await setup();

  const scanner = new PropertyScanner(apiKey);
  await scanner.init();

  // Fetch listings from Domain
  const rawListings = await scanner.searchListings();

  if (rawListings.length === 0) {
    console.log('No listings found. Check criteria or API key.');
    return;
  }

  // Parse and normalize
  const parsed = rawListings.map(l => scanner.parseListing(l));
  console.log(`\n📋 Parsed ${parsed.length} listings`);

  // Score each listing
  const scored = parsed.map(l => ({
    ...l,
    score: scoreListing(l)
  }));

  // Save to DB
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
    console.log(`\n🆕 ${result.new} new listings found this scan!`);
  }

  console.log('\n✅ Scan complete!');
}

async function report() {
  await setup();
  const reporter = new Reporter();
  await reporter.init();
  const whatsappReport = reporter.generateWhatsAppReport();
  console.log(whatsappReport);
}

async function alertTest() {
  console.log('🔔 Alert test — would send to WhatsApp:');
  console.log('---');
  await report();
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
  case 'alert-test':
    alertTest().catch(console.error);
    break;
  case 'setup':
    setup().then(() => console.log('Done')).catch(console.error);
    break;
  default:
    console.log('Usage: node src/index.js [scan|report|alert-test|setup]');
}
