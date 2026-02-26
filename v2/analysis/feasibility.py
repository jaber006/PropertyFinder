"""
Development Feasibility Estimator v2

Estimates the financial viability of a development opportunity:
- Purchase costs (price + stamp duty + legals)
- Build costs (construction + approvals)
- Holding costs (interest during build)
- End value estimate (based on suburb medians, configurable per suburb)
- Profit margin

v2 Changes:
- End values now use suburb median house price as baseline
- New duplex dwellings estimated at 80-90% of suburb median house price
- End values configurable per suburb in config.yaml
- More realistic cost estimates
"""

import json
from typing import Dict, Optional, Tuple


class FeasibilityEstimator:
    """Estimate development feasibility for a listing."""

    # Default suburb median house prices (used if not overridden in config)
    DEFAULT_SUBURB_MEDIANS = {
        # NSW — Sydney St George / Bayside
        'Arncliffe': 1_850_000,
        'Banksia': 1_750_000,
        'Turrella': 1_650_000,
        'Rockdale': 1_650_000,
        'Bexley': 1_900_000,
        'Wolli Creek': 1_600_000,
        'Bardwell Park': 1_800_000,
        'Bardwell Valley': 1_750_000,
        'Kingsgrove': 1_800_000,
        'Bexley North': 1_850_000,
        'Hurstville': 2_000_000,
        'Kogarah': 1_900_000,
        'Carlton': 1_700_000,
        'Beverly Hills': 1_750_000,
        'Kyeemagh': 1_700_000,
        'Mascot': 1_750_000,
        'Earlwood': 1_900_000,
        'Clemton Park': 1_850_000,
        # Sydney outer west
        'Marsden Park': 1_100_000,
        'Box Hill': 1_100_000,
        'Schofields': 1_050_000,
        'Riverstone': 1_000_000,
        'Austral': 1_000_000,
        'Leppington': 1_000_000,
        # VIC — Melbourne
        'Sunbury': 800_000,
        'Craigieburn': 750_000,
        'Mickleham': 720_000,
        'Melton': 650_000,
        'Melton South': 630_000,
        'Rockbank': 660_000,
        'Tarneit': 720_000,
        'Wyndham Vale': 680_000,
    }

    # Default duplex value as fraction of suburb median house price
    # A NEW duplex dwelling should sell at 80-90% of the suburb's median HOUSE price
    # (because it's new construction but on a smaller/shared lot)
    DEFAULT_DUPLEX_FACTOR = 0.85  # 85% of median house price per dwelling

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.feas_cfg = self.config.get('feasibility', {})
        
        # Load per-suburb end value overrides from config
        self.suburb_end_values = self.feas_cfg.get('suburb_end_values', {})
        
        # Duplex value factor (configurable)
        self.duplex_factor = self.feas_cfg.get('duplex_value_factor', self.DEFAULT_DUPLEX_FACTOR)

    def _get_suburb_median(self, suburb: str) -> Optional[int]:
        """Get the median house price for a suburb."""
        # First check config overrides
        override = self.suburb_end_values.get(suburb, {})
        if override.get('median_house'):
            return override['median_house']
        # Then use defaults
        return self.DEFAULT_SUBURB_MEDIANS.get(suburb)

    def _get_duplex_end_value_each(self, suburb: str) -> Optional[int]:
        """
        Get the estimated end value per duplex dwelling.
        
        Logic: A NEW duplex dwelling sells at ~85% of suburb median house price.
        This is because:
        - It's brand new (premium)
        - But on a smaller/shared lot (discount)
        - Net effect: ~80-90% of full house median
        """
        # Check for explicit per-suburb override
        override = self.suburb_end_values.get(suburb, {})
        if override.get('duplex_each'):
            return override['duplex_each']
        
        # Calculate from suburb median
        median = self._get_suburb_median(suburb)
        if median:
            factor = override.get('duplex_factor', self.duplex_factor)
            return int(median * factor)
        
        return None

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
        stamp_duty = self._calc_stamp_duty(price, state)
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
            site_works = 50_000
            professional_fees = 50_000
            council_contributions = 30_000
            landscaping = 25_000
            build_cost = (dwelling_size * 2) * build_cost_per_sqm
            contingency = int((build_cost + demolition + da_costs + site_works + 
                             professional_fees + council_contributions + landscaping) * 0.10)
            total_build = (build_cost + demolition + da_costs + site_works + 
                          professional_fees + council_contributions + landscaping + contingency)
        elif dev_type == 'subdivision':
            demolition = 30_000
            da_costs = 25_000
            site_works = 80_000
            professional_fees = 30_000
            council_contributions = 20_000
            landscaping = 10_000
            build_cost = 0
            contingency = int((demolition + da_costs + site_works + 
                             professional_fees + council_contributions) * 0.10)
            total_build = (demolition + da_costs + site_works + professional_fees + 
                          council_contributions + landscaping + contingency)
        elif dev_type == 'knockdown_rebuild':
            dwelling_size = 250
            demolition = 35_000
            da_costs = 20_000
            site_works = 20_000
            professional_fees = 40_000
            council_contributions = 15_000
            landscaping = 20_000
            build_cost = dwelling_size * build_cost_per_sqm
            contingency = int((build_cost + demolition + da_costs + site_works + 
                             professional_fees + council_contributions + landscaping) * 0.10)
            total_build = (build_cost + demolition + da_costs + site_works + 
                          professional_fees + council_contributions + landscaping + contingency)
        else:
            return None

        # --- Holding costs ---
        holding_months = self.feas_cfg.get('holding_cost_months', 18)
        monthly_rate = self.feas_cfg.get('holding_cost_monthly_rate', 0.005)
        total_invested = purchase_total + total_build
        holding_cost = int(total_invested * monthly_rate * holding_months)

        # --- Total costs ---
        total_cost = purchase_total + total_build + holding_cost

        # --- End value estimate (IMPROVED in v2) ---
        end_value = self._estimate_end_value(suburb, state, dev_type, land_size, price)

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
            'site_works': site_works,
            'professional_fees': professional_fees,
            'council_contributions': council_contributions,
            'landscaping': landscaping,
            'contingency': contingency,
            'total_build': total_build,
            'holding_cost': holding_cost,
            'holding_months': holding_months,
            'total_cost': total_cost,
            'end_value': end_value,
            'end_value_method': 'suburb_median',
            'selling_costs': selling_costs,
            'net_proceeds': net_proceeds,
            'profit': profit,
            'profit_margin_pct': profit_margin_pct,
            'build_cost_per_sqm': build_cost_per_sqm,
            'suburb_median_house': self._get_suburb_median(suburb),
        }

    def _calc_stamp_duty(self, price: int, state: str = 'NSW') -> int:
        """Calculate stamp duty based on NSW rates (from 1 July 2025)."""
        if state != 'NSW':
            # Rough estimate for other states
            return int(price * 0.055)
        
        # NSW rates from 1 July 2025
        if price <= 17_000:
            return int(price * 0.0125)
        elif price <= 36_000:
            return int(212 + (price - 17_000) * 0.015)
        elif price <= 97_000:
            return int(497 + (price - 36_000) * 0.0175)
        elif price <= 364_000:
            return int(1_565 + (price - 97_000) * 0.035)
        elif price <= 1_240_000:
            return int(10_912 + (price - 364_000) * 0.045)
        else:
            return int(50_332 + (price - 1_240_000) * 0.055)

    def _determine_dev_type(self, listing: Dict, land_size: Optional[float]) -> str:
        """Determine the most likely development type."""
        text = ' '.join([
            listing.get('headline', ''),
            listing.get('description', ''),
        ]).lower()

        if any(kw in text for kw in ['duplex', 'dual occ', 'dual occupancy']):
            return 'duplex'
        if any(kw in text for kw in ['subdivide', 'subdivision', 'subdividable']):
            return 'subdivision'

        if land_size:
            if land_size >= 1000:
                return 'subdivision'
            elif land_size >= 550:
                return 'duplex'

        zoning = listing.get('zoning', '')
        if zoning:
            z = zoning.upper()
            if z in ('R3', 'R4', 'RGZ', 'MUZ'):
                return 'duplex'

        return 'knockdown_rebuild'

    def _estimate_end_value(self, suburb: str, state: str,
                            dev_type: str, land_size: Optional[float],
                            purchase_price: int = 0) -> int:
        """
        Estimate end value based on suburb median house prices.
        
        v2 Logic:
        - Duplex: Each dwelling = ~85% of suburb median house price × 2
        - Subdivision: Each lot = ~50% of median house price × num_lots
        - KDR: New build = ~115% of suburb median house price
        """
        if dev_type == 'duplex':
            duplex_each = self._get_duplex_end_value_each(suburb)
            if duplex_each:
                return duplex_each * 2
            # Fallback: use purchase price with conservative multiplier
            return int(purchase_price * 2.0) if purchase_price else 0

        elif dev_type == 'subdivision':
            median = self._get_suburb_median(suburb)
            if median and land_size and land_size >= 1000:
                num_lots = int(land_size / 450)
                lot_value = int(median * 0.50)  # Land value ~50% of house
                return lot_value * num_lots
            if median:
                return median
            return int(purchase_price * 1.3) if purchase_price else 0

        elif dev_type == 'knockdown_rebuild':
            median = self._get_suburb_median(suburb)
            if median:
                return int(median * 1.15)  # New build premium
            return int(purchase_price * 1.2) if purchase_price else 0

        return int(purchase_price * 1.2) if purchase_price else 0

    def estimate_listings(self, listings: list) -> list:
        """Estimate feasibility for a batch of listings."""
        for listing in listings:
            feas = self.estimate(listing)
            if feas:
                listing['feasibility_json'] = json.dumps(feas)
        return listings
