"""
Development Feasibility Estimator

Estimates the financial viability of a development opportunity:
- Purchase costs (price + stamp duty + legals)
- Build costs (construction + approvals)
- Holding costs (interest during build)
- End value estimate
- Profit margin
"""

import json
from typing import Dict, Optional, Tuple


class FeasibilityEstimator:
    """Estimate development feasibility for a listing."""

    # Median end values per dwelling by area (rough estimates)
    # These are conservative — actual values depend heavily on suburb
    MEDIAN_END_VALUES = {
        # NSW — Sydney
        'Arncliffe': {'duplex_each': 1_400_000, 'house': 1_800_000},
        'Banksia': {'duplex_each': 1_350_000, 'house': 1_700_000},
        'Turrella': {'duplex_each': 1_350_000, 'house': 1_650_000},
        'Rockdale': {'duplex_each': 1_300_000, 'house': 1_650_000},
        'Bexley': {'duplex_each': 1_400_000, 'house': 1_750_000},
        'Wolli Creek': {'duplex_each': 1_250_000, 'house': 1_500_000},
        'Bardwell Park': {'duplex_each': 1_400_000, 'house': 1_800_000},
        'Bardwell Valley': {'duplex_each': 1_400_000, 'house': 1_750_000},
        'Kingsgrove': {'duplex_each': 1_400_000, 'house': 1_800_000},
        'Bexley North': {'duplex_each': 1_350_000, 'house': 1_700_000},
        'Hurstville': {'duplex_each': 1_500_000, 'house': 2_000_000},
        'Kogarah': {'duplex_each': 1_450_000, 'house': 1_900_000},
        'Carlton': {'duplex_each': 1_350_000, 'house': 1_700_000},
        'Beverly Hills': {'duplex_each': 1_350_000, 'house': 1_750_000},
        'Kyeemagh': {'duplex_each': 1_350_000, 'house': 1_700_000},
        'Mascot': {'duplex_each': 1_400_000, 'house': 1_750_000},
        'Earlwood': {'duplex_each': 1_500_000, 'house': 1_900_000},
        'Clemton Park': {'duplex_each': 1_450_000, 'house': 1_850_000},
        # Sydney outer west
        'Marsden Park': {'duplex_each': 900_000, 'house': 1_100_000},
        'Box Hill': {'duplex_each': 900_000, 'house': 1_100_000},
        'Schofields': {'duplex_each': 880_000, 'house': 1_050_000},
        'Riverstone': {'duplex_each': 850_000, 'house': 1_000_000},
        'Austral': {'duplex_each': 850_000, 'house': 1_000_000},
        'Leppington': {'duplex_each': 850_000, 'house': 1_000_000},
        # VIC — Melbourne
        'Sunbury': {'duplex_each': 650_000, 'house': 800_000},
        'Craigieburn': {'duplex_each': 620_000, 'house': 750_000},
        'Mickleham': {'duplex_each': 600_000, 'house': 720_000},
        'Melton': {'duplex_each': 550_000, 'house': 650_000},
        'Melton South': {'duplex_each': 530_000, 'house': 630_000},
        'Rockbank': {'duplex_each': 560_000, 'house': 660_000},
        'Tarneit': {'duplex_each': 600_000, 'house': 720_000},
        'Wyndham Vale': {'duplex_each': 570_000, 'house': 680_000},
    }

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.feas_cfg = self.config.get('feasibility', {})

    def estimate(self, listing: Dict) -> Optional[Dict]:
        """
        Estimate development feasibility for a listing.
        
        Returns a dict with cost breakdown and profit estimate,
        or None if insufficient data.
        """
        price = listing.get('price_low') or listing.get('price_high')
        if not price:
            return None

        land_size = listing.get('land_size_sqm')
        suburb = listing.get('suburb', '')
        state = listing.get('state', 'NSW')

        # Determine development type
        dev_type = self._determine_dev_type(listing, land_size)

        # --- Purchase costs ---
        stamp_duty_rate = self.feas_cfg.get('stamp_duty_rate', 0.055)
        stamp_duty = int(price * stamp_duty_rate)
        legals = 5_000
        purchase_total = price + stamp_duty + legals

        # --- Build costs ---
        build_cost_per_sqm = self.feas_cfg.get('build_cost_per_sqm', {}).get(
            state, self.feas_cfg.get('build_cost_per_sqm', {}).get('default', 2600)
        )

        if dev_type == 'duplex':
            dwelling_size = self.feas_cfg.get('duplex_size_sqm', 180)
            demolition = 40_000
            da_costs = 35_000
            infrastructure = 50_000
            build_cost = (dwelling_size * 2) * build_cost_per_sqm
            total_build = build_cost + demolition + da_costs + infrastructure
        elif dev_type == 'subdivision':
            # Subdivision: no build, just split and sell lots
            demolition = 30_000
            da_costs = 25_000
            infrastructure = 80_000  # roads, services, etc.
            build_cost = 0
            total_build = demolition + da_costs + infrastructure
        elif dev_type == 'knockdown_rebuild':
            dwelling_size = 250  # single new home
            demolition = 35_000
            da_costs = 20_000
            infrastructure = 15_000
            build_cost = dwelling_size * build_cost_per_sqm
            total_build = build_cost + demolition + da_costs + infrastructure
        else:
            return None

        # --- Holding costs ---
        holding_months = self.feas_cfg.get('holding_cost_months', 18)
        monthly_rate = self.feas_cfg.get('holding_cost_monthly_rate', 0.005)
        total_invested = purchase_total + total_build
        holding_cost = int(total_invested * monthly_rate * holding_months)

        # --- Total costs ---
        total_cost = purchase_total + total_build + holding_cost

        # --- End value estimate ---
        end_value = self._estimate_end_value(suburb, state, dev_type, land_size)
        if not end_value:
            # Fallback: estimate from price with multiplier
            if dev_type == 'duplex':
                end_value = int(price * 1.6)  # 2 dwellings at ~80% of purchase each
            elif dev_type == 'subdivision':
                end_value = int(price * 1.3)
            else:
                end_value = int(price * 1.2)

        # Selling costs
        selling_rate = self.feas_cfg.get('selling_costs_rate', 0.03)
        selling_costs = int(end_value * selling_rate)

        # --- Profit calculation ---
        net_proceeds = end_value - selling_costs
        profit = net_proceeds - total_cost
        profit_margin_pct = round((profit / total_cost) * 100, 1) if total_cost > 0 else 0

        return {
            'dev_type': dev_type,
            'purchase_price': price,
            'stamp_duty': stamp_duty,
            'legals': legals,
            'purchase_total': purchase_total,
            'build_cost': build_cost if dev_type != 'subdivision' else 0,
            'demolition': demolition,
            'da_costs': da_costs,
            'infrastructure': infrastructure,
            'total_build': total_build,
            'holding_cost': holding_cost,
            'holding_months': holding_months,
            'total_cost': total_cost,
            'end_value': end_value,
            'selling_costs': selling_costs,
            'net_proceeds': net_proceeds,
            'profit': profit,
            'profit_margin_pct': profit_margin_pct,
            'build_cost_per_sqm': build_cost_per_sqm,
        }

    def _determine_dev_type(self, listing: Dict, land_size: Optional[float]) -> str:
        """Determine the most likely development type."""
        text = ' '.join([
            listing.get('headline', ''),
            listing.get('description', ''),
        ]).lower()

        # Explicit mentions
        if any(kw in text for kw in ['duplex', 'dual occ', 'dual occupancy']):
            return 'duplex'
        if any(kw in text for kw in ['subdivide', 'subdivision', 'subdividable']):
            return 'subdivision'

        # Based on land size
        if land_size:
            if land_size >= 1000:
                return 'subdivision'
            elif land_size >= 550:
                return 'duplex'

        # Default based on zoning
        zoning = listing.get('zoning', '')
        if zoning:
            z = zoning.upper()
            if z in ('R3', 'R4', 'RGZ', 'MUZ'):
                return 'duplex'

        return 'knockdown_rebuild'

    def _estimate_end_value(self, suburb: str, state: str,
                            dev_type: str, land_size: Optional[float]) -> Optional[int]:
        """Estimate end value based on suburb medians."""
        values = self.MEDIAN_END_VALUES.get(suburb)
        if not values:
            return None

        if dev_type == 'duplex':
            return values.get('duplex_each', 0) * 2
        elif dev_type == 'subdivision':
            # Estimate number of lots
            if land_size and land_size >= 1000:
                num_lots = int(land_size / 450)  # ~450m² per lot
                lot_value = int(values.get('house', 800_000) * 0.5)  # Land value ~50% of house
                return lot_value * num_lots
            return values.get('house', 800_000)
        elif dev_type == 'knockdown_rebuild':
            # New build premium
            return int(values.get('house', 800_000) * 1.15)
        return None

    def estimate_listings(self, listings: list) -> list:
        """Estimate feasibility for a batch of listings."""
        for listing in listings:
            feas = self.estimate(listing)
            if feas:
                listing['feasibility_json'] = json.dumps(feas)
        return listings
