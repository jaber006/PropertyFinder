"""
Domain.com.au API Scanner

Uses the official Domain API for listing search.
- Listings Management (Sandbox) — APPROVED, 500 calls/day
- Agents & Listings — PENDING (handled gracefully)
- Properties & Locations — PENDING (handled gracefully)
- Price Estimation — PENDING (handled gracefully)
"""

import os
import re
import time
import json
import requests
from typing import List, Dict, Optional, Any
from datetime import datetime


class DomainAPIScanner:
    """Scanner using the official Domain.com.au API."""

    BASE_URL = "https://api.domain.com.au"
    SEARCH_ENDPOINT = "/v1/listings/residential/_search"  # Agents & Listings API (pending)

    def __init__(self, api_key: str = None, config: Dict = None):
        self.api_key = api_key or os.getenv('DOMAIN_API_KEY', '')
        self.config = config or {}
        self.session = requests.Session()
        self.session.headers.update({
            'X-Api-Key': self.api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        self._call_count = 0
        self._delay = self.config.get('scanner', {}).get('delay_between_requests_sec', 2.0)

    def _api_call(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """Make an API call with rate limiting and error handling."""
        url = f"{self.BASE_URL}{endpoint}"
        self._call_count += 1

        try:
            if method == 'GET':
                resp = self.session.get(url, **kwargs)
            else:
                resp = self.session.post(url, **kwargs)

            if resp.status_code == 200:
                return resp
            elif resp.status_code == 401:
                print("  ❌ Domain API: Unauthorized — check API key")
            elif resp.status_code == 403:
                print(f"  ⚠️  Domain API: Forbidden on {endpoint} — API may not be approved yet")
            elif resp.status_code == 429:
                print("  ⏳ Domain API: Rate limited — waiting 60s")
                time.sleep(60)
                return self._api_call(method, endpoint, **kwargs)
            else:
                print(f"  ❌ Domain API: {resp.status_code} on {endpoint}")
                if resp.text:
                    print(f"     {resp.text[:200]}")
            return None

        except requests.RequestException as e:
            print(f"  ❌ Domain API request failed: {e}")
            return None

    def search_listings(self, region: Dict) -> List[Dict]:
        """
        Search for listings in a region using Domain API.
        Uses the residential listing search endpoint.
        """
        suburbs = region.get('suburbs', [])
        state = region.get('state', 'NSW')
        price_min = region.get('price_min', 0)
        price_max = region.get('price_max', 10000000)
        property_types = region.get('property_types', ['house'])
        min_land = region.get('min_land_sqm', 0)

        # Map property types to Domain API format
        type_map = {
            'house': 'House',
            'townhouse': 'Townhouse',
            'duplex': 'DuplexSemi',
            'villa': 'Villa',
            'land': 'VacantLand',
        }
        api_types = [type_map.get(t, t.title()) for t in property_types]

        all_listings = []
        page_size = self.config.get('scanner', {}).get('domain_api_page_size', 100)
        max_pages = self.config.get('scanner', {}).get('max_pages_per_suburb', 3)

        # Search by suburb batches (API allows multiple locations)
        # Batch suburbs into groups of 10
        for i in range(0, len(suburbs), 10):
            suburb_batch = suburbs[i:i+10]
            locations = [{'state': state, 'suburb': s} for s in suburb_batch]

            payload = {
                'listingType': 'Sale',
                'propertyTypes': api_types,
                'minPrice': price_min,
                'maxPrice': price_max,
                'minLandArea': min_land if min_land > 0 else None,
                'locations': locations,
                'pageSize': page_size,
                'sort': {
                    'sortKey': 'DateUpdated',
                    'direction': 'Descending'
                }
            }
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}

            batch_name = ', '.join(suburb_batch[:3])
            if len(suburb_batch) > 3:
                batch_name += f' +{len(suburb_batch)-3} more'
            print(f"  🔍 Domain API: {batch_name} ({state})")

            for page in range(1, max_pages + 1):
                payload['pageNumber'] = page
                resp = self._api_call('POST', self.SEARCH_ENDPOINT, json=payload)

                if resp is None:
                    break

                data = resp.json()
                if not data:
                    break

                for item in data:
                    parsed = self._parse_listing(item, region)
                    if parsed:
                        all_listings.append(parsed)

                print(f"     Page {page}: {len(data)} listings")

                # Stop if we got fewer than page size (no more pages)
                if len(data) < page_size:
                    break

                time.sleep(self._delay)

            time.sleep(self._delay)

        return all_listings

    def _parse_listing(self, raw: Dict, region: Dict) -> Optional[Dict]:
        """Parse a raw Domain API listing into our standard format."""
        listing = raw.get('listing', raw)
        lid = listing.get('id')
        if not lid:
            return None

        props = listing.get('propertyDetails', {})
        addr_obj = props.get('address', {})
        price_details = listing.get('priceDetails', {})

        address = (props.get('displayableAddress') or
                   addr_obj.get('displayAddress') or
                   self._build_address(addr_obj))

        suburb = addr_obj.get('suburb', '')
        state = addr_obj.get('state', region.get('state', ''))
        postcode = addr_obj.get('postcode', '')

        price_display = price_details.get('displayPrice', 'Contact Agent')
        price_low, price_high = self._parse_price(price_display)

        lat = props.get('latitude') or addr_obj.get('latitude')
        lng = props.get('longitude') or addr_obj.get('longitude')

        headline = listing.get('headline', '')
        description = listing.get('summaryDescription', '') or listing.get('description', '')

        # Listing date / days on market
        listing_date = listing.get('dateListed') or listing.get('dateUpdated')
        dom = None
        if listing_date:
            try:
                listed = datetime.fromisoformat(listing_date.replace('Z', '+00:00'))
                dom = (datetime.now(listed.tzinfo) - listed).days
            except (ValueError, TypeError):
                pass

        return {
            'id': f"domain-{lid}",
            'source': 'domain_api',
            'url': f"https://www.domain.com.au/{listing.get('listingSlug', lid)}",
            'address': address,
            'suburb': suburb,
            'state': state,
            'postcode': postcode,
            'region_name': region.get('name', ''),
            'price_display': price_display,
            'price_low': price_low,
            'price_high': price_high,
            'property_type': props.get('propertyType', '').lower() or 'house',
            'bedrooms': props.get('bedrooms', 0),
            'bathrooms': props.get('bathrooms', 0),
            'parking': props.get('carSpaces', 0),
            'land_size_sqm': props.get('landArea'),
            'building_size_sqm': props.get('buildingArea'),
            'frontage_m': None,  # Not available from API
            'headline': headline,
            'description': description,
            'features_text': '',
            'agent_name': self._get_agent(listing),
            'agent_phone': self._get_agent_phone(listing),
            'agency': listing.get('advertiser', {}).get('name', ''),
            'lat': lat,
            'lng': lng,
            'zoning': None,  # Would need Properties & Locations API
            'year_built': None,
            'listing_date': listing_date,
            'auction_date': listing.get('auctionSchedule', {}).get('time') if listing.get('auctionSchedule') else None,
            'days_on_market': dom,
            'status': 'active',
            'raw_json': json.dumps(raw)
        }

    def _build_address(self, addr: Dict) -> str:
        """Build display address from components."""
        parts = []
        if addr.get('streetNumber'):
            parts.append(addr['streetNumber'])
        if addr.get('street'):
            parts.append(addr['street'])
        if addr.get('suburb'):
            parts.append(addr['suburb'])
        if addr.get('state'):
            parts.append(addr['state'])
        if addr.get('postcode'):
            parts.append(addr['postcode'])
        return ' '.join(parts) if parts else 'Unknown'

    def _get_agent(self, listing: Dict) -> str:
        contacts = listing.get('advertiser', {}).get('contacts', [])
        if contacts:
            return contacts[0].get('name', '')
        return ''

    def _get_agent_phone(self, listing: Dict) -> str:
        contacts = listing.get('advertiser', {}).get('contacts', [])
        if contacts:
            phones = contacts[0].get('phoneNumbers', [])
            if phones:
                return phones[0].get('number', '')
        return ''

    def _parse_price(self, display: str) -> tuple:
        """Extract numeric price from display string."""
        if not display:
            return None, None
        cleaned = display.replace('$', '').replace(',', '').strip()

        # Range: "$1.3M - $1.8M" or "1300000 - 1800000"
        range_match = re.search(r'([\d.]+)\s*[mM]?\s*[-–to]+\s*\$?\s*([\d.]+)\s*[mM]?', cleaned)
        if range_match:
            low = float(range_match.group(1))
            high = float(range_match.group(2))
            if low < 1000:
                low *= 1_000_000
            if high < 1000:
                high *= 1_000_000
            return int(low), int(high)

        # Single: "$1.8M" or "1800000"
        single_match = re.search(r'([\d.]+)\s*[mM]?', cleaned)
        if single_match:
            val = float(single_match.group(1))
            if val < 1000:
                val *= 1_000_000
            return int(val), int(val)

        return None, None

    # ─── Pending API Interfaces ──────────────────────────────────────────

    def get_property_details(self, property_id: str) -> Optional[Dict]:
        """
        Get detailed property info (zoning, features, etc.)
        Uses Properties & Locations API — PENDING APPROVAL.
        """
        resp = self._api_call('GET', f'/properties/{property_id}')
        if resp:
            return resp.json()
        print(f"  ℹ️  Properties API not yet available for {property_id}")
        return None

    def get_price_estimate(self, property_id: str) -> Optional[Dict]:
        """
        Get automated price estimate.
        Uses Price Estimation API — PENDING APPROVAL.
        """
        resp = self._api_call('GET', f'/properties/{property_id}/priceEstimate')
        if resp:
            return resp.json()
        print(f"  ℹ️  Price Estimation API not yet available for {property_id}")
        return None

    def get_suburb_performance(self, state: str, suburb: str) -> Optional[Dict]:
        """
        Get suburb median prices and performance data.
        Uses Properties & Locations API — PENDING APPROVAL.
        """
        resp = self._api_call(
            'GET',
            f'/suburbPerformanceStatistics/{state}/{suburb}',
            params={'propertyCategory': 'house', 'chronologicalSpan': 5, 'tPlusFrom': 1, 'tPlusTo': 4}
        )
        if resp:
            return resp.json()
        print(f"  ℹ️  Suburb performance API not yet available for {suburb}")
        return None

    def search_sold(self, suburb: str, state: str, months: int = 12) -> List[Dict]:
        """
        Search sold listings.
        Uses Agents & Listings API — PENDING APPROVAL.
        """
        payload = {
            'listingType': 'Sold',
            'propertyTypes': ['House'],
            'locations': [{'state': state, 'suburb': suburb}],
            'pageSize': 100,
            'sort': {'sortKey': 'DateSold', 'direction': 'Descending'}
        }
        resp = self._api_call('POST', '/residential/search/listing', json=payload)
        if resp:
            return resp.json()
        print(f"  ℹ️  Sold data search not yet available for {suburb}")
        return []

    @property
    def calls_made(self) -> int:
        return self._call_count
