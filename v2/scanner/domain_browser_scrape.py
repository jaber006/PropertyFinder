#!/usr/bin/env python3
"""
Domain.com.au Browser Scraper — Full suburb sweep via Playwright.

Scrapes Domain search results using headless Chromium, extracting listing data
from __NEXT_DATA__ JSON embedded in each page.

Usage:
    python scanner/domain_browser_scrape.py
"""

import json
import time
import os
import re
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

# All target suburbs with postcodes
SUBURBS = {
    # Primary (Bayside Council — near Al Zahra College)
    'Arncliffe':       {'postcode': '2205', 'state': 'NSW', 'tier': 'primary'},
    'Banksia':         {'postcode': '2216', 'state': 'NSW', 'tier': 'primary'},
    'Bexley':          {'postcode': '2207', 'state': 'NSW', 'tier': 'primary'},
    'Bexley North':    {'postcode': '2207', 'state': 'NSW', 'tier': 'primary'},
    'Rockdale':        {'postcode': '2216', 'state': 'NSW', 'tier': 'primary'},
    'Wolli Creek':     {'postcode': '2205', 'state': 'NSW', 'tier': 'primary'},
    'Turrella':        {'postcode': '2205', 'state': 'NSW', 'tier': 'primary'},
    'Bardwell Park':   {'postcode': '2207', 'state': 'NSW', 'tier': 'primary'},
    'Bardwell Valley': {'postcode': '2207', 'state': 'NSW', 'tier': 'primary'},
    # Secondary (adjacent — ripple effect zones)
    'Hurstville':      {'postcode': '2220', 'state': 'NSW', 'tier': 'secondary'},
    'Kogarah':         {'postcode': '2217', 'state': 'NSW', 'tier': 'secondary'},
    'Carlton':         {'postcode': '2218', 'state': 'NSW', 'tier': 'secondary'},
    'Kyeemagh':        {'postcode': '2216', 'state': 'NSW', 'tier': 'secondary'},
    'Kingsgrove':      {'postcode': '2208', 'state': 'NSW', 'tier': 'secondary'},
    'Beverly Hills':   {'postcode': '2209', 'state': 'NSW', 'tier': 'secondary'},
    'Narwee':          {'postcode': '2209', 'state': 'NSW', 'tier': 'secondary'},
    'Riverwood':       {'postcode': '2210', 'state': 'NSW', 'tier': 'secondary'},
}

# Search parameters
PRICE_MIN = 800000
PRICE_MAX = 3000000
PROPERTY_TYPES = 'house,town-house,duplex,semi-detached'
MAX_PAGES = 5  # Domain shows ~20 per page, max 5 pages = 100 per suburb
DELAY_BETWEEN_PAGES = 3  # seconds
DELAY_BETWEEN_SUBURBS = 4  # seconds


def build_url(suburb, info, page=1):
    """Build Domain search URL for a suburb."""
    slug = suburb.lower().replace(' ', '-')
    state = info['state'].lower()
    postcode = info['postcode']
    
    url = f"https://www.domain.com.au/sale/{slug}-{state}-{postcode}/"
    params = []
    params.append(f"price={PRICE_MIN}-{PRICE_MAX}")
    params.append(f"ptype={PROPERTY_TYPES}")
    if page > 1:
        params.append(f"page={page}")
    url += '?' + '&'.join(params)
    return url


def extract_listings_from_page(page_obj, suburb, info):
    """Extract listings from current page's __NEXT_DATA__."""
    nd_raw = page_obj.evaluate("""() => {
        const el = document.getElementById('__NEXT_DATA__');
        return el ? el.textContent : null;
    }""")
    
    if not nd_raw:
        return [], 0, 0
    
    data = json.loads(nd_raw)
    page_props = data.get('props', {}).get('pageProps', {})
    
    # Check for error
    if page_props.get('statusCode') in (404, 500):
        return [], 0, 0
    
    component_props = page_props.get('componentProps', {})
    listings_map = component_props.get('listingsMap', {})
    total_pages = component_props.get('totalPages', 1) or 1
    
    listings = []
    for key, item in listings_map.items():
        model = item.get('listingModel')
        if not model:
            continue
        
        # ID is at the item level, not inside listingModel
        lid = item.get('id') or key
        if not lid:
            continue
        
        addr = model.get('address', {})
        features = model.get('features', {})
        branding = model.get('branding', {})
        
        # Address — Domain gives street + suburb separately
        street = addr.get('street', '')
        sub = addr.get('suburb', suburb)
        st = addr.get('state', info['state'])
        pc = addr.get('postcode', info['postcode'])
        display_addr = f"{street}, {sub} {st} {pc}".strip() if street else f"{sub} {st} {pc}"
        
        # Price
        price_display = model.get('price', 'Contact Agent')
        price_low, price_high = parse_price(price_display)
        
        # URL
        url_path = model.get('url', '')
        listing_url = f"https://www.domain.com.au{url_path}" if url_path.startswith('/') else url_path
        if not listing_url:
            listing_url = f"https://www.domain.com.au/{lid}"
        
        # Property type - from features, not model level
        prop_type = (features.get('propertyType', '') or model.get('propertyType', '') or '').lower()
        if not prop_type:
            prop_type = 'house'
        
        listing = {
            'id': f"domain-{lid}",
            'source': 'domain_browser',
            'url': listing_url,
            'address': display_addr,
            'suburb': addr.get('suburb', suburb),
            'state': addr.get('state', info['state']),
            'postcode': addr.get('postcode', info['postcode']),
            'region_name': 'Sydney - St George',
            'price_display': price_display,
            'price_low': price_low,
            'price_high': price_high,
            'property_type': prop_type,
            'bedrooms': features.get('beds', 0) or 0,
            'bathrooms': features.get('baths', 0) or 0,
            'parking': features.get('parking', 0) or 0,
            'land_size_sqm': features.get('landSize'),
            'building_size_sqm': features.get('buildingSize'),
            'frontage_m': None,
            'headline': model.get('headline', ''),
            'description': (model.get('description', '') or '')[:500],
            'features_text': json.dumps(features) if features else '',
            'agent_name': ', '.join(a.get('agentName', '') for a in branding.get('agents', []) if a.get('agentName')) or '',
            'agent_phone': '',
            'agency': branding.get('brandName', '') or branding.get('agencyName', ''),
            'lat': addr.get('lat'),
            'lng': addr.get('lng'),
            'zoning': None,
            'year_built': None,
            'listing_date': model.get('listingDate'),
            'auction_date': model.get('auctionDate'),
            'days_on_market': None,
            'status': 'active',
            'raw_json': json.dumps(item),
            'tier': info['tier'],
        }
        listings.append(listing)
    
    return listings, total_pages, len(listings_map)


def parse_price(display):
    """Extract numeric price from display string."""
    if not display:
        return None, None
    cleaned = display.replace('$', '').replace(',', '').strip()
    
    # Ignore non-price strings
    lower = cleaned.lower()
    if lower in ('contact agent', 'auction', 'unknown', '', 'price on request', 'by negotiation'):
        return None, None
    
    # Range
    range_match = re.search(r'([\d.]+)\s*[mM]?\s*[-\u2013to]+\s*\$?\s*([\d.]+)\s*[mM]?', cleaned)
    if range_match:
        low = float(range_match.group(1))
        high = float(range_match.group(2))
        if low < 1000:
            low *= 1_000_000
        if high < 1000:
            high *= 1_000_000
        return int(low), int(high)
    
    # Single
    single_match = re.search(r'([\d.]+)\s*[mM]?', cleaned)
    if single_match:
        val = float(single_match.group(1))
        if val < 1000:
            val *= 1_000_000
        return int(val), int(val)
    
    return None, None


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    output_dir = Path(__file__).parent.parent / 'data'
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 60)
    print("Domain.com.au Browser Scraper")
    print(f"Date: {today}")
    print(f"Suburbs: {len(SUBURBS)}")
    print(f"Price range: ${PRICE_MIN:,} - ${PRICE_MAX:,}")
    print(f"Property types: {PROPERTY_TYPES}")
    print("=" * 60)
    
    all_listings = []
    suburb_stats = {}
    
    pw = sync_playwright().start()
    try:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-AU',
        )
        page = ctx.new_page()
        
        for suburb, info in SUBURBS.items():
            print(f"\n--- {suburb} ({info['tier']}) ---", flush=True)
            suburb_listings = []
            
            total_pages = 1
            for pg in range(1, MAX_PAGES + 1):
                if pg > total_pages:
                    break
                url = build_url(suburb, info, pg)
                print(f"  Page {pg}/{total_pages}: {url}", flush=True)
                
                try:
                    page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    time.sleep(DELAY_BETWEEN_PAGES)
                    
                    listings, tp, raw_count = extract_listings_from_page(page, suburb, info)
                    total_pages = tp
                    suburb_listings.extend(listings)
                    print(f"    -> {len(listings)} listings (page {pg}/{total_pages})", flush=True)
                    
                    if len(listings) == 0:
                        break
                        
                except Exception as e:
                    print(f"    ERROR: {e}", flush=True)
                    break
                
                time.sleep(DELAY_BETWEEN_PAGES)
            
            # Deduplicate within suburb
            seen = set()
            unique = []
            for l in suburb_listings:
                if l['id'] not in seen:
                    seen.add(l['id'])
                    unique.append(l)
            
            suburb_stats[suburb] = len(unique)
            all_listings.extend(unique)
            print(f"  Total for {suburb}: {len(unique)}", flush=True)
            
            time.sleep(DELAY_BETWEEN_SUBURBS)
    
    except Exception as e:
        print(f"\n!!! SCRAPER ERROR: {e}", flush=True)
        print(f"    Saving {len(all_listings)} listings collected so far...", flush=True)
    finally:
        try:
            browser.close()
        except:
            pass
        try:
            pw.stop()
        except:
            pass
    
    # Global dedup
    seen = set()
    unique_all = []
    for l in all_listings:
        if l['id'] not in seen:
            seen.add(l['id'])
            unique_all.append(l)
    
    # Save results
    output_file = output_dir / f'domain-browser-scrape-{today}.json'
    output_data = {
        'scrape_date': today,
        'source': 'domain_browser',
        'criteria': {
            'price_min': PRICE_MIN,
            'price_max': PRICE_MAX,
            'property_types': PROPERTY_TYPES,
            'suburbs': list(SUBURBS.keys()),
        },
        'suburb_stats': suburb_stats,
        'total_unique': len(unique_all),
        'listings': unique_all,
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    # Also save to parent data dir for import
    parent_output = Path(__file__).parent.parent.parent / 'data' / f'domain-browser-scrape-{today}.json'
    parent_output.parent.mkdir(exist_ok=True)
    with open(parent_output, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 60}")
    print(f"SCRAPE COMPLETE")
    print(f"{'=' * 60}")
    print(f"Total unique listings: {len(unique_all)}")
    print(f"\nBy suburb:")
    for sub, count in sorted(suburb_stats.items(), key=lambda x: -x[1]):
        tier = SUBURBS[sub]['tier']
        print(f"  {sub:<20} {count:>3} ({tier})")
    print(f"\nSaved to: {output_file}")
    print(f"Also to:  {parent_output}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
