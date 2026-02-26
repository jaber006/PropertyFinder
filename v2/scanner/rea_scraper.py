"""
realestate.com.au Web Scraper

Scrapes REA search results for property listings.
REA uses a React-based frontend with JSON data embedded in the page.
"""

import re
import time
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Any
from datetime import datetime


class REAScraper:
    """Scrape property listings from realestate.com.au."""

    def __init__(self, config: Dict = None):
        self.config = config or {}
        scanner_cfg = self.config.get('scanner', {})
        self.delay = scanner_cfg.get('delay_between_requests_sec', 2.0)
        self.max_pages = scanner_cfg.get('max_pages_per_suburb', 3)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': scanner_cfg.get('user_agent',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-AU,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })

    def build_search_url(self, suburb: str, state: str, region: Dict, page: int = 1) -> str:
        """
        Build REA search URL.
        Format: https://www.realestate.com.au/buy/property-house-in-arncliffe,+nsw+2205/list-1
        """
        suburb_slug = suburb.lower().replace(' ', '+')
        state_slug = state.lower()

        # Property types
        type_map = {
            'house': 'house',
            'townhouse': 'townhouse',
            'duplex': 'duplex+semi-detached',
            'villa': 'villa',
            'land': 'land',
        }
        ptypes = '+'.join(type_map.get(t, t) for t in region.get('property_types', ['house']))

        price_min = region.get('price_min', '')
        price_max = region.get('price_max', '')
        min_land = region.get('min_land_sqm', '')

        # Build URL
        url = f"https://www.realestate.com.au/buy/property-{ptypes}-between-{price_min}-{price_max}-in-{suburb_slug},+{state_slug}/list-{page}"

        params = []
        if min_land:
            params.append(f"minLandArea={min_land}")

        if params:
            url += '?' + '&'.join(params)

        return url

    def scrape_region(self, region: Dict) -> List[Dict]:
        """Scrape all suburbs in a region from REA."""
        all_listings = []
        state = region.get('state', 'NSW')

        for suburb in region.get('suburbs', []):
            listings = self._scrape_suburb(suburb, state, region)
            all_listings.extend(listings)
            time.sleep(self.delay)

        # Deduplicate
        seen = set()
        unique = []
        for l in all_listings:
            if l['id'] not in seen:
                seen.add(l['id'])
                unique.append(l)

        return unique

    def _scrape_suburb(self, suburb: str, state: str, region: Dict) -> List[Dict]:
        """Scrape listings for a single suburb on REA."""
        all_listings = []

        for page in range(1, self.max_pages + 1):
            url = self.build_search_url(suburb, state, region, page)
            print(f"  🏘️  REA: {suburb} ({state}) p{page}")

            try:
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 403:
                    print(f"     ⚠️  Blocked (403) — REA requires browser-like requests")
                    break
                if resp.status_code == 404:
                    print(f"     ℹ️  No results (404)")
                    break
                if resp.status_code != 200:
                    print(f"     ❌ HTTP {resp.status_code}")
                    break

                listings = self._extract_listings(resp.text, suburb, state, region)
                all_listings.extend(listings)
                print(f"     ✅ {len(listings)} listings")

                if len(listings) == 0:
                    break

            except requests.RequestException as e:
                print(f"     ❌ Request failed: {e}")
                break

            time.sleep(self.delay)

        return all_listings

    def _extract_listings(self, html: str, suburb: str, state: str, region: Dict) -> List[Dict]:
        """Extract listings from REA HTML."""
        soup = BeautifulSoup(html, 'lxml')
        listings = []

        # REA embeds data in a script tag with argonaut format or __NEXT_DATA__
        # Try to find JSON data in script tags
        for script in soup.find_all('script'):
            text = script.string or ''
            if 'listingSearch' in text or 'tieredResults' in text or '"listings"' in text:
                try:
                    # Try to find the JSON object
                    json_match = re.search(r'(\{.*"listings?".*\})', text, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group(1))
                        results = self._find_listings_in_json(data)
                        for item in results:
                            parsed = self._parse_rea_listing(item, suburb, state, region)
                            if parsed:
                                listings.append(parsed)
                except (json.JSONDecodeError, TypeError):
                    continue

        # Also try __NEXT_DATA__ (newer REA pages)
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                results = self._find_listings_in_json(data)
                for item in results:
                    parsed = self._parse_rea_listing(item, suburb, state, region)
                    if parsed and parsed['id'] not in {l['id'] for l in listings}:
                        listings.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

        # Fallback: parse HTML listing cards
        if not listings:
            cards = soup.select('.residential-card, [data-testid="residential-card"], article.residential-card__content')
            for card in cards:
                parsed = self._parse_rea_card(card, suburb, state, region)
                if parsed:
                    listings.append(parsed)

        return listings

    def _find_listings_in_json(self, data: Any, depth: int = 0) -> List[Dict]:
        """Recursively find listing objects in nested JSON."""
        results = []
        if depth > 10:
            return results

        if isinstance(data, dict):
            # Check if this looks like a listing
            if data.get('id') and (data.get('address') or data.get('prettyAddress')):
                results.append(data)
            # Also check for listing arrays
            for key in ('listings', 'results', 'tieredResults', 'exactMatch', 'items'):
                if key in data:
                    sub = data[key]
                    if isinstance(sub, list):
                        for item in sub:
                            results.extend(self._find_listings_in_json(item, depth + 1))
                    elif isinstance(sub, dict):
                        results.extend(self._find_listings_in_json(sub, depth + 1))
            # Recurse into other values
            for k, v in data.items():
                if k not in ('listings', 'results', 'tieredResults', 'exactMatch', 'items'):
                    if isinstance(v, (dict, list)):
                        results.extend(self._find_listings_in_json(v, depth + 1))
        elif isinstance(data, list):
            for item in data:
                results.extend(self._find_listings_in_json(item, depth + 1))

        return results

    def _parse_rea_listing(self, item: Dict, suburb: str, state: str, region: Dict) -> Optional[Dict]:
        """Parse an REA listing from JSON data."""
        lid = item.get('id') or item.get('listingId')
        if not lid:
            return None

        # Address
        addr = item.get('address', {})
        if isinstance(addr, str):
            address = addr
        else:
            address = (addr.get('display', {}).get('fullAddress') or
                       addr.get('prettyAddress') or
                       addr.get('displayAddress') or
                       f"{addr.get('streetAddress', '')} {addr.get('suburb', suburb)}")

        # Price
        price_data = item.get('price', {})
        if isinstance(price_data, str):
            price_display = price_data
        else:
            price_display = (price_data.get('display') or
                             price_data.get('displayPrice') or
                             item.get('priceText', 'Contact Agent'))
        price_low, price_high = self._parse_price(price_display)

        # Features
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

        # Land size
        prop_size = item.get('propertySize', {})
        land_size = None
        if isinstance(prop_size, dict):
            land_obj = prop_size.get('land', {})
            if isinstance(land_obj, dict):
                land_size = land_obj.get('displayValue') or land_obj.get('value')
                if isinstance(land_size, str):
                    m = re.search(r'([\d,.]+)', land_size)
                    land_size = float(m.group(1).replace(',', '')) if m else None
        if land_size is None:
            land_size = item.get('landSize') or item.get('landArea')

        # URL
        url_path = item.get('_links', {}).get('canonical', {}).get('href', '') or item.get('prettyUrl', '') or item.get('url', '')
        if url_path and not url_path.startswith('http'):
            url_path = f"https://www.realestate.com.au{url_path}"
        if not url_path:
            url_path = f"https://www.realestate.com.au/{lid}"

        # Description
        description = item.get('description', '') or item.get('summaryDescription', '')

        return {
            'id': f"rea-{lid}",
            'source': 'rea_web',
            'url': url_path,
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
            'description': description,
            'features_text': '',
            'agent_name': self._get_rea_agent(item),
            'agent_phone': '',
            'agency': self._get_rea_agency(item),
            'lat': item.get('address', {}).get('location', {}).get('latitude') if isinstance(item.get('address'), dict) else None,
            'lng': item.get('address', {}).get('location', {}).get('longitude') if isinstance(item.get('address'), dict) else None,
            'zoning': None,
            'year_built': None,
            'listing_date': item.get('dateListed') or item.get('listingDate'),
            'auction_date': item.get('auctionDate'),
            'days_on_market': None,
            'status': 'active',
            'raw_json': json.dumps(item)
        }

    def _parse_rea_card(self, card, suburb: str, state: str, region: Dict) -> Optional[Dict]:
        """Parse an REA listing from an HTML card element."""
        link = card.find('a', href=True)
        if not link:
            return None

        href = link.get('href', '')
        id_match = re.search(r'(\d{8,})', href)
        if not id_match:
            return None

        lid = id_match.group(1)
        address = card.select_one('.residential-card__address-heading, .property-card-address')
        address_text = address.get_text(strip=True) if address else 'Unknown'

        price_el = card.select_one('.property-price, .residential-card__price')
        price_text = price_el.get_text(strip=True) if price_el else 'Contact Agent'
        price_low, price_high = self._parse_price(price_text)

        listing_url = href if href.startswith('http') else f"https://www.realestate.com.au{href}"

        return {
            'id': f"rea-{lid}",
            'source': 'rea_web',
            'url': listing_url,
            'address': address_text,
            'suburb': suburb,
            'state': state,
            'postcode': '',
            'region_name': region.get('name', ''),
            'price_display': price_text,
            'price_low': price_low,
            'price_high': price_high,
            'property_type': 'house',
            'bedrooms': 0,
            'bathrooms': 0,
            'parking': 0,
            'land_size_sqm': None,
            'building_size_sqm': None,
            'frontage_m': None,
            'headline': '',
            'description': '',
            'features_text': '',
            'agent_name': '',
            'agent_phone': '',
            'agency': '',
            'lat': None,
            'lng': None,
            'zoning': None,
            'year_built': None,
            'listing_date': None,
            'auction_date': None,
            'days_on_market': None,
            'status': 'active',
            'raw_json': ''
        }

    def _get_rea_agent(self, item: Dict) -> str:
        agents = item.get('agents', item.get('lister', []))
        if isinstance(agents, list) and agents:
            agent = agents[0]
            return agent.get('name', '') if isinstance(agent, dict) else str(agent)
        return ''

    def _get_rea_agency(self, item: Dict) -> str:
        agency = item.get('agency', item.get('listerBrand', {}))
        if isinstance(agency, dict):
            return agency.get('name', '') or agency.get('brandName', '')
        return ''

    def _parse_price(self, display: str) -> tuple:
        """Extract numeric price from display string."""
        if not display:
            return None, None
        cleaned = display.replace('$', '').replace(',', '').strip()

        range_match = re.search(r'([\d.]+)\s*[mM]?\s*[-–to]+\s*\$?\s*([\d.]+)\s*[mM]?', cleaned)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            if low < 1000:
                low *= 1_000_000
            if high < 1000:
                high *= 1_000_000
            return int(low), int(high)

        single_match = re.search(r'([\d.]+)\s*[mM]?', cleaned)
        if single_match:
            val = float(single_match.group(1))
            if val < 1000:
                val *= 1_000_000
            return int(val), int(val)

        return None, None


