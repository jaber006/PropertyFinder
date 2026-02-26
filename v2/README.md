# PropertyFinder v2 — Development Opportunity Scanner

AI-powered property development opportunity scanner for Australia. Scans property listings nationwide and identifies development opportunities — duplex, subdivision, knockdown-rebuild — scoring each property 0-100 for development potential.

## Features

- **Multi-source scanning** — Domain.com.au API + web scraping, realestate.com.au web scraping, JSON import
- **National scope** — Configure any Australian suburb/region
- **Development scoring (0-100)** — Land size, frontage, zoning, dwelling age, keywords
- **Feasibility estimates** — Purchase cost + build cost vs end value with profit margin
- **Smart deduplication** — SQLite DB with dedup by listing ID
- **Price tracking** — Detects and logs price changes across scans
- **Alert system** — New high-scoring listings saved to `alerts/new-listings.json`
- **CLI interface** — scan, import, alerts, report, stats, rescore

## Quick Start

```bash
cd v2/

# Install dependencies
pip install -r requirements.txt

# Import existing scraped data (from ../data/ JSON files)
python main.py import

# Or import a specific file
python main.py import path/to/scrape.json

# View top opportunities
python main.py report

# Check alerts
python main.py alerts

# Run a live scan (Domain API + web scraping)
python main.py scan

# Database stats
python main.py stats
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py scan` | Full scan of all configured regions |
| `python main.py scan --region Sydney` | Scan only regions matching "Sydney" |
| `python main.py scan --api-only` | Only use Domain API (skip web scraping) |
| `python main.py import` | Import from `../data/` JSON files |
| `python main.py import file.json` | Import specific JSON file |
| `python main.py import --dir ./exports/` | Import all JSONs from directory |
| `python main.py alerts` | Show alerts from last 24 hours |
| `python main.py alerts --hours 48` | Show alerts from last 48 hours |
| `python main.py report` | Top 20 development opportunities |
| `python main.py report --top 50 -s 70` | Top 50 with score >= 70 |
| `python main.py rescore` | Re-score all active listings |
| `python main.py stats` | Database statistics |

## Architecture

```
v2/
├── main.py                  # CLI runner (scan, import, alerts, report, stats, rescore)
├── config.yaml              # Region config, scoring weights, feasibility params
├── requirements.txt         # Python dependencies
│
├── scanner/                 # Listing acquisition
│   ├── domain_api.py        # Domain.com.au official API (Agents & Listings pending)
│   ├── domain_scraper.py    # Domain.com.au web scraper (blocked by bot protection)
│   ├── rea_scraper.py       # realestate.com.au web scraper (blocked by bot protection)
│   ├── browser_scraper.py   # Playwright browser-based scraper (requires playwright)
│   ├── importer.py          # JSON file importer (most reliable data source)
│   └── db.py                # SQLite database manager
│
├── analysis/                # Development analysis
│   ├── scorer.py            # Development potential scoring (0-100)
│   └── feasibility.py       # Financial feasibility estimation
│
├── alerts/                  # Alert management
│   ├── manager.py           # Alert saving and retrieval
│   └── new-listings.json    # Active alerts (auto-generated)
│
└── data/
    └── listings_v2.db       # SQLite database (auto-created)
```

## Development Scoring

Each listing is scored 0-100 based on weighted factors:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Land size | 25% | 550m²+ gets points, 800m²+ gets more |
| Frontage | 15% | Wider frontage = easier subdivision |
| Price/value | 15% | Below-median price = more profit margin |
| Dwelling age | 15% | Older = more likely knockdown candidate |
| Zoning | 15% | R3/R4/RGZ = medium+ density allowed |
| Keywords | 10% | DA approved, development site, etc. |
| Feasibility | 5% | Estimated profit margin |

### Development Flags Detected

- DA approved / development application
- Listed as development opportunity
- Subdivision potential / Corner block
- Duplex/dual-occ mentioned
- Old dwelling (knockdown candidate)
- Medium/high density zoning (R3/R4/RGZ)
- Rear lane access
- Deceased estate (motivated sale)
- Heritage/flood/bushfire risks (negative)

## Data Sources

| Source | Method | Status |
|--------|--------|--------|
| JSON Import | File import | **Primary** — most reliable |
| Domain API (Listings Management) | Official API | Sandbox only (no search) |
| Domain API (Agents & Listings) | Official API | Pending approval |
| Domain API (Properties & Locations) | Official API | Pending approval |
| Domain API (Price Estimation) | Official API | Pending approval |
| Domain.com.au | Web scraping | Blocked by bot protection |
| realestate.com.au | Web scraping | Blocked by bot protection (Kasada) |

### Getting Data In

Since both Domain and REA use aggressive bot protection, the most reliable workflow is:

1. **Browser scraping via Clawdbot** — manually browse listings, export JSON
2. **Import JSON** — `python main.py import scrape-data.json`
3. **Domain API** — when Agents & Listings API is approved, `python main.py scan` will work directly

## Configuration

Edit `config.yaml` to:
- Add/remove watched regions and suburbs
- Adjust price ranges and minimum land sizes
- Tune scoring weights
- Set feasibility assumptions (build costs, stamp duty, etc.)
- Configure alert thresholds

### Default Regions

1. **Sydney - St George**: Arncliffe, Banksia, Turrella, Rockdale, Bexley, Wolli Creek ($1.3-2.5M, 550m²+)
2. **Melbourne - Growth Corridors**: Sunbury, Craigieburn, Melton, Tarneit ($600K-1.5M, 600m²+)
3. **Sydney - Outer West**: Marsden Park, Schofields, Austral ($800K-1.8M, 500m²+)

## Requirements

- Python 3.8+
- Domain API key (in `../.env` as `DOMAIN_API_KEY`)
- Internet connection (for API/scraping; not needed for import)

## License

Private — personal use only.
