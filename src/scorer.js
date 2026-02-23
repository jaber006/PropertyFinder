const { getDistance } = require('geolib');
const criteria = require('../config/criteria.json');

/**
 * Score a listing 0-100 based on weighted criteria
 */
function scoreListing(listing) {
  const weights = criteria.scoring;
  let score = 0;

  // 1. Proximity to school (40%)
  if (listing.distance_to_school_km != null) {
    const maxDist = criteria.keyLocations[0].maxDistanceKm || 5;
    const proxScore = Math.max(0, 1 - (listing.distance_to_school_km / maxDist));
    score += proxScore * weights.proximity_to_school_weight * 100;
  }

  // 2. Price below budget midpoint (20%)
  const budgetMid = (criteria.search.budget.min + criteria.search.budget.max) / 2;
  if (listing.price_low) {
    const price = listing.price_high ? (listing.price_low + listing.price_high) / 2 : listing.price_low;
    if (price <= criteria.search.budget.min) {
      score += weights.price_below_budget_weight * 100; // max score - well under budget
    } else if (price <= budgetMid) {
      score += weights.price_below_budget_weight * 75;
    } else if (price <= criteria.search.budget.max) {
      const ratio = (criteria.search.budget.max - price) / (criteria.search.budget.max - budgetMid);
      score += ratio * weights.price_below_budget_weight * 50;
    }
    // Over budget = 0 for this component
  }

  // 3. Land size (15%) — bigger is better for family home
  if (listing.land_size_sqm) {
    if (listing.land_size_sqm >= 700) {
      score += weights.land_size_weight * 100;
    } else if (listing.land_size_sqm >= 500) {
      score += weights.land_size_weight * 75;
    } else if (listing.land_size_sqm >= 350) {
      score += weights.land_size_weight * 50;
    } else {
      score += weights.land_size_weight * 25;
    }
  }

  // 4. Bedrooms (10%) — 4+ is ideal
  if (listing.bedrooms >= 5) {
    score += weights.bedrooms_weight * 100;
  } else if (listing.bedrooms >= 4) {
    score += weights.bedrooms_weight * 80;
  } else if (listing.bedrooms >= 3) {
    score += weights.bedrooms_weight * 50;
  }

  // 5. Condition/quality signals (10%) — keyword analysis
  const desc = (listing.headline + ' ' + listing.description).toLowerCase();
  const positiveSignals = ['renovated', 'modern', 'new kitchen', 'new bathroom', 'updated',
    'polished', 'immaculate', 'move-in ready', 'north facing', 'sunny', 'spacious'];
  const negativeSignals = ['needs work', 'handyman', 'potential', 'as-is', 'deceased estate',
    'original condition', 'investor', 'must sell'];

  let conditionScore = 50; // neutral baseline
  for (const signal of positiveSignals) {
    if (desc.includes(signal)) conditionScore = Math.min(100, conditionScore + 10);
  }
  for (const signal of negativeSignals) {
    if (desc.includes(signal)) conditionScore = Math.max(0, conditionScore - 10);
  }
  score += (conditionScore / 100) * weights.condition_weight * 100;

  // 6. Transport proximity (5%)
  if (listing.lat && listing.lng) {
    const stations = criteria.keyLocations.filter(l => l.name.includes('Station'));
    let bestStationDist = Infinity;
    for (const station of stations) {
      const dist = getDistance(
        { latitude: listing.lat, longitude: listing.lng },
        { latitude: station.lat, longitude: station.lng }
      ) / 1000;
      bestStationDist = Math.min(bestStationDist, dist);
    }
    if (bestStationDist <= 0.5) {
      score += weights.transport_weight * 100;
    } else if (bestStationDist <= 1) {
      score += weights.transport_weight * 70;
    } else if (bestStationDist <= 2) {
      score += weights.transport_weight * 40;
    }
  }

  return Math.round(score * 10) / 10;
}

/**
 * Rank an array of listings by score
 */
function rankListings(listings) {
  return listings
    .map(l => ({ ...l, score: scoreListing(l) }))
    .sort((a, b) => b.score - a.score);
}

module.exports = { scoreListing, rankListings };
