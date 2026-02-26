#!/usr/bin/env python3
"""
PropertyFinder v2 — AI-Powered Property Development Opportunity Scanner

Scans Australian property listings and identifies development opportunities
(duplex, subdivision, knockdown-rebuild). National scope.

Usage:
    python main.py scan                 Run full scan of all watched regions
    python main.py scan --region X      Scan a specific region only
    python main.py import FILE          Import listings from a JSON file
    python main.py import --dir DIR     Import all JSON files from a directory
    python main.py alerts               Show new listings since last scan
    python main.py alerts --hours N     Show alerts from last N hours
    python main.py report               Generate summary of best opportunities
    python main.py report --top N       Show top N opportunities
    python main.py stats                Show database statistics
    python main.py rescore              Re-score all active listings
"""

import os
import sys
import json
import argparse
import yaml
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from scanner.domain_api import DomainAPIScanner
from scanner.domain_scraper import DomainWebScraper
from scanner.rea_scraper import REAScraper
from scanner.importer import ListingImporter
from scanner.db import ListingDB
from analysis.scorer import DevelopmentScorer
from analysis.feasibility import FeasibilityEstimator
from alerts.manager import AlertManager


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = Path(__file__).parent / 'config.yaml'
    if not config_path.exists():
        print("Error: config.yaml not found")
        sys.exit(1)
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def load_env():
    """Load environment variables from .env file."""
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    else:
        env_path = Path(__file__).parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)


def _score_and_save(listings, config, db):
    """Score listings, estimate feasibility, and save to DB. Returns counts."""
    scorer = DevelopmentScorer(config)
    feasibility = FeasibilityEstimator(config)

    scored = scorer.score_listings(listings)
    scored = feasibility.estimate_listings(scored)
    counts = db.bulk_upsert(scored)
    return scored, counts


def cmd_scan(args):
    """Run a full scan of all watched regions."""
    load_env()
    config = load_config()
    regions = config.get('regions', [])

    if args.region:
        regions = [r for r in regions if args.region.lower() in r.get('name', '').lower()]
        if not regions:
            print(f"Error: No region matching '{args.region}'")
            return

    print("=" * 60)
    print("PropertyFinder v2 -- Development Opportunity Scanner")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Scanning {len(regions)} region(s)")
    print("=" * 60)

    db = ListingDB()
    alert_mgr = AlertManager(min_score=config.get('alerts', {}).get('min_score', 60))

    api_key = os.getenv('DOMAIN_API_KEY', '')
    domain_api = DomainAPIScanner(api_key, config) if api_key else None
    domain_web = DomainWebScraper(config)
    rea_scraper = REAScraper(config)

    total_new = 0
    total_updated = 0
    total_found = 0

    for region in regions:
        region_name = region.get('name', 'Unknown')
        print(f"\n{'=' * 60}")
        print(f"Region: {region_name}")
        print(f"  Suburbs: {', '.join(region.get('suburbs', []))}")
        print(f"  Budget: ${region.get('price_min', 0):,.0f} - ${region.get('price_max', 0):,.0f}")
        print(f"  Min land: {region.get('min_land_sqm', 0)}sqm")
        print()

        region_listings = []

        # 1. Domain API (try silently — Agents & Listings may still be pending)
        if domain_api:
            try:
                api_listings = domain_api.search_listings(region)
                if api_listings:
                    region_listings.extend(api_listings)
                    print(f"  [Domain API] {len(api_listings)} listings")
            except Exception:
                pass  # API not yet approved

        # 2. Domain web scraping
        if not args.api_only:
            print("  [Domain Web] Scraping...")
            try:
                web_listings = domain_web.scrape_region(region)
                existing_ids = {l['id'] for l in region_listings}
                new_web = [l for l in web_listings if l['id'] not in existing_ids]
                region_listings.extend(new_web)
                print(f"  [Domain Web] {len(new_web)} listings")
            except Exception as e:
                print(f"  [Domain Web] Error: {e}")

        # 3. REA scraping
        if not args.api_only:
            print("  [REA] Scraping...")
            try:
                rea_listings = rea_scraper.scrape_region(region)
                region_listings.extend(rea_listings)
                print(f"  [REA] {len(rea_listings)} listings")
            except Exception as e:
                print(f"  [REA] Error: {e}")

        if not region_listings:
            msg = ("No listings found via API/scraping. Both Domain and REA use "
                   "bot protection. Use 'python main.py import' to load data from "
                   "browser-scraped JSON files instead.")
            print(f"\n  NOTE: {msg}")
            db.log_scan('full', region_name, 0, 0, 0, 'blocked by bot protection')
            continue

        # Score + save
        print(f"\n  Scoring {len(region_listings)} listings...")
        scored, counts = _score_and_save(region_listings, config, db)
        total_new += counts['new']
        total_updated += counts['updated']
        total_found += len(region_listings)

        print(f"  Saved: {counts['new']} new | {counts['updated']} updated | {counts['unchanged']} unchanged")

        db.log_scan('full', region_name, len(region_listings), counts['new'], counts['updated'])

        # Show top 5
        top5 = sorted(scored, key=lambda x: x.get('development_score', 0), reverse=True)[:5]
        if top5:
            print(f"\n  Top 5 in {region_name}:")
            for i, l in enumerate(top5, 1):
                score = l.get('development_score', 0)
                addr = l.get('address', 'Unknown')[:50]
                price = l.get('price_display', '?')
                land = l.get('land_size_sqm')
                land_str = f"{land:.0f}sqm" if land else '?'
                flags = json.loads(l.get('development_flags', '[]'))
                flag_str = ' | '.join(flags[:2]) if flags else ''
                print(f"    {i}. [{score}/100] {addr}")
                print(f"       {price} | Land: {land_str} {f'| {flag_str}' if flag_str else ''}")

    # Alerts
    new_from_db = db.get_new_listings(hours=1)
    if new_from_db:
        num_alerts = alert_mgr.save_alerts(new_from_db)
        if num_alerts > 0:
            print(f"\n{num_alerts} new alert(s) saved to alerts/new-listings.json")

    # Stale
    stale_count = db.mark_stale(hours=72)
    if stale_count > 0:
        print(f"Marked {stale_count} stale listings (not seen in 72h)")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Scan complete!")
    print(f"  Total found: {total_found}")
    print(f"  New listings: {total_new}")
    print(f"  Price updates: {total_updated}")
    if domain_api:
        print(f"  Domain API calls: {domain_api.calls_made}")

    stats = db.get_stats()
    print(f"  Database: {stats.get('active', 0)} active | "
          f"{stats.get('stale', 0)} stale | {stats.get('total', 0)} total")
    print("=" * 60)
    db.close()


def cmd_import(args):
    """Import listings from JSON files."""
    config = load_config()
    db = ListingDB()
    importer = ListingImporter(config)

    region_name = args.region_name or ''

    if args.dir:
        print(f"Importing from directory: {args.dir}")
        listings = importer.import_directory(args.dir, region_name)
    elif args.file:
        print(f"Importing from: {args.file}")
        listings = importer.import_file(args.file, region_name)
    else:
        # Default: import from ../data/
        data_dir = str(Path(__file__).parent.parent / 'data')
        if os.path.isdir(data_dir):
            print(f"Importing from default data directory: {data_dir}")
            listings = importer.import_directory(data_dir, region_name)
        else:
            print("Error: No file or directory specified. Use --file or --dir")
            return

    if not listings:
        print("No listings found to import.")
        db.close()
        return

    print(f"\nScoring {len(listings)} imported listings...")
    scored, counts = _score_and_save(listings, config, db)

    print(f"\nImport complete:")
    print(f"  Total: {len(listings)}")
    print(f"  New: {counts['new']}")
    print(f"  Updated: {counts['updated']}")
    print(f"  Unchanged: {counts['unchanged']}")

    # Save alerts
    alert_mgr = AlertManager(min_score=config.get('alerts', {}).get('min_score', 60))
    num_alerts = alert_mgr.save_alerts(scored)
    if num_alerts:
        print(f"  Alerts: {num_alerts} high-scoring listings saved")

    # Show top 10
    top = sorted(scored, key=lambda x: x.get('development_score', 0), reverse=True)[:10]
    if top:
        print(f"\nTop {len(top)} Development Opportunities:")
        for i, l in enumerate(top, 1):
            score = l.get('development_score', 0)
            addr = l.get('address', 'Unknown')[:50]
            price = l.get('price_display', '?')
            land = l.get('land_size_sqm')
            land_str = f"{land:.0f}sqm" if land else '?'
            flags = json.loads(l.get('development_flags', '[]'))
            flag_str = ' | '.join(flags[:3]) if flags else ''
            print(f"  {i:>2}. [{score}/100] {addr}")
            print(f"      {price} | Land: {land_str}")
            if flag_str:
                print(f"      Flags: {flag_str}")

            # Feasibility
            if l.get('feasibility_json'):
                try:
                    feas = json.loads(l['feasibility_json']) if isinstance(l['feasibility_json'], str) else l['feasibility_json']
                    dev = feas.get('dev_type', '').replace('_', ' ').title()
                    profit = feas.get('profit', 0)
                    margin = feas.get('profit_margin_pct', 0)
                    total_cost = feas.get('total_cost', 0)
                    end_val = feas.get('end_value', 0)
                    status = 'PROFIT' if profit > 0 else 'LOSS'
                    print(f"      {dev}: Cost ${total_cost:,.0f} -> Value ${end_val:,.0f} = "
                          f"{status} ${abs(profit):,.0f} ({margin}%)")
                except (json.JSONDecodeError, TypeError):
                    pass

            if l.get('url'):
                print(f"      {l['url']}")
            print()

    db.close()


def cmd_alerts(args):
    """Show recent alerts."""
    config = load_config()
    alert_mgr = AlertManager(min_score=config.get('alerts', {}).get('min_score', 60))

    hours = args.hours or 24
    alerts = alert_mgr.get_recent_alerts(hours)

    if not alerts:
        print(f"No alerts in the last {hours} hours.")
        print("Run 'python main.py scan' or 'python main.py import' first.")
        return

    print(f"{len(alerts)} alert(s) in the last {hours} hours:\n")
    for alert in alerts:
        print(alert_mgr.format_alert_text(alert))
        print()


def cmd_report(args):
    """Generate a report of best opportunities."""
    load_env()
    config = load_config()
    db = ListingDB()

    top_n = args.top or 20
    min_score = args.min_score or 0

    listings = db.get_top_listings(limit=top_n, min_score=min_score)

    if not listings:
        print("No listings in database. Run 'python main.py scan' or 'python main.py import' first.")
        db.close()
        return

    print("=" * 60)
    print("PropertyFinder v2 -- Development Opportunity Report")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # Market summary
    summary = db.get_market_summary()
    if summary:
        print(f"\nMarket Summary by Suburb:")
        print(f"{'Suburb':<20} {'State':<5} {'#':>4} {'Avg Price':>12} "
              f"{'Avg Land':>8} {'Avg Score':>9} {'Top':>5}")
        print("-" * 68)
        for row in summary:
            avg_price = f"${row['avg_price']:,.0f}" if row['avg_price'] else '-'
            avg_land = f"{row['avg_land']:.0f}sqm" if row['avg_land'] else '-'
            print(f"{row['suburb']:<20} {row['state']:<5} {row['count']:>4} "
                  f"{avg_price:>12} {avg_land:>8} {row['avg_score']:>8.1f} "
                  f"{row['top_score']:>5.0f}")

    # Top opportunities
    print(f"\nTop {len(listings)} Development Opportunities:\n")

    for i, l in enumerate(listings, 1):
        score = l.get('development_score', 0)
        addr = l.get('address', 'Unknown')
        suburb = l.get('suburb', '')
        state = l.get('state', '')
        price = l.get('price_display', 'Contact Agent')
        land = l.get('land_size_sqm')
        beds = l.get('bedrooms', 0)
        baths = l.get('bathrooms', 0)

        print(f"  {i:>2}. [{score}/100] {addr}")
        print(f"      {suburb}, {state} | {price}")

        details = []
        if land:
            details.append(f"Land: {land:.0f}sqm")
        if beds:
            details.append(f"{beds}bed")
        if baths:
            details.append(f"{baths}bath")
        if l.get('days_on_market'):
            details.append(f"{l['days_on_market']}d on market")
        if details:
            print(f"      {' | '.join(details)}")

        # Flags
        flags = []
        if l.get('development_flags'):
            try:
                flags = json.loads(l['development_flags']) if isinstance(l['development_flags'], str) else l['development_flags']
            except json.JSONDecodeError:
                pass
        if flags:
            print(f"      Flags: {' | '.join(flags[:4])}")

        # Feasibility
        if l.get('feasibility_json'):
            try:
                feas = json.loads(l['feasibility_json']) if isinstance(l['feasibility_json'], str) else l['feasibility_json']
                dev = feas.get('dev_type', '').replace('_', ' ').title()
                profit = feas.get('profit', 0)
                margin = feas.get('profit_margin_pct', 0)
                total_cost = feas.get('total_cost', 0)
                end_val = feas.get('end_value', 0)
                status = 'PROFIT' if profit > 0 else 'LOSS'
                print(f"      {dev}: Cost ${total_cost:,.0f} -> Value ${end_val:,.0f} = "
                      f"{status} ${abs(profit):,.0f} ({margin}%)")
            except (json.JSONDecodeError, TypeError):
                pass

        if l.get('url'):
            print(f"      {l['url']}")
        print()

    stats = db.get_stats()
    print("-" * 60)
    print(f"Database: {stats.get('active', 0)} active listings | "
          f"{stats.get('new_24h', 0)} new in 24h | "
          f"Avg score: {stats.get('avg_score', 0)}")

    db.close()


def cmd_stats(args):
    """Show database statistics."""
    db = ListingDB()
    stats = db.get_stats()
    summary = db.get_market_summary()

    print("PropertyFinder v2 -- Database Statistics\n")
    print(f"  Total listings:    {stats.get('total', 0)}")
    print(f"  Active:            {stats.get('active', 0)}")
    print(f"  Stale:             {stats.get('stale', 0)}")
    print(f"  New (24h):         {stats.get('new_24h', 0)}")
    print(f"  Avg dev score:     {stats.get('avg_score', 0)}")

    if summary:
        print(f"\n  Suburbs tracked:   {len(summary)}")
        print(f"\n  By suburb:")
        for row in summary:
            print(f"    {row['suburb']:<20} ({row['state']}) "
                  f"-- {row['count']} listings, avg score {row['avg_score']:.1f}")

    db.close()


def cmd_rescore(args):
    """Re-score all active listings with current config."""
    config = load_config()
    db = ListingDB()
    scorer = DevelopmentScorer(config)
    feasibility = FeasibilityEstimator(config)

    listings = db.get_all_active()
    if not listings:
        print("No active listings to re-score.")
        db.close()
        return

    print(f"Re-scoring {len(listings)} active listings...")
    scored = scorer.score_listings(listings)
    scored = feasibility.estimate_listings(scored)
    counts = db.bulk_upsert(scored)

    print(f"Done. Updated {counts['updated'] + counts['unchanged']} listings.")

    # Show top 5
    top5 = sorted(scored, key=lambda x: x.get('development_score', 0), reverse=True)[:5]
    if top5:
        print(f"\nTop 5:")
        for i, l in enumerate(top5, 1):
            print(f"  {i}. [{l.get('development_score', 0)}/100] {l.get('address', '?')}")

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description='PropertyFinder v2 -- Development Opportunity Scanner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py scan                      Scan all regions (API + web scraping)
  python main.py scan --region Sydney      Scan Sydney regions only
  python main.py import                    Import from ../data/ JSON files
  python main.py import --file data.json   Import from specific file
  python main.py import --dir ./exports/   Import all JSONs from directory
  python main.py alerts                    Show alerts from last 24h
  python main.py report                    Top 20 opportunities
  python main.py report --top 50 -s 70     Top 50 with score >= 70
  python main.py rescore                   Re-score all listings
  python main.py stats                     Database statistics
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # scan
    scan_parser = subparsers.add_parser('scan', help='Run full scan of watched regions')
    scan_parser.add_argument('--region', '-r', help='Filter by region name')
    scan_parser.add_argument('--api-only', action='store_true',
                             help='Only use Domain API (skip web scraping)')

    # import
    import_parser = subparsers.add_parser('import', help='Import listings from JSON files')
    import_parser.add_argument('file', nargs='?', help='JSON file to import')
    import_parser.add_argument('--dir', '-d', help='Directory of JSON files to import')
    import_parser.add_argument('--region-name', help='Region name to tag imported listings')

    # alerts
    alerts_parser = subparsers.add_parser('alerts', help='Show new listing alerts')
    alerts_parser.add_argument('--hours', '-H', type=int, default=24,
                               help='Show alerts from last N hours (default: 24)')

    # report
    report_parser = subparsers.add_parser('report', help='Generate opportunity report')
    report_parser.add_argument('--top', '-n', type=int, default=20,
                               help='Number of top opportunities (default: 20)')
    report_parser.add_argument('--min-score', '-s', type=float, default=0,
                               help='Minimum development score')

    # stats
    subparsers.add_parser('stats', help='Show database statistics')

    # rescore
    subparsers.add_parser('rescore', help='Re-score all active listings')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'scan': cmd_scan,
        'import': cmd_import,
        'alerts': cmd_alerts,
        'report': cmd_report,
        'stats': cmd_stats,
        'rescore': cmd_rescore,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
