"""
Alert Manager

Saves new high-scoring listings to alerts/new-listings.json
and provides alert display functionality.
"""

import os
import json
from datetime import datetime
from typing import List, Dict


class AlertManager:
    """Manage alerts for new development opportunities."""

    def __init__(self, alerts_dir: str = None, min_score: float = 60):
        if alerts_dir is None:
            alerts_dir = os.path.join(os.path.dirname(__file__))
        self.alerts_dir = alerts_dir
        self.alerts_file = os.path.join(alerts_dir, 'new-listings.json')
        self.min_score = min_score

    def save_alerts(self, listings: List[Dict]) -> int:
        """
        Save qualifying listings to alerts file.
        Returns number of alerts saved.
        """
        qualifying = [
            l for l in listings
            if l.get('development_score', 0) >= self.min_score
        ]

        if not qualifying:
            return 0

        # Load existing alerts
        existing = self._load_existing()
        existing_ids = {a['id'] for a in existing}

        # Add new alerts
        new_alerts = []
        for listing in qualifying:
            if listing['id'] not in existing_ids:
                alert = self._format_alert(listing)
                new_alerts.append(alert)

        if new_alerts:
            all_alerts = new_alerts + existing
            # Keep only last 200 alerts
            all_alerts = all_alerts[:200]

            with open(self.alerts_file, 'w') as f:
                json.dump(all_alerts, f, indent=2, default=str)

        return len(new_alerts)

    def get_recent_alerts(self, hours: int = 24) -> List[Dict]:
        """Get alerts from the last N hours."""
        alerts = self._load_existing()
        cutoff = datetime.now().timestamp() - (hours * 3600)

        recent = []
        for alert in alerts:
            try:
                alert_time = datetime.fromisoformat(alert.get('alert_time', '')).timestamp()
                if alert_time >= cutoff:
                    recent.append(alert)
            except (ValueError, TypeError):
                recent.append(alert)  # Include if can't parse date

        return recent

    def get_all_alerts(self) -> List[Dict]:
        """Get all saved alerts."""
        return self._load_existing()

    def clear_alerts(self):
        """Clear all alerts."""
        with open(self.alerts_file, 'w') as f:
            json.dump([], f)

    def _load_existing(self) -> List[Dict]:
        """Load existing alerts from file."""
        if not os.path.exists(self.alerts_file):
            return []
        try:
            with open(self.alerts_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _format_alert(self, listing: Dict) -> Dict:
        """Format a listing as an alert entry."""
        # Parse feasibility if available
        feasibility = {}
        if listing.get('feasibility_json'):
            try:
                feas = listing['feasibility_json']
                if isinstance(feas, str):
                    feas = json.loads(feas)
                feasibility = {
                    'dev_type': feas.get('dev_type', ''),
                    'total_cost': feas.get('total_cost', 0),
                    'end_value': feas.get('end_value', 0),
                    'profit': feas.get('profit', 0),
                    'profit_margin_pct': feas.get('profit_margin_pct', 0),
                }
            except (json.JSONDecodeError, TypeError):
                pass

        # Parse flags
        flags = []
        if listing.get('development_flags'):
            try:
                f = listing['development_flags']
                flags = json.loads(f) if isinstance(f, str) else f
            except (json.JSONDecodeError, TypeError):
                pass

        return {
            'id': listing.get('id', ''),
            'alert_time': datetime.now().isoformat(),
            'address': listing.get('address', ''),
            'suburb': listing.get('suburb', ''),
            'state': listing.get('state', ''),
            'region': listing.get('region_name', ''),
            'price': listing.get('price_display', 'Contact Agent'),
            'price_low': listing.get('price_low'),
            'land_size_sqm': listing.get('land_size_sqm'),
            'bedrooms': listing.get('bedrooms', 0),
            'development_score': listing.get('development_score', 0),
            'development_flags': flags,
            'feasibility': feasibility,
            'listing_url': listing.get('url', ''),
            'days_on_market': listing.get('days_on_market'),
            'source': listing.get('source', ''),
        }

    def format_alert_text(self, alert: Dict) -> str:
        """Format an alert for display."""
        lines = []
        score = alert.get('development_score', 0)
        stars = '⭐' * min(5, int(score / 20))

        lines.append(f"{'─' * 50}")
        lines.append(f"{stars} Score: {score}/100")
        lines.append(f"📍 {alert.get('address', 'Unknown')}")
        lines.append(f"   {alert.get('suburb', '')} {alert.get('state', '')} | {alert.get('region', '')}")
        lines.append(f"💰 {alert.get('price', 'Contact Agent')}")

        if alert.get('land_size_sqm'):
            lines.append(f"📐 Land: {alert['land_size_sqm']}m²")

        if alert.get('days_on_market'):
            lines.append(f"📅 {alert['days_on_market']} days on market")

        flags = alert.get('development_flags', [])
        if flags:
            lines.append(f"🏗️  Flags: {' | '.join(flags[:5])}")

        feas = alert.get('feasibility', {})
        if feas.get('dev_type'):
            lines.append(f"📊 {feas['dev_type'].replace('_', ' ').title()}")
            if feas.get('profit'):
                profit = feas['profit']
                margin = feas.get('profit_margin_pct', 0)
                emoji = '✅' if profit > 0 else '❌'
                lines.append(f"   {emoji} Est. profit: ${profit:,.0f} ({margin}%)")

        if alert.get('listing_url'):
            lines.append(f"🔗 {alert['listing_url']}")

        return '\n'.join(lines)
