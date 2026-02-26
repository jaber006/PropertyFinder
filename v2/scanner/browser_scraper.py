"""
Browser-based scraper using Playwright.

Falls back to this when direct HTTP requests are blocked by bot protection.
Requires: pip install playwright && python -m playwright install chromium

Usage from CLI:
    python main.py scan --browser
"""

import re
import json
import time
from typing import List, Dict, Optional, Any
from datetime import datetime


def is_playwright_available() -> bool:
    """Check if Playwright is installed."""
    try:
        from playwright.sync_api import sync_playwright
        return True
    except ImportError:
        return False


class BrowserScraper:
    """Scrape property listings using a real browser via Playwright."""

    def __init__(self, config: Dict = None, headless: bool = True):
        self.config = config or {}
        self.headless = headless
        self._browser = None
        self._context = None
        self._page = None
        self.delay = self.config.get('scanner', {}).get('delay_between_requests_sec', 3.0)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def start(self):
        """Launch browser."""
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._context = self._browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-AU',
        )
        self._page = self._context.new_page()

    def stop(self):
        """Close browser."""
        if self._browser:
            self._browser.close()
        if hasattr(self, '_pw') and self._pw:
            self._pw.stop()

    def scrape_domain_region(self, region: Dict) -> List[Dict]:
        """Scrape Domain.com.au for a region using browser."""
        if not self._page:
            self.start()

        all_listings = []
        state = region.get('state', 'NSW')

        for suburb in region.get('suburbs', []):
            listings = self._scrape_domain_suburb(suburb, state, region)
            all_listings.extend(listings)
            time.sleep(self.delay)

        # Deduplicate
        seen = set()
        return [l for l in all_listings if not (l['id'] in seen or seen.add(l['id']))]

    def _scrape_domain_suburb(self, suburb: str, state: str, region: Dict) -> List[Dict]:
        """Scrape a single suburb from Domain."""
        suburb_slug = suburb.lower().replace(' ', '-')
        state_slug = state.lower()
        price_min = region.get('price_min', '')
        price_max = region.get('price_max', '')

        url = f"https://www.domain.com.au/sale/{suburb_slug}-{state_slug}/?price={price_min}-{price_max}&ptype=house,town-house,duplex,semi-detached"
        print(f"  🌐 Browser: Domain {suburb} ({state})")

        try:
            self._page.goto(url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Extract __NEXT_DATA__
            next_data = self._page.evaluate('''() => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }''')

            listings = []
            if next_data:
                try:
                    data = json.loads(next_data)
                    listings_map = (data.get('props', {})
                                    .get('pageProps', {})
                                    .get('componentProps', {})
                                    .get('listingsMap', {}))

                    for item in listings_map.values():
                        parsed = self._parse_domain_listing(item, suburb, state, region)
                        if parsed:
                            listings.append(parsed)
                except (json.JSONDecodeError, KeyError):
                    pass

            print(f"     ✅ {len(listings)} listings")
            return listings

        except Exception as e:
            print(f"     ❌ {e}")
            return []

    def scrape_rea_region(self, region: Dict) -> List[Dict]:
        """Scrape realestate.com.au for a region using browser."""
        if not self._page:
            self.start()

        all_listings = []
        state = region.get('state', 'NSW')

        for suburb in region.get('suburbs', []):
            listings = self._scrape_rea_suburb(suburb, state, region)
            all_listings.extend(listings)
            time.sleep(self.delay)

        seen = set()
        return [l for l in all_listings if not (l['id'] in seen or seen.add(l['id']))]

    def _scrape_rea_suburb(self, suburb: str, state: str, region: Dict) -> List[Dict]:
        """Scrape a single suburb from REA."""
        suburb_slug = suburb.lower().replace(' ', '+')
        state_slug = state.lower()
        price_min = region.get('price_min', '')
        price_max = region.get('price_max', '')

        url = f"https://www.realestate.com.au/buy/property-house-between-{price_min}-{price_max}-in-{suburb_slug},+{state_slug}/list-1"
        print(f"  🏘️  Browser: REA {suburb} ({state})")

        try:
            self._page.goto(url, wait_until='networkidle', timeout=30000)
            time.sleep(2)

            # Extract listing data from page
            page_content = self._page.content()
            listings = self._extract_rea_listings(page_content, suburb, state, region)
            print(f"     ✅ {len(listings)} listings")
            return listings

        except Exception as e:
            print(f"     ❌ {e}")
            return []

    def _extract_rea_listings(self, html: str, suburb: str, state: str, region: Dict) -> List[Dict]:
        """Extract REA listings from page HTML."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'lxml')
        listings = []

        # Try to find JSON data
        for script in soup.find_all('script'):
            text = script.string or ''
            if '"listings"' in text or '"tieredResults"' in text:
                try:
                    data = json.loads(text)
                    results = self._find_listings_json(data)
                    for item in results:
                        parsed = self._parse_rea_listing(item, suburb, state, region)
                        if parsed:
                            listings.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    continue

        # Also try __NEXT_DATA__
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                results = self._find_listings_json(data)
                existing_ids = {l['id'] for l in listings}
                for item in results:
                    parsed = self._parse_rea_listing(item, suburb, state, region)
                    if parsed and parsed['id'] not in existing_ids:
                        listings.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        return listings

    def _find_listings_json(self, data: Any, depth: int = 0) -> List[Dict]:
        """Recursively find listing objects in JSON."""
        results = []
        if depth > 10:
            return results

        if isinstance(data, dict):
            if data.get('id') and (data.get('address') or data.get('prettyAddress')):
                results.append(data)
            for key in ('listings', 'results', 'tieredResults', 'exactMatch', 'items'):
                if key in data:
                    sub = data[key]
                    if isinstance(sub, list):
                        for item in sub:
                            results.extend(self._find_listings_json(item, depth + 1))
                    elif isinstance(sub, dict):
                        results.extend(self._find_listings_json(sub, depth + 1))
        elif isinstance(data, list):
            for item in data:
                results.extend(self._find_listings_json(item, depth + 1))

        return results

    def _parse_domain_listing(self, item: Dict, suburb: str, state: str, region: Dict) -> Optional[Dict]:
        """Parse Domain listing from __NEXT_DATA__."""
        model = item.get('listingModel')
        if not model:
            return None
        lid = model.get('id') or model.get('listingId')
        if not lid:
            return None

        addr = model.get('address', {})
        features = model.get('features', {})
        price_display = model.get('price', 'Contact Agent')
        price_low, price_high = self._parse_price(price_display)
        url_path = model.get('url', '')

        return {
            'id': f"domain-{lid}",
            'source': 'domain_browser',
            'url': f"https://www.domain.com.au{url_path}" if url_path.startswith('/') else url_path,
            'address': addr.get('displayAddress', addr.get('street', 'Unknown')),
            'suburb': addr.get('suburb', suburb),
            'state': addr.get('state', state),
            'postcode': addr.get('postcode', ''),
            'region_name': region.get('name', ''),
            'price_display': price_display,
            'price_low': price_low,
            'price_high': price_high,
            'property_type': model.get('propertyType', '').lower() or 'house',
            'bedrooms': features.get('beds', 0),
            'bathrooms': features.get('baths', 0),
            'parking': features.get('parking', 0),
            'land_size_sqm': features.get('landSize'),
            'building_size_sqm': features.get('buildingSize'),
            'frontage_m': None,
            'headline': model.get('headline', ''),
            'description': model.get('description', ''),
            'features_text': '',
            'agent_name': model.get('branding', {}).get('agentNames', ''),
            'agent_phone': '',
            'agency': model.get('branding', {}).get('agencyName', ''),
            'lat': addr.get('lat'),
            'lng': addr.get('lng'),
            'zoning': None,
            'year_built': None,
            'listing_date': model.get('listingDate'),
            'auction_date': model.get('auctionDate'),
            'days_on_market': None,
            'status': 'active',
            'raw_json': json.dumps(item)
        }

    def _parse_rea_listing(self, item: Dict, suburb: str, state: str, region: Dict) -> Optional[Dict]:
        """Parse REA listing from JSON."""
        lid = item.get('id') or item.get('listingId')
        if not lid:
            return None

        addr = item.get('address', {})
        if isinstance(addr, str):
            address = addr
        else:
            address = (addr.get('display', {}).get('fullAddress') or
                       addr.get('prettyAddress') or
                       addr.get('displayAddress') or
                       f"{addr.get('streetAddress', '')} {addr.get('suburb', suburb)}")

        price_data = item.get('price', {})
        if isinstance(price_data, str):
            price_display = price_data
        else:
            price_display = (price_data.get('display') or
                             price_data.get('displayPrice') or
                             item.get('priceText', 'Contact Agent'))
        price_low, price_high = self._parse_price(price_display)

        features = item.get('features', item.get('generalFeatures', {}))
        if isinstance(features, list):
            beds = next((f.get('value', 0) for f in features if f.get('type') == 'bedrooms'), 0)
            baths = next((f.get('value', 0) for f in features if f.get('type') == 'bathrooms'), 0)
            cars = next((f.get('value', 0) for f in features if f.get('type') == 'parkingSpaces'), 0)
        elif isinstance(features, dict):
            beds = features.get('bedrooms', features.get('beds', 0)) or 0
            baths = features.get('bathrooms', features.get('baths', 0)) or 0
            cars = features.get('parkingSpaces', features.get('parking', 0)) or 0
        else:
            beds = baths = cars = 0

        land_size = None
        prop_size = item.get('propertySize', {})
        if isinstance(prop_size, dict):
            land_obj = prop_size.get('land', {})
            if isinstance(land_obj, dict):
                land_size = land_obj.get('displayValue') or land_obj.get('value')
                if isinstance(land_size, str):
                    m = re.search(r'([\d,.]+)', land_size)
                    land_size = float(m.group(1).replace(',', '')) if m else None

        url_path = (item.get('_links', {}).get('canonical', {}).get('href', '') or
                    item.get('prettyUrl', '') or item.get('url', ''))
        if url_path and not url_path.startswith('http'):
            url_path = f"https://www.realestate.com.au{url_path}"

        return {
            'id': f"rea-{lid}",
            'source': 'rea_browser',
            'url': url_path or f"https://www.realestate.com.au/{lid}",
            'address': address.strip() if isinstance(address, str) else str(address),
            'suburb': addr.get('suburb', suburb) if isinstance(addr, dict) else suburb,
            'state': addr.get('state', state) if isinstance(addr, dict) else state,
            'postcode': addr.get('postcode', '') if isinstance(addr, dict) else '',
            'region_name': region.get('name', ''),
            'price_display': price_display,
            'price_low': price_low,
            'price_high': price_high,
            'property_type': item.get('propertyType', '').lower() or 'house',
            'bedrooms': int(beds) if beds else 0,
            'bathrooms': int(baths) if baths else 0,
            'parking': int(cars) if cars else 0,
            'land_size_sqm': float(land_size) if land_size else None,
            'building_size_sqm': None,
            'frontage_m': None,
            'headline': item.get('headline', '') or item.get('title', ''),
            'description': item.get('description', '') or item.get('summaryDescription', ''),
            'features_text': '',
            'agent_name': '',
            'agent_phone': '',
            'agency': '',
            'lat': addr.get('location', {}).get('latitude') if isinstance(addr, dict) else None,
            'lng': addr.get('location', {}).get('longitude') if isinstance(addr, dict) else None,
            'zoning': None,
            'year_built': None,
            'listing_date': item.get('dateListed') or item.get('listingDate'),
            'auction_date': item.get('auctionDate'),
            'days_on_market': None,
            'status': 'active',
            'raw_json': json.dumps(item)
        }

    def _parse_price(self, display: str) -> tuple:
        """Parse price from display string."""
        if not display:
            return None, None
        cleaned = display.replace('$', '').replace(',', '').strip()
        range_match = re.search(r'([\d.]+)\s*[mM]?\s*[-\u2013to]+\s*\$?\s*([\d.]+)\s*[mM]?', cleaned)
        if range_match:
            low, high = float(range_match.group(1)), float(range_match.group(2))
            if low < 1000: low *= 1_000_000
            if high < 1000: high *= 1_000_000
            return int(low), int(high)
        single_match = re.search(r'([\d.]+)\s*[mM]?', cleaned)
        if single_match:
            val = float(single_match.group(1))
            if val < 1000: val *= 1_000_000
            return int(val), int(val)
        return None, None
