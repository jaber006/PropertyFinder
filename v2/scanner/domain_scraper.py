"""
Domain.com.au Web Scraper

Fallback/supplement to the official API.
Scrapes Domain search results pages for listing data.
Uses __NEXT_DATA__ JSON embedded in the page when available.
"""

import re
import time
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime


class DomainWebScraper:
    """Scrape property listings from Domain.com.au search pages."""

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
        """Build Domain search URL from region criteria."""
        suburb_slug = suburb.lower().replace(' ', '-')
        state_slug = state.lower()

        price_min = region.get('price_min', '')
        price_max = region.get('price_max', '')

        # Map property types
        type_map = {
            'house': 'house',
            'townhouse': 'town-house',
            'duplex': 'duplex,semi-detached',
            'villa': 'villa',
            'land': 'vacant-land',
        }
        ptypes = ','.join(type_map.get(t, t) for t in region.get('property_types', ['house']))

        url = f"https://www.domain.com.au/sale/{suburb_slug}-{state_slug}/"
        params = []
        if price_min or price_max:
            params.append(f"price={price_min}-{price_max}")
        if ptypes:
            params.append(f"ptype={ptypes}")
        if page > 1:
            params.append(f"page={page}")

        if params:
            url += '?' + '&'.join(params)
        return url

    def scrape_region(self, region: Dict) -> List[Dict]:
        """Scrape all suburbs in a region."""
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
        """Scrape listings for a single suburb."""
        all_listings = []

        for page in range(1, self.max_pages + 1):
            url = self.build_search_url(suburb, state, region, page)
            print(f"  🌐 Domain web: {suburb} ({state}) p{page}")

            try:
                resp = self.session.get(url, timeout=60)
                if resp.status_code == 403:
                    print(f"     ⚠️  Blocked (403) — Domain may require browser")
                    break
                if resp.status_code == 404:
                    print(f"     ℹ️  No results page (404)")
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
        """Extract listings from Domain HTML page."""
        soup = BeautifulSoup(html, 'lxml')
        listings = []

        # Try __NEXT_DATA__ first (most reliable)
        next_data_tag = soup.find('script', id='__NEXT_DATA__')
        if next_data_tag and next_data_tag.string:
            try:
                next_data = json.loads(next_data_tag.string)
                component_props = (next_data.get('props', {})
                                   .get('pageProps', {})
                                   .get('componentProps', {}))
                listings_map = component_props.get('listingsMap', {})

                for item in listings_map.values():
                    parsed = self._parse_next_data_listing(item, suburb, state, region)
                    if parsed:
                        listings.append(parsed)

                if listings:
                    return listings
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        # Fallback: parse HTML cards
        cards = soup.select(
            '[data-testid*="listing-card-wrapper"], '
            'li[data-testid^="listing-"]'
        )
        for card in cards:
            parsed = self._parse_html_card(card, suburb, state, region)
            if parsed:
                listings.append(parsed)

        return listings

    def _parse_next_data_listing(self, item: Dict, suburb: str, state: str, region: Dict) -> Optional[Dict]:
        """Parse a listing from __NEXT_DATA__ JSON."""
        model = item.get('listingModel')
        if not model:
            return None

        lid = model.get('id') or model.get('listingId')
        if not lid:
            return None

        addr = model.get('address', {})
        address = addr.get('displayAddress') or addr.get('displayableAddress') or addr.get('street', 'Unknown')
        features = model.get('features', {})

        price_display = model.get('price', 'Contact Agent')
        price_low, price_high = self._parse_price(price_display)

        url_path = model.get('url', '')
        listing_url = f"https://www.domain.com.au{url_path}" if url_path.startswith('/') else url_path

        return {
            'id': f"domain-{lid}",
            'source': 'domain_web',
            'url': listing_url or f"https://www.domain.com.au/{lid}",
            'address': address,
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

    def _parse_html_card(self, card, suburb: str, state: str, region: Dict) -> Optional[Dict]:
        """Parse a listing from an HTML card element."""
        # Find listing link
        link = card.find('a', href=True)
        if not link:
            return None

        href = link.get('href', '')
        id_match = re.search(r'(\d{7,})', href)
        if not id_match:
            return None

        lid = id_match.group(1)

        # Address
        addr_el = card.select_one('[data-testid="listing-card-address"], [data-testid="address-line1"]')
        address = addr_el.get_text(strip=True) if addr_el else link.get('aria-label', 'Unknown')

        # Price
        price_el = card.select_one('[data-testid="listing-card-price"]')
        price_text = price_el.get_text(strip=True) if price_el else 'Contact Agent'
        price_low, price_high = self._parse_price(price_text)

        # Features
        feat_el = card.select_one('[data-testid="property-features"]')
        feat_text = feat_el.get_text() if feat_el else ''
        beds = int(m.group(1)) if (m := re.search(r'(\d+)\s*[Bb]ed', feat_text)) else 0
        baths = int(m.group(1)) if (m := re.search(r'(\d+)\s*[Bb]ath', feat_text)) else 0
        cars = int(m.group(1)) if (m := re.search(r'(\d+)\s*[Cc]ar', feat_text)) else 0

        listing_url = href if href.startswith('http') else f"https://www.domain.com.au{href}"

        return {
            'id': f"domain-{lid}",
            'source': 'domain_web',
            'url': listing_url,
            'address': address,
            'suburb': suburb,
            'state': state,
            'postcode': '',
            'region_name': region.get('name', ''),
            'price_display': price_text,
            'price_low': price_low,
            'price_high': price_high,
            'property_type': 'house',
            'bedrooms': beds,
            'bathrooms': baths,
            'parking': cars,
            'land_size_sqm': None,
            'building_size_sqm': None,
            'frontage_m': None,
            'headline': '',
            'description': '',
            'features_text': feat_text,
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
