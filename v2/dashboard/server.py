"""
PropertyFinder v2 — Web Dashboard Server

Flask app serving the property dashboard with map view, listing cards,
filters, stats, and feasibility calculator.

Usage:
    python server.py
    # or: python main.py dashboard
"""

import os
import sys
import json
import sqlite3
import random
from datetime import datetime, timedelta
from flask import Flask, jsonify, render_template, request

# Add project root to path so we can import from parent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

app = Flask(__name__, template_folder='templates', static_folder='static')

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'listings_v2.db')

# Suburb centroid coordinates for geocoding
SUBURB_COORDS = {
    'Arncliffe': (-33.9367, 151.1522),
    'Banksia': (-33.9453, 151.1386),
    'Bexley': (-33.9500, 151.1200),
    'Bexley North': (-33.9433, 151.1133),
    'Rockdale': (-33.9533, 151.1369),
    'Hurstville': (-33.9667, 151.1000),
    'Kyeemagh': (-33.9417, 151.1600),
    'Carlton': (-33.9683, 151.1233),
    'Bardwell Park': (-33.9267, 151.1350),
    'Bardwell Valley': (-33.9300, 151.1300),
    'Kogarah': (-33.9717, 151.1333),
    'Turrella': (-33.9300, 151.1433),
    'Wolli Creek': (-33.9267, 151.1533),
    'Beverly Hills': (-33.9467, 151.0833),
    'Mascot': (-33.9267, 151.1933),
    'Kingsgrove': (-33.9400, 151.1000),
}


def get_db():
    """Get a database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def geocode_listing(listing):
    """Add lat/lng to a listing if missing, using suburb centroid + jitter."""
    if listing.get('lat') and listing.get('lng'):
        return listing

    suburb = listing.get('suburb', '')
    coords = SUBURB_COORDS.get(suburb)
    if coords:
        # Add slight random offset so pins don't stack (±0.002 degrees ≈ ±200m)
        # Use listing id as seed for consistency
        seed = hash(listing.get('id', ''))
        rng = random.Random(seed)
        listing['lat'] = coords[0] + rng.uniform(-0.002, 0.002)
        listing['lng'] = coords[1] + rng.uniform(-0.002, 0.002)
        listing['geocoded'] = True
    else:
        listing['lat'] = None
        listing['lng'] = None
        listing['geocoded'] = False

    return listing


def format_listing(row):
    """Convert a DB row to a JSON-friendly dict with geocoding and OSM data."""
    d = dict(row)

    # Parse JSON fields
    for field in ('score_breakdown', 'development_flags', 'feasibility_json', 'osm_json'):
        if d.get(field) and isinstance(d[field], str):
            try:
                d[field] = json.loads(d[field])
            except (json.JSONDecodeError, TypeError):
                pass

    # Geocode if needed (fallback to centroid if no lat/lng from OSM geocoding)
    d = geocode_listing(d)

    # Extract OSM-specific data for the API response
    osm_data = d.get('osm_json') or {}
    if isinstance(osm_data, dict):
        pois = osm_data.get('pois', {})
        # Include lat/lng for each POI so dashboard can render map overlays
        d['nearby_schools'] = [
            {
                'name': s.get('name', ''),
                'distance_m': s.get('distance_m', 0),
                'type': s.get('type', 'unknown'),
                'lat': s.get('lat'),
                'lng': s.get('lng'),
            }
            for s in pois.get('schools', [])[:8]  # Top 8 nearest
        ]
        d['nearby_stations'] = [
            {
                'name': s.get('name', ''),
                'distance_m': s.get('distance_m', 0),
                'lat': s.get('lat'),
                'lng': s.get('lng'),
            }
            for s in pois.get('stations', [])[:5]  # Top 5 nearest
        ]
        road_cls = pois.get('road_classification', {})
        d['road_type'] = road_cls.get('label', 'Unknown') if road_cls else 'Unknown'
        d['road_name'] = road_cls.get('road_name', '') if road_cls else ''
        d['location_score'] = osm_data.get('location_score', 0)
        d['growth_score'] = osm_data.get('growth_score', 0)
        d['location_flags'] = osm_data.get('location_flags', [])
        d['growth_flags'] = osm_data.get('growth_flags', [])
        # Nearby amenities summary with coordinates
        d['nearby_supermarkets'] = [
            {'name': s.get('name', ''), 'distance_m': s.get('distance_m', 0), 'lat': s.get('lat'), 'lng': s.get('lng')}
            for s in pois.get('supermarkets', [])[:3]
        ]
        d['nearby_hospitals'] = [
            {'name': s.get('name', ''), 'distance_m': s.get('distance_m', 0), 'lat': s.get('lat'), 'lng': s.get('lng')}
            for s in pois.get('hospitals', [])[:2]
        ]
        d['nearby_parks'] = [
            {'name': s.get('name', ''), 'distance_m': s.get('distance_m', 0), 'lat': s.get('lat'), 'lng': s.get('lng')}
            for s in pois.get('parks', [])[:3]
        ]

    # Check if new (first_seen within last 24h)
    if d.get('first_seen'):
        try:
            first_seen = datetime.fromisoformat(d['first_seen'])
            d['is_new'] = (datetime.now(tz=None) - first_seen) < timedelta(hours=24)
        except (ValueError, TypeError):
            d['is_new'] = False
    else:
        d['is_new'] = False

    # Remove raw_json to reduce payload (keep osm_json parsed above)
    d.pop('raw_json', None)
    d.pop('description', None)
    d.pop('osm_json', None)  # Already extracted into separate fields

    return d


# ---- Routes ----

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


@app.route('/api/listings')
def api_listings():
    """Get all active listings with optional filters."""
    conn = get_db()
    try:
        query = "SELECT * FROM listings WHERE status = 'active'"
        params = []

        # Filters
        suburbs = request.args.get('suburbs')
        if suburbs:
            suburb_list = [s.strip() for s in suburbs.split(',') if s.strip()]
            if suburb_list:
                placeholders = ','.join(['?' for _ in suburb_list])
                query += f" AND suburb IN ({placeholders})"
                params.extend(suburb_list)

        min_price = request.args.get('min_price', type=int)
        if min_price:
            query += " AND (price_low >= ? OR price_high >= ?)"
            params.extend([min_price, min_price])

        max_price = request.args.get('max_price', type=int)
        if max_price:
            query += " AND (price_low <= ? OR (price_low IS NULL AND price_high <= ?))"
            params.extend([max_price, max_price])

        min_land = request.args.get('min_land', type=float)
        if min_land:
            query += " AND land_size_sqm >= ?"
            params.append(min_land)

        min_score = request.args.get('min_score', type=float)
        if min_score:
            query += " AND development_score >= ?"
            params.append(min_score)

        property_type = request.args.get('property_type')
        if property_type:
            query += " AND property_type = ?"
            params.append(property_type)

        new_only = request.args.get('new_only')
        if new_only == 'true':
            query += " AND first_seen > datetime('now', '-24 hours')"

        query += " ORDER BY development_score DESC"

        rows = conn.execute(query, params).fetchall()
        listings = [format_listing(r) for r in rows]

        return jsonify(listings)
    finally:
        conn.close()


@app.route('/api/listings/<listing_id>')
def api_listing_detail(listing_id):
    """Get a single listing by ID."""
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            return jsonify({'error': 'Not found'}), 404

        # Use format_listing to get full OSM data extraction
        d = format_listing(row)

        # Get price history
        history = conn.execute(
            "SELECT price_display, price_low, price_high, recorded_at FROM price_history WHERE listing_id = ? ORDER BY recorded_at DESC",
            (listing_id,)
        ).fetchall()
        d['price_history'] = [dict(h) for h in history]

        return jsonify(d)
    finally:
        conn.close()


@app.route('/api/stats')
def api_stats():
    """Get dashboard statistics."""
    conn = get_db()
    try:
        # Basic stats
        row = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale,
                COUNT(CASE WHEN first_seen > datetime('now', '-24 hours') THEN 1 END) as new_24h,
                ROUND(AVG(CASE WHEN status = 'active' THEN development_score END), 1) as avg_score,
                MAX(CASE WHEN status = 'active' THEN development_score END) as max_score,
                MIN(CASE WHEN status = 'active' THEN development_score END) as min_score
            FROM listings
        """).fetchone()
        stats = dict(row)

        # Top suburb by avg score
        top_suburb = conn.execute("""
            SELECT suburb, ROUND(AVG(development_score), 1) as avg_score, COUNT(*) as cnt
            FROM listings WHERE status = 'active'
            GROUP BY suburb ORDER BY avg_score DESC LIMIT 1
        """).fetchone()
        stats['top_suburb'] = dict(top_suburb) if top_suburb else None

        # Last scan date
        last_scan = conn.execute(
            "SELECT started_at FROM scan_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        stats['last_scan'] = last_scan['started_at'] if last_scan else None

        # If no scan log, use most recent first_seen
        if not stats['last_scan']:
            last_seen = conn.execute(
                "SELECT MAX(first_seen) as last FROM listings"
            ).fetchone()
            stats['last_scan'] = last_seen['last'] if last_seen else None

        # Suburbs list for filters
        suburbs = conn.execute(
            "SELECT DISTINCT suburb FROM listings WHERE status = 'active' ORDER BY suburb"
        ).fetchall()
        stats['suburbs'] = [s['suburb'] for s in suburbs]

        # Property types for filters
        ptypes = conn.execute(
            "SELECT DISTINCT property_type FROM listings WHERE status = 'active' AND property_type IS NOT NULL ORDER BY property_type"
        ).fetchall()
        stats['property_types'] = [p['property_type'] for p in ptypes]

        # Price range
        price_range = conn.execute("""
            SELECT MIN(price_low) as min_price, MAX(price_high) as max_price
            FROM listings WHERE status = 'active' AND (price_low IS NOT NULL OR price_high IS NOT NULL)
        """).fetchone()
        stats['price_range'] = dict(price_range) if price_range else {'min_price': 0, 'max_price': 5000000}

        # Score distribution
        score_dist = conn.execute("""
            SELECT
                COUNT(CASE WHEN development_score >= 70 THEN 1 END) as hot,
                COUNT(CASE WHEN development_score >= 50 AND development_score < 70 THEN 1 END) as good,
                COUNT(CASE WHEN development_score >= 30 AND development_score < 50 THEN 1 END) as below_avg,
                COUNT(CASE WHEN development_score < 30 THEN 1 END) as poor
            FROM listings WHERE status = 'active'
        """).fetchone()
        stats['score_distribution'] = dict(score_dist)

        return jsonify(stats)
    finally:
        conn.close()


def start_server(port=8050, open_browser=True):
    """Start the Flask development server."""
    if open_browser:
        import webbrowser
        import threading
        def _open():
            import time
            time.sleep(1.5)
            webbrowser.open(f'http://localhost:{port}')
        threading.Thread(target=_open, daemon=True).start()

    print(f"\n{'='*60}")
    print(f"  PropertyFinder Dashboard")
    print(f"  http://localhost:{port}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*60}\n")

    app.run(host='0.0.0.0', port=port, debug=False)


if __name__ == '__main__':
    start_server()
