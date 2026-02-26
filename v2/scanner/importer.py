"""
Data Importer — loads listings from JSON files (manual scrapes, browser exports, etc.)

This is the most reliable data source since Domain and REA both block direct
HTTP requests with bot protection (Kasada/CloudFlare). Until the Domain
Agents & Listings API is approved, this is the primary way to feed data in.

Supports:
  - v1 stgeorge-scrape format (from Clawdbot browser scraping)
  - v1 rea-scrape format
  - Generic JSON array of listings
"""

import json
import re
import os
from typing import List, Dict, Optional
from datetime import datetime


class ListingImporter:
    """Import listings from various JSON formats into the standard schema."""

    def __init__(self, config: Dict = None):
        self.config = config or {}

    def import_file(self, filepath: str, region_name: str = '') -> List[Dict]:
        """Import listings from a JSON file, auto-detecting format."""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            return self._import_generic_list(data, region_name)
        elif isinstance(data, dict):
            # Detect format
            if 'listings' in data and 'scrape_date' in data:
                return self._import_stgeorge_format(data, region_name)
            elif 'listings' in data and 'scrapeDate' in data:
                return self._import_rea_format(data, region_name)
            elif 'listings' in data:
                return self._import_generic_list(data['listings'], region_name)
            else:
                print(f"  ⚠️  Unknown JSON format in {filepath}")
                return []
        return []

    def import_directory(self, dirpath: str, region_name: str = '') -> List[Dict]:
        """Import all JSON files from a directory."""
        all_listings = []
        for fname in sorted(os.listdir(dirpath)):
            if fname.endswith('.json') and not fname.startswith('.'):
                fpath = os.path.join(dirpath, fname)
                print(f"  📄 Importing {fname}...")
                listings = self.import_file(fpath, region_name)
                all_listings.extend(listings)
                print(f"     → {len(listings)} listings")
        return all_listings

    def _import_stgeorge_format(self, data: Dict, region_name: str) -> List[Dict]:
        """Import from the stgeorge-scrape JSON format."""
        listings = []
        scrape_date = data.get('scrape_date', '')

        for item in data.get('listings', []):
            listing = self._convert_scrape_listing(item, scrape_date, region_name)
            if listing:
                listings.append(listing)
        return listings

    def _import_rea_format(self, data: Dict, region_name: str) -> List[Dict]:
        """Import from the rea-scrape JSON format."""
        listings = []
        scrape_date = data.get('scrapeDate', '')

        for item in data.get('listings', []):
            listing = self._convert_scrape_listing(item, scrape_date, region_name)
            if listing:
                listings.append(listing)

        # Also import from knockdownCandidates if present
        for item in data.get('knockdownCandidates500plus', []):
            listing = self._convert_candidate(item, scrape_date, region_name)
            if listing:
                # Only add if not already present
                existing_addrs = {l.get('address', '').lower() for l in listings}
                if listing['address'].lower() not in existing_addrs:
                    listings.append(listing)

        return listings

    def _convert_scrape_listing(self, item: Dict, scrape_date: str, region_name: str) -> Optional[Dict]:
        """Convert a scraped listing item to standard format."""
        address = item.get('address', '')
        suburb = item.get('suburb', '')
        if not address and not suburb:
            return None

        full_address = f"{address}, {suburb}" if suburb and suburb not in address else address
        postcode = item.get('postcode', '')

        # Use REA URL ID if available, otherwise generate from normalized address
        url = item.get('url', '')
        url_id_match = re.search(r'(\d{8,})', url) if url else None
        if url_id_match:
            lid = f"rea-{url_id_match.group(1)}"
        else:
            # Normalize: strip unit letters, punctuation, etc
            addr_norm = re.sub(r'[^a-z0-9]', '', full_address.lower())
            lid = f"import-{addr_norm[:50]}"

        price_display = item.get('price', '') or ''
        price_low, price_high = self._parse_price(price_display)

        url = item.get('url', '')

        # Build description from notes
        notes = item.get('notes', '')
        description = notes

        return {
            'id': lid,
            'source': 'import',
            'url': url,
            'address': full_address,
            'suburb': suburb,
            'state': 'NSW',  # Default, could be improved
            'postcode': postcode,
            'region_name': region_name or 'Sydney - St George',
            'price_display': price_display or 'Contact Agent',
            'price_low': price_low,
            'price_high': price_high,
            'property_type': (item.get('property_type', '') or item.get('propertyType', '') or 'house').lower(),
            'bedrooms': item.get('beds', 0) or 0,
            'bathrooms': item.get('baths', 0) or 0,
            'parking': item.get('cars', 0) or 0,
            'land_size_sqm': item.get('land_sqm') or item.get('landSize'),
            'building_size_sqm': None,
            'frontage_m': None,
            'headline': '',
            'description': description,
            'features_text': '',
            'agent_name': '',
            'agent_phone': '',
            'agency': '',
            'lat': None,
            'lng': None,
            'zoning': None,
            'year_built': None,
            'listing_date': scrape_date,
            'auction_date': None,
            'days_on_market': None,
            'status': 'active',
            'raw_json': json.dumps(item),
        }

    def _convert_candidate(self, item: Dict, scrape_date: str, region_name: str) -> Optional[Dict]:
        """Convert a knockdown candidate item to standard format."""
        address = item.get('address', '')
        if not address:
            return None

        addr_slug = re.sub(r'[^a-z0-9]', '', address.lower())
        lid = f"import-{addr_slug[:50]}"

        price_display = item.get('price', '') or ''
        price_low, price_high = self._parse_price(price_display)

        # Extract suburb from address
        suburb = ''
        parts = address.split(',')
        if len(parts) >= 2:
            suburb = parts[-1].strip()

        return {
            'id': lid,
            'source': 'import',
            'url': '',
            'address': address,
            'suburb': suburb,
            'state': 'NSW',
            'postcode': '',
            'region_name': region_name or 'Sydney - St George',
            'price_display': price_display or 'Contact Agent',
            'price_low': price_low,
            'price_high': price_high,
            'property_type': 'house',
            'bedrooms': 0,
            'bathrooms': 0,
            'parking': 0,
            'land_size_sqm': item.get('landSize'),
            'building_size_sqm': None,
            'frontage_m': None,
            'headline': '',
            'description': item.get('notes', ''),
            'features_text': '',
            'agent_name': '',
            'agent_phone': '',
            'agency': '',
            'lat': None,
            'lng': None,
            'zoning': None,
            'year_built': None,
            'listing_date': scrape_date,
            'auction_date': None,
            'days_on_market': None,
            'status': 'active',
            'raw_json': json.dumps(item),
        }

    def _parse_price(self, display: str) -> tuple:
        """Extract numeric price from display string."""
        if not display or display.lower() in ('contact agent', 'auction', 'unknown', ''):
            return None, None
        cleaned = display.replace('$', '').replace(',', '').strip()

        # Range: "$2,250,000 - $2,300,000" or "$1.5M - $2.5M"
        range_match = re.search(r'([\d.]+)\s*[mM]?\s*[-–to]+\s*\$?\s*([\d.]+)\s*[mM]?', cleaned)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            if low < 1000:
                low *= 1_000_000
            if high < 1000:
                high *= 1_000_000
            return int(low), int(high)

        # Single: "$1,700,000" or "Guide $1,700,000" or "$1.7M"
        single_match = re.search(r'([\d.]+)\s*[mM]?', cleaned)
        if single_match:
            val = float(single_match.group(1))
            if val < 1000:
                val *= 1_000_000
            return int(val), int(val)

        return None, None
