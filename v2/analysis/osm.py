"""
OSM (OpenStreetMap) Location Intelligence Module

Queries Overpass API for Points of Interest near a property:
- Schools, train stations, bus stops
- Supermarkets, hospitals, parks
- Road classification for the property's street

Also handles geocoding via Nominatim.

Rate limits:
- Overpass API: no hard limit, but be respectful (cache for 24h)
- Nominatim: 1 request per second, cache permanently
"""

import json
import math
import time
import sqlite3
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


# ─── Haversine distance ─────────────────────────────────────────

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in metres between two lat/lng points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─── Suburb centroid fallbacks ───────────────────────────────────

SUBURB_CENTROIDS = {
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
    'Earlwood': (-33.9200, 151.1300),
    'Clemton Park': (-33.9217, 151.1167),
}


# ─── Overpass API queries ────────────────────────────────────────

# Overpass API endpoints (in priority order — use mirrors for reliability)
OVERPASS_ENDPOINTS = [
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",   # Fast, reliable mirror
    "https://overpass-api.de/api/interpreter",                     # Primary (often rate-limited)
    "https://overpass.kumi.systems/api/interpreter",               # Alternative mirror
]
OVERPASS_URL = OVERPASS_ENDPOINTS[0]  # Default to fastest
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# User-Agent for Nominatim (required by their policy — must be descriptive)
USER_AGENT = "PropertyFinder/2.0 (Australian property development analysis tool; https://github.com/jaber006/PropertyFinder)"


def _overpass_query(query: str, timeout: int = 30) -> Optional[dict]:
    """Execute an Overpass API query, trying multiple endpoints on failure."""
    data = urllib.parse.urlencode({'data': query}).encode('utf-8')
    
    for i, endpoint in enumerate(OVERPASS_ENDPOINTS):
        # Shorter timeout for fallback endpoints
        ep_timeout = timeout if i == 0 else 15
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={'User-Agent': USER_AGENT}
        )
        try:
            with urllib.request.urlopen(req, timeout=ep_timeout) as resp:
                body = resp.read().decode('utf-8')
                if not body.strip():
                    continue  # Empty response, try next
                return json.loads(body)
        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            # Don't print for expected failures to reduce noise
            continue
        except json.JSONDecodeError:
            continue
        except Exception:
            continue
    
    return None


def _nominatim_geocode(address: str, suburb: str, state: str = "NSW",
                       country: str = "Australia") -> Optional[Tuple[float, float]]:
    """Geocode an address using Nominatim. Returns (lat, lng) or None."""
    query = f"{address}, {suburb}, {state}, {country}"
    params = urllib.parse.urlencode({
        'q': query,
        'format': 'json',
        'limit': 1,
        'countrycodes': 'au',
    })
    url = f"{NOMINATIM_URL}?{params}"
    req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            results = json.loads(resp.read().decode('utf-8'))
            if results:
                lat = float(results[0]['lat'])
                lon = float(results[0]['lon'])
                return (lat, lon)
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError,
            KeyError, IndexError, ValueError, Exception) as e:
        print(f"    [OSM] Nominatim geocode error for '{query}': {e}")
    return None


def query_pois(lat: float, lng: float) -> Dict:
    """
    Query all Points of Interest near a coordinate using Overpass API.
    Uses two simpler queries for reliability:
    1. Nearby (within 1.5km): schools, stations, bus stops, supermarkets, parks, roads
    2. Far (within 3km): hospitals only
    Returns a dict with categorised POIs and distances.
    """
    # Query 1: Nearby POIs (≤2km radius — covers schools, stations, shops, parks, roads)
    query_nearby = f"""
    [out:json][timeout:60];
    (
      node["amenity"="school"](around:1500,{lat},{lng});
      way["amenity"="school"](around:1500,{lat},{lng});
      node["railway"="station"](around:2000,{lat},{lng});
      node["highway"="bus_stop"](around:500,{lat},{lng});
      node["shop"="supermarket"](around:1000,{lat},{lng});
      way["shop"="supermarket"](around:1000,{lat},{lng});
      node["leisure"="park"](around:500,{lat},{lng});
      way["leisure"="park"](around:500,{lat},{lng});
      way["highway"~"^(primary|trunk|secondary|tertiary|residential|living_street|service|unclassified)$"](around:50,{lat},{lng});
    );
    out center tags;
    """

    # Query 2: Hospitals (wider radius)
    query_hospitals = f"""
    [out:json][timeout:30];
    (
      node["amenity"="hospital"](around:3000,{lat},{lng});
      way["amenity"="hospital"](around:3000,{lat},{lng});
    );
    out center tags;
    """

    # Execute both queries
    result_nearby = _overpass_query(query_nearby)
    result_hospitals = _overpass_query(query_hospitals)
    
    # Merge elements
    all_elements = []
    if result_nearby and 'elements' in result_nearby:
        all_elements.extend(result_nearby['elements'])
    if result_hospitals and 'elements' in result_hospitals:
        all_elements.extend(result_hospitals['elements'])
    
    if not all_elements:
        return _empty_pois()
    
    result = {'elements': all_elements}

    # Categorise results
    pois = {
        'schools': [],
        'stations': [],
        'bus_stops': [],
        'supermarkets': [],
        'hospitals': [],
        'parks': [],
        'roads': [],
    }

    for elem in result['elements']:
        tags = elem.get('tags', {})

        # Get coordinates (node has lat/lon directly, way has center)
        if elem['type'] == 'node':
            elat, elng = elem.get('lat', 0), elem.get('lon', 0)
        elif elem['type'] == 'way':
            center = elem.get('center', {})
            elat, elng = center.get('lat', 0), center.get('lon', 0)
        else:
            continue

        if elat == 0 and elng == 0:
            continue

        dist = haversine_m(lat, lng, elat, elng)
        name = tags.get('name', 'Unknown')

        # Categorise
        if tags.get('amenity') == 'school':
            school_type = 'unknown'
            isced = tags.get('isced:level', '')
            if '1' in isced or 'primary' in name.lower():
                school_type = 'primary'
            elif '2' in isced or '3' in isced or 'high' in name.lower() or 'secondary' in name.lower():
                school_type = 'secondary'
            pois['schools'].append({
                'name': name,
                'type': school_type,
                'distance_m': round(dist),
                'lat': elat,
                'lng': elng,
            })
        elif tags.get('railway') == 'station':
            pois['stations'].append({
                'name': name,
                'distance_m': round(dist),
                'lat': elat,
                'lng': elng,
            })
        elif tags.get('highway') == 'bus_stop':
            pois['bus_stops'].append({
                'name': name,
                'distance_m': round(dist),
            })
        elif tags.get('shop') == 'supermarket':
            pois['supermarkets'].append({
                'name': name,
                'distance_m': round(dist),
            })
        elif tags.get('amenity') == 'hospital':
            pois['hospitals'].append({
                'name': name,
                'distance_m': round(dist),
            })
        elif tags.get('leisure') == 'park':
            pois['parks'].append({
                'name': name,
                'distance_m': round(dist),
            })
        elif tags.get('highway') in (
            'primary', 'trunk', 'secondary', 'tertiary', 'residential',
            'living_street', 'service', 'unclassified'
        ) and tags.get('highway') != 'bus_stop':
            pois['roads'].append({
                'name': name,
                'highway_type': tags['highway'],
                'distance_m': round(dist),
            })

    # Sort each category by distance
    for key in pois:
        pois[key].sort(key=lambda x: x.get('distance_m', 99999))

    # Determine road classification (nearest road)
    pois['road_classification'] = _classify_road(pois['roads'])

    return pois


def _empty_pois() -> Dict:
    """Return an empty POI structure."""
    return {
        'schools': [],
        'stations': [],
        'bus_stops': [],
        'supermarkets': [],
        'hospitals': [],
        'parks': [],
        'roads': [],
        'road_classification': {'type': 'unknown', 'label': 'Unknown', 'score_adj': 0},
    }


def _classify_road(roads: List[Dict]) -> Dict:
    """Classify the nearest road to the property."""
    if not roads:
        return {'type': 'unknown', 'label': 'Unknown', 'score_adj': 0}

    nearest = roads[0]
    hw = nearest.get('highway_type', 'unknown')

    classifications = {
        'trunk': {'label': 'Main Road (trunk)', 'score_adj': -15},
        'primary': {'label': 'Main Road', 'score_adj': -15},
        'secondary': {'label': 'Busy Road', 'score_adj': -10},
        'tertiary': {'label': 'Moderate Road', 'score_adj': -5},
        'residential': {'label': 'Residential', 'score_adj': 0},
        'living_street': {'label': 'Quiet Street', 'score_adj': 5},
        'service': {'label': 'Service/Cul-de-sac', 'score_adj': 8},
        'unclassified': {'label': 'Quiet Road', 'score_adj': 3},
    }

    cls = classifications.get(hw, {'label': hw.title(), 'score_adj': 0})
    return {
        'type': hw,
        'label': cls['label'],
        'road_name': nearest.get('name', 'Unknown'),
        'score_adj': cls['score_adj'],
    }


# ─── Location Scoring ───────────────────────────────────────────

def score_location(pois: Dict) -> Tuple[float, Dict, List[str]]:
    """
    Score location quality based on OSM POI data.
    
    Returns (score, breakdown, flags) where:
    - score: 0-30 (location quality points)
    - breakdown: dict of component scores
    - flags: list of notable location flags
    """
    breakdown = {}
    flags = []

    # 1. Transport proximity: 0-15 points (train station distance)
    transport_score = 0
    stations = pois.get('stations', [])
    if stations:
        nearest_station = stations[0]
        dist = nearest_station['distance_m']
        name = nearest_station['name']
        if dist < 800:
            transport_score = 15
            flags.append(f'🚂 {name} station {dist}m — walking distance')
        elif dist < 1500:
            transport_score = 8
            flags.append(f'🚂 {name} station {dist}m — close')
        elif dist < 2000:
            transport_score = 3
            flags.append(f'🚂 {name} station {dist}m')
    
    # Bus stop bonus (up to +3 if no nearby train)
    bus_stops = pois.get('bus_stops', [])
    if bus_stops and transport_score < 15:
        transport_score = min(15, transport_score + 3)
        if not stations or stations[0]['distance_m'] >= 1500:
            flags.append(f'🚌 {len(bus_stops)} bus stop(s) nearby')

    breakdown['transport'] = transport_score

    # 2. School proximity: 0-5 points
    school_score = 0
    schools = pois.get('schools', [])
    if schools:
        # Count schools within 1km
        close_schools = [s for s in schools if s['distance_m'] < 1000]
        all_schools = schools
        if len(close_schools) >= 3:
            school_score = 5
            flags.append(f'🏫 {len(close_schools)} schools within 1km')
        elif len(close_schools) >= 1:
            school_score = 3
        elif len(all_schools) >= 1:
            school_score = 1
    breakdown['schools'] = school_score

    # 3. Amenities: 0-5 points (shops, hospital, parks)
    amenity_score = 0
    
    supermarkets = pois.get('supermarkets', [])
    if supermarkets:
        if supermarkets[0]['distance_m'] < 500:
            amenity_score += 3
            flags.append(f'🛒 {supermarkets[0]["name"]} {supermarkets[0]["distance_m"]}m')
        elif supermarkets[0]['distance_m'] < 1000:
            amenity_score += 2

    hospitals = pois.get('hospitals', [])
    if hospitals:
        if hospitals[0]['distance_m'] < 2000:
            amenity_score += 1
            flags.append(f'🏥 {hospitals[0]["name"]} {hospitals[0]["distance_m"]}m')

    parks = pois.get('parks', [])
    if parks:
        amenity_score += 1
        if parks[0]['distance_m'] < 300:
            flags.append(f'🌳 Park within {parks[0]["distance_m"]}m')

    amenity_score = min(5, amenity_score)
    breakdown['amenities'] = amenity_score

    # 4. Street quality: -15 to +8 points (road classification)
    road_cls = pois.get('road_classification', {})
    street_score = road_cls.get('score_adj', 0)
    road_label = road_cls.get('label', 'Unknown')
    road_name = road_cls.get('road_name', '')
    
    if street_score < -5:
        flags.append(f'⚠️ {road_label} ({road_name}) — traffic/noise concerns')
    elif street_score > 3:
        flags.append(f'✅ {road_label} — quiet street')

    breakdown['street_quality'] = street_score

    # Total location score (0-30 range, but street can go negative)
    total = transport_score + school_score + amenity_score + street_score
    # Clamp to 0-30 range
    total = max(0, min(30, total))

    breakdown['total'] = total
    return total, breakdown, flags


# ─── Growth Potential Scoring ────────────────────────────────────

# Known future infrastructure projects (hardcoded for now)
INFRASTRUCTURE_PROJECTS = {
    'Arncliffe': [
        {'name': 'Arncliffe Central mixed-use development', 'type': 'urban_renewal', 'boost': 5},
        {'name': 'Sydney Metro City & Southwest (Arncliffe proximity)', 'type': 'transport', 'boost': 3},
    ],
    'Banksia': [
        {'name': 'Arncliffe Central proximity', 'type': 'urban_renewal', 'boost': 3},
    ],
    'Turrella': [
        {'name': 'Arncliffe Central proximity', 'type': 'urban_renewal', 'boost': 2},
    ],
    'Rockdale': [
        {'name': 'Rockdale town centre renewal', 'type': 'urban_renewal', 'boost': 3},
    ],
    'Wolli Creek': [
        {'name': 'Sydney Metro Southwest corridor', 'type': 'transport', 'boost': 3},
    ],
    'Hurstville': [
        {'name': 'Hurstville City Centre masterplan', 'type': 'urban_renewal', 'boost': 4},
    ],
    'Kogarah': [
        {'name': 'St George Hospital expansion', 'type': 'health', 'boost': 3},
    ],
}

# Suburb median house prices for ripple effect calculation
SUBURB_MEDIANS = {
    'Arncliffe': 1_850_000,
    'Banksia': 1_750_000,
    'Bexley': 1_900_000,
    'Bexley North': 1_850_000,
    'Rockdale': 1_650_000,
    'Hurstville': 2_000_000,
    'Kyeemagh': 1_700_000,
    'Carlton': 1_700_000,
    'Bardwell Park': 1_800_000,
    'Bardwell Valley': 1_750_000,
    'Kogarah': 1_900_000,
    'Turrella': 1_650_000,
    'Wolli Creek': 1_600_000,
    'Beverly Hills': 1_750_000,
    'Mascot': 1_750_000,
    'Kingsgrove': 1_800_000,
    'Earlwood': 1_900_000,
    'Clemton Park': 1_850_000,
}

# Average of all tracked suburbs (for ripple effect comparison)
_all_medians = list(SUBURB_MEDIANS.values())
AREA_AVERAGE_MEDIAN = sum(_all_medians) / len(_all_medians) if _all_medians else 1_800_000


def score_growth_potential(suburb: str) -> Tuple[float, Dict, List[str]]:
    """
    Score growth potential based on infrastructure projects and ripple effect.
    
    Returns (score, breakdown, flags) where:
    - score: 0-15 (growth potential points)
    - breakdown: dict of component scores
    - flags: list of notable growth flags
    """
    breakdown = {}
    flags = []

    # 1. Infrastructure proximity (0-10 points)
    infra_score = 0
    projects = INFRASTRUCTURE_PROJECTS.get(suburb, [])
    for proj in projects:
        infra_score += proj['boost']
        flags.append(f'📈 {proj["name"]}')
    infra_score = min(10, infra_score)
    breakdown['infrastructure'] = infra_score

    # 2. Ripple effect (0-5 points)
    # Suburbs priced below area average have more room to grow
    ripple_score = 0
    median = SUBURB_MEDIANS.get(suburb, AREA_AVERAGE_MEDIAN)
    if median < AREA_AVERAGE_MEDIAN * 0.85:
        ripple_score = 5
        flags.append(f'💎 Underpriced relative to neighbours — ripple effect potential')
    elif median < AREA_AVERAGE_MEDIAN * 0.95:
        ripple_score = 3
        flags.append(f'📊 Below area average price — growth potential')
    elif median < AREA_AVERAGE_MEDIAN:
        ripple_score = 1
    breakdown['ripple_effect'] = ripple_score

    total = min(15, infra_score + ripple_score)
    breakdown['total'] = total
    return total, breakdown, flags


# ─── Geocoding with cache ───────────────────────────────────────

class OSMCache:
    """SQLite-backed cache for geocoding and POI data."""

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self):
        """Create cache tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS geocode_cache (
                address_key TEXT PRIMARY KEY,
                lat REAL,
                lng REAL,
                source TEXT,
                cached_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS osm_cache (
                cache_key TEXT PRIMARY KEY,
                pois_json TEXT,
                cached_at TEXT DEFAULT (datetime('now'))
            );
        """)
        self.conn.commit()

    def get_geocode(self, address_key: str) -> Optional[Tuple[float, float]]:
        """Get cached geocode result."""
        row = self.conn.execute(
            "SELECT lat, lng FROM geocode_cache WHERE address_key = ?",
            (address_key,)
        ).fetchone()
        if row and row['lat'] and row['lng']:
            return (row['lat'], row['lng'])
        return None

    def set_geocode(self, address_key: str, lat: float, lng: float, source: str = 'nominatim'):
        """Cache a geocode result."""
        self.conn.execute(
            "INSERT OR REPLACE INTO geocode_cache (address_key, lat, lng, source) VALUES (?, ?, ?, ?)",
            (address_key, lat, lng, source)
        )
        self.conn.commit()

    def get_pois(self, cache_key: str, max_age_hours: int = 24) -> Optional[Dict]:
        """Get cached POI data if fresh enough."""
        row = self.conn.execute(
            "SELECT pois_json, cached_at FROM osm_cache WHERE cache_key = ?",
            (cache_key,)
        ).fetchone()
        if not row:
            return None
        
        # Check freshness
        try:
            cached_at = datetime.fromisoformat(row['cached_at'])
            if datetime.utcnow() - cached_at > timedelta(hours=max_age_hours):
                return None  # Stale
        except (ValueError, TypeError):
            return None
        
        try:
            return json.loads(row['pois_json'])
        except (json.JSONDecodeError, TypeError):
            return None

    def set_pois(self, cache_key: str, pois: Dict):
        """Cache POI data."""
        self.conn.execute(
            "INSERT OR REPLACE INTO osm_cache (cache_key, pois_json) VALUES (?, ?)",
            (cache_key, json.dumps(pois))
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


# ─── Main orchestration ─────────────────────────────────────────

class LocationIntelligence:
    """Orchestrates geocoding, POI queries, and location scoring."""

    def __init__(self, db_path: str):
        self.cache = OSMCache(db_path)
        self._last_nominatim_call = 0.0  # Rate limiting

    def geocode_listing(self, listing: Dict) -> Tuple[Optional[float], Optional[float]]:
        """
        Geocode a listing address. Uses cache, then Nominatim, then suburb centroid.
        Returns (lat, lng) tuple.
        """
        address = listing.get('address', '')
        suburb = listing.get('suburb', '')
        state = listing.get('state', 'NSW')

        if not address and not suburb:
            return None, None

        # Check if listing already has good coordinates
        if listing.get('lat') and listing.get('lng'):
            return listing['lat'], listing['lng']

        # Build cache key
        cache_key = f"{address}|{suburb}|{state}".lower().strip()

        # Check cache
        cached = self.cache.get_geocode(cache_key)
        if cached:
            return cached

        # Try Nominatim
        if address:
            self._rate_limit_nominatim()
            coords = _nominatim_geocode(address, suburb, state)
            if coords:
                self.cache.set_geocode(cache_key, coords[0], coords[1], 'nominatim')
                return coords

        # Fall back to suburb centroid
        centroid = SUBURB_CENTROIDS.get(suburb)
        if centroid:
            self.cache.set_geocode(cache_key, centroid[0], centroid[1], 'centroid')
            return centroid

        return None, None

    def get_pois(self, lat: float, lng: float) -> Dict:
        """
        Get POIs near coordinates. Uses cache (24h), then Overpass API.
        """
        # Round to ~100m grid for cache efficiency
        cache_key = f"{lat:.4f},{lng:.4f}"

        # Check cache
        cached = self.cache.get_pois(cache_key)
        if cached:
            return cached

        # Rate limit fresh queries (2 seconds between Overpass requests)
        time.sleep(2)

        # Query Overpass
        pois = query_pois(lat, lng)
        
        # Cache results even if partial (to avoid re-querying failed locations)
        self.cache.set_pois(cache_key, pois)
        
        return pois

    def analyse_listing(self, listing: Dict) -> Dict:
        """
        Full location analysis for a listing.
        Returns dict with location_score, growth_score, pois, etc.
        """
        # Geocode
        lat, lng = self.geocode_listing(listing)
        if not lat or not lng:
            return {
                'lat': None, 'lng': None,
                'location_score': 0, 'location_breakdown': {},
                'location_flags': [],
                'growth_score': 0, 'growth_breakdown': {},
                'growth_flags': [],
                'pois': _empty_pois(),
                'geocode_source': 'none',
            }

        # Get POIs
        pois = self.get_pois(lat, lng)

        # Score location
        loc_score, loc_breakdown, loc_flags = score_location(pois)

        # Score growth potential
        suburb = listing.get('suburb', '')
        growth_score, growth_breakdown, growth_flags = score_growth_potential(suburb)

        return {
            'lat': lat,
            'lng': lng,
            'location_score': loc_score,
            'location_breakdown': loc_breakdown,
            'location_flags': loc_flags,
            'growth_score': growth_score,
            'growth_breakdown': growth_breakdown,
            'growth_flags': growth_flags,
            'pois': pois,
            'geocode_source': 'nominatim' if lat != SUBURB_CENTROIDS.get(suburb, (0,0))[0] else 'centroid',
        }

    def _rate_limit_nominatim(self):
        """Ensure at least 1 second between Nominatim requests."""
        now = time.time()
        elapsed = now - self._last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        self._last_nominatim_call = time.time()

    def close(self):
        self.cache.close()
