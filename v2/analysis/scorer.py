"""
Development Opportunity Scorer

Scores each listing 0-100 for development potential:
- Land size (wider/larger = more potential)
- Estimated frontage
- Price vs land value ratio
- Dwelling age (older = more likely knockdown)
- Zoning (R3/R4/RGZ = medium+ density)
- Keywords (DA approved, development potential, etc.)
"""

import re
import json
from typing import Dict, List, Optional, Tuple


class DevelopmentScorer:
    """Score listings for development potential on a 0-100 scale."""

    # Keywords that signal development opportunity (positive)
    POSITIVE_KEYWORDS = [
        'development potential', 'development site', 'developer',
        'da approved', 'da approval', 'development application',
        'stca', 'subject to council approval',
        'subdivide', 'subdivision', 'subdividable',
        'duplex', 'dual occupancy', 'dual occ',
        'granny flat', 'secondary dwelling',
        'knockdown rebuild', 'knock down', 'knock-down',
        'rebuild', 'build your dream',
        'land value', 'land only', 'vacant land',
        'corner block', 'corner position', 'corner lot',
        'wide frontage', 'north facing',
        'r3', 'r4', 'medium density', 'high density',
        'rgz', 'residential growth zone',
        'mixed use', 'b4', 'e1',
        'flat block', 'level block',
        'two street frontage', 'dual access',
        'rear lane', 'rear access', 'lane access',
        'original condition', 'original home',
        'deceased estate', 'executor', 'must sell', 'must be sold',
        'unrenovated', 'un-renovated',
        'investor', 'investment opportunity',
        'holding income',
    ]

    # Keywords that reduce development score
    NEGATIVE_KEYWORDS = [
        'heritage', 'heritage listed', 'heritage overlay',
        'conservation', 'conservation area',
        'flood zone', 'flood prone', 'flood affected',
        'bushfire', 'bap', 'flame zone',
        'easement', 'right of way',
        'strata', 'body corporate', 'common property',
        'leasehold',
        'steep', 'steep slope', 'sloping',
        'contaminated', 'remediation',
    ]

    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.weights = self.config.get('scoring', {
            'land_size_weight': 0.25,
            'frontage_weight': 0.15,
            'price_value_weight': 0.15,
            'dwelling_age_weight': 0.15,
            'zoning_weight': 0.15,
            'keyword_weight': 0.10,
            'feasibility_weight': 0.05,
        })

    def score(self, listing: Dict) -> Tuple[float, Dict, List[str]]:
        """
        Score a listing for development potential.
        
        Returns:
            (score, breakdown, flags) where:
            - score: 0-100 float
            - breakdown: dict of component scores
            - flags: list of notable flags
        """
        breakdown = {}
        flags = []

        # 1. Land size score (25%)
        land_score, land_flags = self._score_land_size(listing)
        breakdown['land_size'] = land_score
        flags.extend(land_flags)

        # 2. Frontage score (15%)
        frontage_score, frontage_flags = self._score_frontage(listing)
        breakdown['frontage'] = frontage_score
        flags.extend(frontage_flags)

        # 3. Price/value score (15%)
        price_score, price_flags = self._score_price_value(listing)
        breakdown['price_value'] = price_score
        flags.extend(price_flags)

        # 4. Dwelling age score (15%)
        age_score, age_flags = self._score_dwelling_age(listing)
        breakdown['dwelling_age'] = age_score
        flags.extend(age_flags)

        # 5. Zoning score (15%)
        zoning_score, zoning_flags = self._score_zoning(listing)
        breakdown['zoning'] = zoning_score
        flags.extend(zoning_flags)

        # 6. Keyword analysis (10%)
        keyword_score, keyword_flags = self._score_keywords(listing)
        breakdown['keywords'] = keyword_score
        flags.extend(keyword_flags)

        # 7. Feasibility bonus (5%)
        feas_score = self._score_feasibility_bonus(listing)
        breakdown['feasibility'] = feas_score

        # Calculate weighted total
        total = (
            land_score * self.weights.get('land_size_weight', 0.25) +
            frontage_score * self.weights.get('frontage_weight', 0.15) +
            price_score * self.weights.get('price_value_weight', 0.15) +
            age_score * self.weights.get('dwelling_age_weight', 0.15) +
            zoning_score * self.weights.get('zoning_weight', 0.15) +
            keyword_score * self.weights.get('keyword_weight', 0.10) +
            feas_score * self.weights.get('feasibility_weight', 0.05)
        )

        # Clamp to 0-100
        total = max(0, min(100, round(total, 1)))

        return total, breakdown, flags

    def _score_land_size(self, listing: Dict) -> Tuple[float, List[str]]:
        """Score based on land size. Bigger = better for development."""
        land = listing.get('land_size_sqm')
        flags = []

        if not land:
            # Try to extract from description
            land = self._extract_land_from_text(listing)
            if land:
                flags.append(f'Land {land}m² (from description)')

        if not land:
            return 30, flags  # Unknown — neutral-ish

        if land >= 1000:
            flags.append(f'🏗️ Large lot {land}m² — excellent for subdivision')
            return 100, flags
        elif land >= 800:
            flags.append(f'Large lot {land}m² — good for duplex/subdivision')
            return 90, flags
        elif land >= 700:
            flags.append(f'Good lot {land}m² — duplex potential')
            return 80, flags
        elif land >= 600:
            flags.append(f'Decent lot {land}m² — possible duplex (STCA)')
            return 65, flags
        elif land >= 550:
            flags.append(f'Minimum lot {land}m² — tight duplex potential')
            return 50, flags
        elif land >= 450:
            return 30, flags
        else:
            return 15, flags

    def _score_frontage(self, listing: Dict) -> Tuple[float, List[str]]:
        """Score based on estimated frontage. Wider = easier to subdivide."""
        frontage = listing.get('frontage_m')
        flags = []

        if not frontage:
            # Estimate from keywords
            text = self._get_full_text(listing).lower()
            frontage_match = re.search(r'(\d+\.?\d*)\s*m?\s*(?:frontage|wide|front)', text)
            if frontage_match:
                frontage = float(frontage_match.group(1))
                flags.append(f'Frontage ~{frontage}m (from listing text)')

        if not frontage:
            # Rough estimate from land size (assume 2:3 ratio)
            land = listing.get('land_size_sqm')
            if land and land > 0:
                frontage = (land / 1.5) ** 0.5  # sqrt(area / ratio)
                # Don't flag estimated values

        if not frontage:
            return 40, flags  # Unknown

        if frontage >= 20:
            flags.append(f'Wide frontage ~{frontage:.0f}m — easy subdivision')
            return 100, flags
        elif frontage >= 16:
            flags.append(f'Good frontage ~{frontage:.0f}m — duplex viable')
            return 85, flags
        elif frontage >= 14:
            flags.append(f'Adequate frontage ~{frontage:.0f}m')
            return 65, flags
        elif frontage >= 12:
            return 45, flags
        elif frontage >= 10:
            return 30, flags
        else:
            return 15, flags

    def _score_price_value(self, listing: Dict) -> Tuple[float, List[str]]:
        """Score based on price relative to the region's price range."""
        flags = []
        price = listing.get('price_low')
        if not price:
            return 40, flags  # Unknown

        # Get region config for context
        region_name = listing.get('region_name', '')

        # Check if price is below region midpoint (more room for development profit)
        regions = self.config.get('regions', [])
        region_cfg = None
        for r in regions:
            if r.get('name') == region_name:
                region_cfg = r
                break

        if region_cfg:
            min_p = region_cfg.get('price_min', 0)
            max_p = region_cfg.get('price_max', price * 2)
            mid = (min_p + max_p) / 2

            if price <= min_p:
                flags.append('💰 Below region minimum — potential value buy')
                return 100, flags
            elif price <= mid * 0.85:
                flags.append('Good price — well below midpoint')
                return 85, flags
            elif price <= mid:
                return 70, flags
            elif price <= max_p * 0.85:
                return 50, flags
            elif price <= max_p:
                return 35, flags
            else:
                return 15, flags

        return 50, flags

    def _score_dwelling_age(self, listing: Dict) -> Tuple[float, List[str]]:
        """Score based on age of dwelling. Older = more likely knockdown candidate."""
        flags = []
        year_built = listing.get('year_built')

        if not year_built:
            # Estimate from keywords
            year_built = self._estimate_era(listing)

        if not year_built:
            return 50, flags  # Unknown

        from datetime import datetime
        current_year = datetime.now().year
        age = current_year - year_built

        if age >= 60:
            flags.append(f'🏚️ Very old ({year_built}) — likely knockdown candidate')
            return 95, flags
        elif age >= 40:
            flags.append(f'Old dwelling ({year_built}) — knockdown candidate')
            return 80, flags
        elif age >= 25:
            flags.append(f'Aging dwelling ({year_built})')
            return 60, flags
        elif age >= 15:
            return 35, flags
        elif age >= 5:
            return 15, flags
        else:
            flags.append('Recent build — low knockdown potential')
            return 5, flags

    def _score_zoning(self, listing: Dict) -> Tuple[float, List[str]]:
        """Score based on zoning. Medium/high density zones score higher."""
        flags = []
        zoning = listing.get('zoning', '')

        if not zoning:
            # Try to extract from text
            text = self._get_full_text(listing).lower()
            zoning = self._extract_zoning(text)

        if not zoning:
            return 40, flags  # Unknown zoning

        zoning_upper = zoning.upper().strip()

        # NSW zonings
        if zoning_upper in ('R4', 'R4 HIGH DENSITY RESIDENTIAL'):
            flags.append('🏢 R4 zoning — high density allowed')
            return 100, flags
        elif zoning_upper in ('R3', 'R3 MEDIUM DENSITY RESIDENTIAL'):
            flags.append('🏘️ R3 zoning — medium density allowed')
            return 90, flags
        elif zoning_upper in ('B4', 'B4 MIXED USE'):
            flags.append('🏬 B4 Mixed Use zoning')
            return 85, flags
        elif zoning_upper in ('R2', 'R2 LOW DENSITY RESIDENTIAL'):
            flags.append('R2 zoning — low density (duplex STCA)')
            return 55, flags
        elif zoning_upper in ('R1', 'R1 GENERAL RESIDENTIAL'):
            return 50, flags

        # VIC zonings
        elif zoning_upper in ('RGZ', 'RESIDENTIAL GROWTH ZONE'):
            flags.append('🏘️ RGZ — Residential Growth Zone')
            return 90, flags
        elif zoning_upper in ('GRZ', 'GENERAL RESIDENTIAL ZONE'):
            flags.append('GRZ — General Residential')
            return 60, flags
        elif zoning_upper in ('NRZ', 'NEIGHBOURHOOD RESIDENTIAL ZONE'):
            flags.append('NRZ — Neighbourhood Residential (limited)')
            return 40, flags
        elif zoning_upper in ('MUZ', 'MIXED USE ZONE'):
            flags.append('MUZ — Mixed Use Zone')
            return 85, flags

        # QLD
        elif 'MEDIUM DENSITY' in zoning_upper:
            flags.append('Medium density zoning')
            return 80, flags
        elif 'LOW-MEDIUM' in zoning_upper:
            return 60, flags
        elif 'LOW DENSITY' in zoning_upper:
            return 45, flags

        return 40, flags

    def _score_keywords(self, listing: Dict) -> Tuple[float, List[str]]:
        """Score based on keyword analysis of listing text."""
        text = self._get_full_text(listing).lower()
        flags = []

        positive_count = 0
        negative_count = 0

        for kw in self.POSITIVE_KEYWORDS:
            if kw in text:
                positive_count += 1
                if kw in ('da approved', 'da approval'):
                    flags.append('✅ DA approved')
                elif kw in ('development potential', 'development site'):
                    flags.append('📋 Listed as development opportunity')
                elif 'subdivide' in kw or 'subdivision' in kw:
                    flags.append('📐 Subdivision mentioned')
                elif kw in ('duplex', 'dual occupancy', 'dual occ'):
                    flags.append('🏠🏠 Duplex/dual-occ mentioned')
                elif kw in ('corner block', 'corner position', 'corner lot'):
                    flags.append('📐 Corner block')
                elif kw in ('rear lane', 'rear access', 'lane access'):
                    flags.append('🚗 Rear lane access')
                elif kw in ('deceased estate', 'executor'):
                    flags.append('⚡ Deceased estate — motivated sale')

        for kw in self.NEGATIVE_KEYWORDS:
            if kw in text:
                negative_count += 1
                if 'heritage' in kw:
                    flags.append('⚠️ Heritage concerns')
                elif 'flood' in kw:
                    flags.append('⚠️ Flood risk')
                elif 'bushfire' in kw:
                    flags.append('⚠️ Bushfire risk')
                elif 'easement' in kw:
                    flags.append('⚠️ Easement present')

        # Calculate score
        score = 40  # Neutral base
        score += min(positive_count * 12, 60)  # Up to +60 for keywords
        score -= min(negative_count * 15, 40)   # Down to -40 for negative

        return max(0, min(100, score)), list(set(flags))  # Deduplicate flags

    def _score_feasibility_bonus(self, listing: Dict) -> float:
        """Bonus score if feasibility has been calculated and looks good."""
        feas = listing.get('feasibility_json')
        if not feas:
            return 40

        try:
            if isinstance(feas, str):
                feas = json.loads(feas)
            profit_margin = feas.get('profit_margin_pct', 0)
            if profit_margin >= 30:
                return 100
            elif profit_margin >= 20:
                return 80
            elif profit_margin >= 10:
                return 60
            elif profit_margin >= 0:
                return 40
            else:
                return 15
        except (json.JSONDecodeError, TypeError):
            return 40

    # ─── Helper methods ──────────────────────────────────────────────

    def _get_full_text(self, listing: Dict) -> str:
        """Get all text content from a listing for keyword analysis."""
        parts = [
            listing.get('headline', ''),
            listing.get('description', ''),
            listing.get('features_text', ''),
            listing.get('address', ''),
        ]
        return ' '.join(p for p in parts if p)

    def _extract_land_from_text(self, listing: Dict) -> Optional[float]:
        """Try to extract land size from listing description."""
        text = self._get_full_text(listing)
        patterns = [
            r'(\d{3,4})\s*(?:sq\.?\s*m|sqm|m²|m2)',
            r'land\s*(?:size|area)?\s*:?\s*(?:approx\.?)?\s*(\d{3,4})',
            r'(\d{3,4})\s*(?:square\s*)?(?:metres?|meters?)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = float(match.group(1))
                if 100 <= val <= 5000:  # Sanity check
                    return val
        return None

    def _estimate_era(self, listing: Dict) -> Optional[int]:
        """Estimate build era from listing text."""
        text = self._get_full_text(listing).lower()

        era_patterns = [
            (r'built\s*(?:in\s*)?(?:circa\s*)?(\d{4})', None),
            (r'(\d{4})\s*(?:build|built|constructed)', None),
            (r'circa\s*(\d{4})', None),
            (r'(?:19[2-9]\d|20[0-2]\d)s?\s*(?:home|house|dwelling|brick|weatherboard)', None),
        ]

        for pattern, _ in era_patterns:
            match = re.search(pattern, text)
            if match:
                year = int(match.group(1)) if match.group(1).isdigit() else None
                if year and 1900 <= year <= 2026:
                    return year

        # Keyword-based era estimation
        era_keywords = {
            'federation': 1910,
            'californian bungalow': 1925,
            'art deco': 1935,
            'post-war': 1955,
            'post war': 1955,
            'mid-century': 1960,
            '1960s': 1965,
            '1970s': 1975,
            '1980s': 1985,
            'brick veneer': 1975,
            'fibro': 1960,
            'weatherboard': 1950,
            'double brick': 1960,
        }

        for kw, year in era_keywords.items():
            if kw in text:
                return year

        return None

    def _extract_zoning(self, text: str) -> Optional[str]:
        """Extract zoning code from text."""
        patterns = [
            r'(R[1-5])\s',
            r'(R[1-5]\s+\w+\s+density)',
            r'(RGZ|GRZ|NRZ|MUZ|C1Z|C2Z)',
            r'zone[d]?\s+(R[1-5]|RGZ|GRZ|NRZ)',
            r'(B[1-4])\s',
            r'(medium\s+density|high\s+density)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        return None

    def score_listings(self, listings: List[Dict]) -> List[Dict]:
        """Score a batch of listings and attach scores."""
        for listing in listings:
            score, breakdown, flags = self.score(listing)
            listing['development_score'] = score
            listing['score_breakdown'] = json.dumps(breakdown)
            listing['development_flags'] = json.dumps(flags)
        return listings
