# 🏠 PropertyFinder

Automated Sydney property finder for the Arncliffe/Rockdale area. Scans Domain.com.au for listings matching your criteria and alerts you on WhatsApp when something good drops.

## Features

- **Daily automated scans** of Domain.com.au listings
- **Smart filtering** by price, bedrooms, property type, distance to Al Zahra College
- **Comparable sales analysis** — what similar properties actually sold for
- **Distance scoring** — walk/drive time to key locations
- **WhatsApp alerts** — get notified when a match appears
- **Price history tracking** — see price changes over time
- **Sold data analysis** — understand the real market, not just asking prices

## Target Area

Primary search zone: Arncliffe, Rockdale, Bexley, Banksia, Wolli Creek, Turrella, Bardwell Park, Bardwell Valley, Kingsgrove

## Criteria (Default)

| Parameter | Value |
|-----------|-------|
| Budget | $1.8M - $2.8M |
| Type | House |
| Bedrooms | 3+ |
| Key location | Al Zahra College, Arncliffe |

## Setup

```bash
npm install
cp .env.example .env
# Add your Domain API key
npm run scan
```

## Architecture

```
src/
  scanner.js      # Domain API client + scraper
  analyzer.js     # Price analysis + comparables
  scorer.js       # Location scoring + ranking
  notifier.js     # WhatsApp alert integration
  db.js           # SQLite storage
config/
  criteria.json   # Search criteria
  locations.json  # Key locations for distance calc
data/
  listings.db     # SQLite database
```

## Data Sources

- **Domain.com.au API** — primary listing source (free tier: 500 calls/day)
- **Domain sold data** — comparable sales
- **Google Maps / OpenRouteService** — distance calculations

## License

Private — personal use only.
