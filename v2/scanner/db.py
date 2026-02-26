"""
SQLite database for listing storage, deduplication, and tracking.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any


class ListingDB:
    """SQLite database manager for property listings."""

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'listings_v2.db')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._setup()
        self._migrate()

    def _migrate(self):
        """Run any needed schema migrations."""
        # Add osm_json column if it doesn't exist
        try:
            self.conn.execute("SELECT osm_json FROM listings LIMIT 1")
        except sqlite3.OperationalError:
            self.conn.execute("ALTER TABLE listings ADD COLUMN osm_json TEXT")
            self.conn.commit()

    def _setup(self):
        """Create tables if they don't exist."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT,
                address TEXT,
                suburb TEXT,
                state TEXT,
                postcode TEXT,
                region_name TEXT,

                price_display TEXT,
                price_low INTEGER,
                price_high INTEGER,

                property_type TEXT,
                bedrooms INTEGER,
                bathrooms INTEGER,
                parking INTEGER,
                land_size_sqm REAL,
                building_size_sqm REAL,
                frontage_m REAL,

                headline TEXT,
                description TEXT,
                features_text TEXT,
                agent_name TEXT,
                agent_phone TEXT,
                agency TEXT,

                lat REAL,
                lng REAL,
                zoning TEXT,
                year_built INTEGER,

                development_score REAL DEFAULT 0,
                score_breakdown TEXT,
                development_flags TEXT,
                feasibility_json TEXT,

                listing_date TEXT,
                auction_date TEXT,
                days_on_market INTEGER,

                osm_json TEXT,

                status TEXT DEFAULT 'active',
                first_seen TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now')),
                notified INTEGER DEFAULT 0,

                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id TEXT NOT NULL,
                price_display TEXT,
                price_low INTEGER,
                price_high INTEGER,
                recorded_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (listing_id) REFERENCES listings(id)
            );

            CREATE TABLE IF NOT EXISTS scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT,
                region_name TEXT,
                started_at TEXT DEFAULT (datetime('now')),
                finished_at TEXT,
                listings_found INTEGER DEFAULT 0,
                new_listings INTEGER DEFAULT 0,
                price_changes INTEGER DEFAULT 0,
                errors TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_listings_suburb ON listings(suburb);
            CREATE INDEX IF NOT EXISTS idx_listings_state ON listings(state);
            CREATE INDEX IF NOT EXISTS idx_listings_score ON listings(development_score DESC);
            CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
            CREATE INDEX IF NOT EXISTS idx_listings_first_seen ON listings(first_seen);
        """)
        self.conn.commit()

    def upsert_listing(self, listing: Dict[str, Any]) -> str:
        """
        Insert or update a listing. Returns 'new', 'updated', or 'unchanged'.
        Handles deduplication by listing ID.
        """
        lid = listing.get('id')
        if not lid:
            return 'skipped'

        existing = self.conn.execute(
            "SELECT id, price_low, price_high FROM listings WHERE id = ?", (lid,)
        ).fetchone()

        if existing is None:
            # New listing
            cols = [
                'id', 'source', 'url', 'address', 'suburb', 'state', 'postcode',
                'region_name', 'price_display', 'price_low', 'price_high',
                'property_type', 'bedrooms', 'bathrooms', 'parking',
                'land_size_sqm', 'building_size_sqm', 'frontage_m',
                'headline', 'description', 'features_text',
                'agent_name', 'agent_phone', 'agency',
                'lat', 'lng', 'zoning', 'year_built',
                'development_score', 'score_breakdown', 'development_flags',
                'feasibility_json',
                'listing_date', 'auction_date', 'days_on_market',
                'osm_json',
                'status', 'raw_json'
            ]
            vals = [listing.get(c) for c in cols]
            placeholders = ', '.join(['?' for _ in cols])
            col_names = ', '.join(cols)
            self.conn.execute(
                f"INSERT INTO listings ({col_names}) VALUES ({placeholders})", vals
            )
            self.conn.commit()
            return 'new'
        else:
            # Check for price change
            old_low = existing['price_low']
            old_high = existing['price_high']
            new_low = listing.get('price_low')
            new_high = listing.get('price_high')

            status = 'unchanged'
            if old_low != new_low or old_high != new_high:
                self.conn.execute(
                    "INSERT INTO price_history (listing_id, price_display, price_low, price_high) VALUES (?, ?, ?, ?)",
                    (lid, listing.get('price_display'), new_low, new_high)
                )
                status = 'updated'

            # Always update last_seen and scores
            self.conn.execute("""
                UPDATE listings SET
                    price_display = ?, price_low = ?, price_high = ?,
                    development_score = ?, score_breakdown = ?,
                    development_flags = ?, feasibility_json = ?,
                    lat = COALESCE(?, lat), lng = COALESCE(?, lng),
                    osm_json = COALESCE(?, osm_json),
                    last_seen = datetime('now'), status = 'active',
                    raw_json = ?
                WHERE id = ?
            """, (
                listing.get('price_display'), new_low, new_high,
                listing.get('development_score', 0),
                listing.get('score_breakdown'),
                listing.get('development_flags'),
                listing.get('feasibility_json'),
                listing.get('lat'), listing.get('lng'),
                listing.get('osm_json'),
                listing.get('raw_json'),
                lid
            ))
            self.conn.commit()
            return status

    def bulk_upsert(self, listings: List[Dict]) -> Dict[str, int]:
        """Upsert multiple listings, return counts."""
        counts = {'new': 0, 'updated': 0, 'unchanged': 0, 'skipped': 0}
        for listing in listings:
            result = self.upsert_listing(listing)
            counts[result] = counts.get(result, 0) + 1
        return counts

    def get_new_listings(self, hours: int = 24) -> List[Dict]:
        """Get listings first seen within the last N hours."""
        rows = self.conn.execute(
            """SELECT * FROM listings 
               WHERE first_seen > datetime('now', ?) AND status = 'active'
               ORDER BY development_score DESC""",
            (f'-{hours} hours',)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_top_listings(self, limit: int = 20, min_score: float = 0,
                         state: str = None, suburb: str = None) -> List[Dict]:
        """Get top-scored active listings with optional filters."""
        query = "SELECT * FROM listings WHERE status = 'active' AND development_score >= ?"
        params: list = [min_score]

        if state:
            query += " AND state = ?"
            params.append(state)
        if suburb:
            query += " AND suburb = ?"
            params.append(suburb)

        query += " ORDER BY development_score DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_all_active(self) -> List[Dict]:
        """Get all active listings."""
        rows = self.conn.execute(
            "SELECT * FROM listings WHERE status = 'active' ORDER BY development_score DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_market_summary(self) -> Dict:
        """Get summary statistics by suburb."""
        rows = self.conn.execute("""
            SELECT suburb, state, COUNT(*) as count,
                   ROUND(AVG(price_low)) as avg_price,
                   ROUND(AVG(land_size_sqm)) as avg_land,
                   ROUND(AVG(development_score), 1) as avg_score,
                   MAX(development_score) as top_score
            FROM listings WHERE status = 'active' AND price_low IS NOT NULL
            GROUP BY suburb, state ORDER BY avg_score DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def log_scan(self, scan_type: str, region_name: str,
                 listings_found: int, new_listings: int,
                 price_changes: int, errors: str = None):
        """Log a scan run."""
        self.conn.execute("""
            INSERT INTO scan_log (scan_type, region_name, finished_at,
                                  listings_found, new_listings, price_changes, errors)
            VALUES (?, ?, datetime('now'), ?, ?, ?, ?)
        """, (scan_type, region_name, listings_found, new_listings, price_changes, errors))
        self.conn.commit()

    def mark_stale(self, hours: int = 72):
        """Mark listings not seen in N hours as stale."""
        result = self.conn.execute(
            """UPDATE listings SET status = 'stale'
               WHERE status = 'active' AND last_seen < datetime('now', ?)""",
            (f'-{hours} hours',)
        )
        self.conn.commit()
        return result.rowcount

    def get_stats(self) -> Dict:
        """Get database statistics."""
        row = self.conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale,
                COUNT(CASE WHEN first_seen > datetime('now', '-24 hours') THEN 1 END) as new_24h,
                ROUND(AVG(CASE WHEN status = 'active' THEN development_score END), 1) as avg_score
            FROM listings
        """).fetchone()
        return dict(row)

    def close(self):
        """Close the database connection."""
        self.conn.close()
