const initSqlJs = require('sql.js');
const path = require('path');
const fs = require('fs');

const DATA_DIR = path.join(__dirname, '..', 'data');
const DB_PATH = path.join(DATA_DIR, 'listings.db');

let _dbInstance = null;

async function getDb() {
  if (_dbInstance) return _dbInstance;

  if (!fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(DATA_DIR, { recursive: true });
  }

  const SQL = await initSqlJs();
  
  if (fs.existsSync(DB_PATH)) {
    const buffer = fs.readFileSync(DB_PATH);
    _dbInstance = new SQL.Database(buffer);
  } else {
    _dbInstance = new SQL.Database();
  }

  return _dbInstance;
}

function saveDb(db) {
  const data = db.export();
  const buffer = Buffer.from(data);
  fs.writeFileSync(DB_PATH, buffer);
}

async function setup() {
  const db = await getDb();

  db.run(`
    CREATE TABLE IF NOT EXISTS listings (
      id TEXT PRIMARY KEY,
      source TEXT NOT NULL,
      url TEXT,
      address TEXT,
      suburb TEXT,
      state TEXT DEFAULT 'NSW',
      postcode TEXT,
      price_display TEXT,
      price_low INTEGER,
      price_high INTEGER,
      property_type TEXT,
      bedrooms INTEGER,
      bathrooms INTEGER,
      parking INTEGER,
      land_size_sqm REAL,
      building_size_sqm REAL,
      headline TEXT,
      description TEXT,
      agent_name TEXT,
      agent_phone TEXT,
      agency TEXT,
      lat REAL,
      lng REAL,
      distance_to_school_km REAL,
      score REAL,
      listing_date TEXT,
      auction_date TEXT,
      sold_date TEXT,
      sold_price INTEGER,
      status TEXT DEFAULT 'active',
      first_seen TEXT DEFAULT (datetime('now')),
      last_seen TEXT DEFAULT (datetime('now')),
      notified INTEGER DEFAULT 0,
      raw_json TEXT
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS price_history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      listing_id TEXT NOT NULL,
      price_display TEXT,
      price_low INTEGER,
      price_high INTEGER,
      recorded_at TEXT DEFAULT (datetime('now')),
      FOREIGN KEY (listing_id) REFERENCES listings(id)
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS sold_data (
      id TEXT PRIMARY KEY,
      address TEXT,
      suburb TEXT,
      postcode TEXT,
      property_type TEXT,
      bedrooms INTEGER,
      bathrooms INTEGER,
      parking INTEGER,
      land_size_sqm REAL,
      sold_price INTEGER,
      sold_date TEXT,
      days_on_market INTEGER,
      lat REAL,
      lng REAL,
      distance_to_school_km REAL,
      source TEXT,
      raw_json TEXT
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS scan_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      scan_type TEXT,
      started_at TEXT DEFAULT (datetime('now')),
      finished_at TEXT,
      listings_found INTEGER DEFAULT 0,
      new_listings INTEGER DEFAULT 0,
      price_changes INTEGER DEFAULT 0,
      errors TEXT
    )
  `);

  saveDb(db);
  console.log('✅ Database setup complete:', DB_PATH);
}

// Run setup if called directly
if (require.main === module) {
  setup().catch(console.error);
}

module.exports = { getDb, saveDb, setup, DB_PATH };
