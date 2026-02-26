/**
 * PropertyFinder v2 — Dashboard App
 * Map + Cards + Filters + Detail Panel + Feasibility Calculator
 * + OSM Overlays (Schools, Stations) + Suburb Heatmap + Mobile Responsive
 */

// ---- State ----
let allListings = [];
let filteredListings = [];
let map = null;
let markersLayer = null;
let schoolsLayer = null;
let stationsLayer = null;
let heatmapLayer = null;
let heatmapLabelsLayer = null;
let selectedListingId = null;
let stats = {};
let detailPanelOpen = false;
let heatmapActive = false;
let mobileCardsExpanded = false;

// ---- Score Helpers ----
function scoreClass(score) {
    if (score >= 65) return 'hot';
    if (score >= 50) return 'good';
    if (score >= 35) return 'below';
    return 'poor';
}

function scoreBadgeClass(score) {
    return 'score-' + scoreClass(score);
}

function scoreColor(score) {
    if (score >= 65) return '#3fb950';
    if (score >= 50) return '#d29922';
    if (score >= 35) return '#db6d28';
    return '#f85149';
}

function scoreLabel(score) {
    if (score >= 65) return 'Hot';
    if (score >= 50) return 'Good';
    if (score >= 35) return 'Below Avg';
    return 'Poor';
}

function barColor(value, max) {
    const pct = max > 0 ? (value / max) : 0;
    if (pct > 0.7) return '#3fb950';
    if (pct > 0.4) return '#d29922';
    return '#f85149';
}

function barColorClass(value, max) {
    const pct = max > 0 ? (value / max) : 0;
    if (pct > 0.7) return 'seg-green';
    if (pct > 0.4) return 'seg-yellow';
    return 'seg-red';
}

// ---- Format Helpers ----
function formatPrice(display, low, high) {
    if (display && display !== 'Contact Agent' && display !== '' && display !== 'unknown') return display;
    if (low && high && low !== high) return `$${(low/1000).toFixed(0)}K - $${(high/1000).toFixed(0)}K`;
    if (low) return `$${low.toLocaleString()}`;
    if (high) return `$${high.toLocaleString()}`;
    return 'Contact Agent';
}

function formatNumber(n) {
    if (n == null) return '—';
    return n.toLocaleString();
}

function formatCurrency(n) {
    if (n == null) return '—';
    if (Math.abs(n) >= 1000000) return `$${(n / 1000000).toFixed(2)}M`;
    if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(0)}K`;
    return `$${n.toLocaleString()}`;
}

function formatDistance(m) {
    if (m == null) return '—';
    if (m >= 1000) return `${(m / 1000).toFixed(1)}km`;
    return `${Math.round(m)}m`;
}

function roadClass(type) {
    if (!type) return 'road-unknown';
    const t = type.toLowerCase();
    if (t === 'residential' || t === 'living_street') return 'road-residential';
    if (t === 'tertiary' || t === 'moderate road') return 'road-tertiary';
    if (t === 'secondary') return 'road-secondary';
    if (t === 'primary' || t === 'trunk' || t.includes('primary') || t.includes('trunk')) return 'road-primary';
    return 'road-unknown';
}

// ---- Map Setup ----
function initMap() {
    map = L.map('map', {
        center: [-33.945, 151.13],
        zoom: 14,
        zoomControl: true,
        attributionControl: true,
    });

    // Dark tile layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
    }).addTo(map);

    markersLayer = L.markerClusterGroup({
        maxClusterRadius: 40,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        zoomToBoundsOnClick: true,
        iconCreateFunction: function(cluster) {
            const count = cluster.getChildCount();
            let size = 'small';
            if (count >= 20) size = 'large';
            else if (count >= 10) size = 'medium';
            return L.divIcon({
                html: `<div>${count}</div>`,
                className: `marker-cluster marker-cluster-${size}`,
                iconSize: L.point(40, 40),
            });
        }
    });
    map.addLayer(markersLayer);

    // POI layers
    schoolsLayer = L.layerGroup().addTo(map);
    stationsLayer = L.layerGroup().addTo(map);
    heatmapLayer = L.layerGroup();
    heatmapLabelsLayer = L.layerGroup();
}

function createMarkerIcon(score) {
    const color = scoreColor(score);
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="28" height="36" viewBox="0 0 28 36">
        <path d="M14 0C6.27 0 0 6.27 0 14c0 10.5 14 22 14 22s14-11.5 14-22C28 6.27 21.73 0 14 0z" fill="${color}" stroke="#0d1117" stroke-width="1.5"/>
        <circle cx="14" cy="13" r="6" fill="#0d1117" opacity="0.4"/>
        <text x="14" y="17" text-anchor="middle" fill="#fff" font-size="10" font-weight="bold" font-family="sans-serif">${Math.round(score)}</text>
    </svg>`;
    return L.divIcon({
        html: svg,
        className: 'custom-marker',
        iconSize: [28, 36],
        iconAnchor: [14, 36],
        popupAnchor: [0, -36],
    });
}

function createSchoolIcon() {
    return L.divIcon({
        html: '<div style="font-size:16px;text-align:center;line-height:24px;width:24px;height:24px;background:rgba(88,166,255,0.2);border:2px solid #58a6ff;border-radius:50%;display:flex;align-items:center;justify-content:center;">🏫</div>',
        className: 'custom-marker',
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        popupAnchor: [0, -14],
    });
}

function createStationIcon() {
    return L.divIcon({
        html: '<div style="font-size:14px;text-align:center;line-height:26px;width:26px;height:26px;background:rgba(248,81,73,0.2);border:2px solid #f85149;border-radius:4px;display:flex;align-items:center;justify-content:center;">🚉</div>',
        className: 'custom-marker',
        iconSize: [26, 26],
        iconAnchor: [13, 13],
        popupAnchor: [0, -15],
    });
}

function updateMapMarkers() {
    markersLayer.clearLayers();

    const bounds = [];
    filteredListings.forEach(listing => {
        if (listing.lat == null || listing.lng == null) return;

        const marker = L.marker([listing.lat, listing.lng], {
            icon: createMarkerIcon(listing.development_score || 0),
        });

        const price = formatPrice(listing.price_display, listing.price_low, listing.price_high);
        const score = listing.development_score || 0;
        const cls = scoreBadgeClass(score);

        let popupHtml = `
            <div class="popup-title">${listing.address || 'Unknown'}</div>
            <div class="popup-details">
                <span class="label">Price</span><span>${price}</span>
                <span class="label">Land</span><span>${listing.land_size_sqm ? listing.land_size_sqm.toFixed(0) + ' sqm' : '—'}</span>
                <span class="label">Beds/Bath</span><span>${listing.bedrooms || '—'} / ${listing.bathrooms || '—'}</span>
                <span class="label">Score</span><span class="popup-score ${cls}">${score.toFixed(0)}</span>
                <span class="label">Type</span><span>${listing.property_type || '—'}</span>
            </div>`;

        if (listing.url) {
            popupHtml += `<a class="popup-link" href="${listing.url}" target="_blank">View on REA →</a>`;
        }

        popupHtml += `<br><a class="popup-link" href="#" onclick="openDetailPanel('${listing.id}'); return false;">Full Details →</a>`;

        marker.bindPopup(popupHtml, { maxWidth: 280 });

        marker.on('click', () => {
            highlightCard(listing.id);
        });

        markersLayer.addLayer(marker);
        bounds.push([listing.lat, listing.lng]);
    });

    if (bounds.length > 0) {
        map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
    }

    // Update POI layers
    updatePOILayers();
}

// ---- POI Overlay Layers ----
function updatePOILayers() {
    // Collect unique schools and stations from all filtered listings
    // POI lat/lng now included in API response
    const schoolsMap = new Map();
    const stationsMap = new Map();

    filteredListings.forEach(listing => {
        if (listing.nearby_schools) {
            listing.nearby_schools.forEach(s => {
                if (s.lat && s.lng) {
                    const key = `${s.lat.toFixed(5)},${s.lng.toFixed(5)}`;
                    if (!schoolsMap.has(key)) {
                        schoolsMap.set(key, { name: s.name, type: s.type, lat: s.lat, lng: s.lng });
                    }
                }
            });
        }
        if (listing.nearby_stations) {
            listing.nearby_stations.forEach(s => {
                if (s.lat && s.lng) {
                    const key = `${s.lat.toFixed(5)},${s.lng.toFixed(5)}`;
                    if (!stationsMap.has(key)) {
                        stationsMap.set(key, { name: s.name, lat: s.lat, lng: s.lng });
                    }
                }
            });
        }
    });

    // Rebuild school layer
    schoolsLayer.clearLayers();
    schoolsMap.forEach(school => {
        const m = L.marker([school.lat, school.lng], { icon: createSchoolIcon() });
        m.bindPopup(`<div class="poi-popup"><div class="poi-name">🏫 ${school.name}</div><div class="poi-type">${school.type || 'School'}</div></div>`, { maxWidth: 220 });
        schoolsLayer.addLayer(m);
    });

    // Rebuild station layer
    stationsLayer.clearLayers();
    stationsMap.forEach(station => {
        const m = L.marker([station.lat, station.lng], { icon: createStationIcon() });
        m.bindPopup(`<div class="poi-popup"><div class="poi-name">🚉 ${station.name} Station</div></div>`, { maxWidth: 220 });
        stationsLayer.addLayer(m);
    });
}

function toggleLayer(layerName) {
    const checkbox = document.getElementById(`layer-${layerName}`);
    const checked = checkbox ? checkbox.checked : false;

    if (layerName === 'schools') {
        if (checked) map.addLayer(schoolsLayer);
        else map.removeLayer(schoolsLayer);
    } else if (layerName === 'stations') {
        if (checked) map.addLayer(stationsLayer);
        else map.removeLayer(stationsLayer);
    } else if (layerName === 'listings') {
        if (checked) map.addLayer(markersLayer);
        else map.removeLayer(markersLayer);
    }
}

// ---- Suburb Heatmap ----
function toggleHeatmap() {
    const checkbox = document.getElementById('layer-heatmap');
    heatmapActive = checkbox ? checkbox.checked : false;

    if (heatmapActive) {
        buildHeatmap();
        map.addLayer(heatmapLayer);
        map.addLayer(heatmapLabelsLayer);
    } else {
        map.removeLayer(heatmapLayer);
        map.removeLayer(heatmapLabelsLayer);
    }
}

function buildHeatmap() {
    heatmapLayer.clearLayers();
    heatmapLabelsLayer.clearLayers();

    // Aggregate by suburb
    const suburbData = {};
    filteredListings.forEach(listing => {
        const sub = listing.suburb;
        if (!sub) return;
        if (!suburbData[sub]) {
            suburbData[sub] = { scores: [], lats: [], lngs: [], count: 0 };
        }
        suburbData[sub].scores.push(listing.development_score || 0);
        suburbData[sub].count++;
        if (listing.lat && listing.lng) {
            suburbData[sub].lats.push(listing.lat);
            suburbData[sub].lngs.push(listing.lng);
        }
    });

    Object.entries(suburbData).forEach(([suburb, data]) => {
        if (data.lats.length === 0) return;

        const avgScore = data.scores.reduce((a, b) => a + b, 0) / data.scores.length;
        const bestScore = Math.max(...data.scores);
        const centerLat = data.lats.reduce((a, b) => a + b, 0) / data.lats.length;
        const centerLng = data.lngs.reduce((a, b) => a + b, 0) / data.lngs.length;

        // Create a circle for the suburb
        const color = scoreColor(avgScore);
        const radius = Math.max(300, Math.min(800, data.count * 80));

        const circle = L.circle([centerLat, centerLng], {
            radius: radius,
            color: color,
            fillColor: color,
            fillOpacity: 0.2,
            weight: 2,
            opacity: 0.6,
        });

        // Tooltip on hover
        circle.bindTooltip(`
            <div class="heatmap-tooltip">
                <div class="ht-suburb">${suburb}</div>
                <div class="ht-row"><span class="ht-label">Listings</span><span>${data.count}</span></div>
                <div class="ht-row"><span class="ht-label">Avg Score</span><span style="color:${color}">${avgScore.toFixed(1)}</span></div>
                <div class="ht-row"><span class="ht-label">Best Score</span><span>${bestScore.toFixed(1)}</span></div>
            </div>
        `, { className: 'heatmap-tooltip-wrapper', direction: 'top' });

        heatmapLayer.addLayer(circle);

        // Label
        const label = L.divIcon({
            html: `<div style="white-space:nowrap;font-size:11px;font-weight:600;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,0.9);">${suburb}<br><span style="font-size:10px;opacity:0.8">${data.count} · ${avgScore.toFixed(0)}avg</span></div>`,
            className: 'suburb-heatmap-label',
            iconSize: [100, 30],
            iconAnchor: [50, 15],
        });
        heatmapLabelsLayer.addLayer(L.marker([centerLat, centerLng], { icon: label, interactive: false }));
    });
}

// ---- Cards ----
function renderCards() {
    const container = document.getElementById('cards-container');
    const countEl = document.getElementById('listing-count');
    const mobileCount = document.getElementById('mobile-cards-count');

    const countText = `${filteredListings.length} listing${filteredListings.length !== 1 ? 's' : ''} found`;
    countEl.textContent = countText;
    if (mobileCount) mobileCount.textContent = countText;

    if (filteredListings.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">🏠</div>
                <h3>No listings match filters</h3>
                <p>Try adjusting your filter criteria</p>
            </div>`;
        return;
    }

    container.innerHTML = filteredListings.map(listing => {
        const score = listing.development_score || 0;
        const badgeClass = scoreBadgeClass(score);
        const price = formatPrice(listing.price_display, listing.price_low, listing.price_high);

        // Score breakdown
        const sb = listing.score_breakdown || {};
        const cats = sb.categories || {};
        const land = sb.land_development || 0;
        const priceScore = sb.price_value || 0;
        const location = sb.location_quality || 0;
        const growth = sb.growth_potential || 0;

        // Score bars
        const bars = [
            { label: 'Land', value: land, max: 35 },
            { label: 'Price', value: priceScore, max: 20 },
            { label: 'Loc', value: location, max: 30 },
            { label: 'Growth', value: growth, max: 15 },
        ];

        let barsHtml = '<div class="card-score-bars">' + bars.map(b => {
            const pct = b.max > 0 ? Math.min(100, (b.value / b.max) * 100) : 0;
            const color = barColor(b.value, b.max);
            return `<div class="score-bar-item">
                <div class="score-bar-label">${b.label} ${b.value.toFixed(0)}/${b.max}</div>
                <div class="score-bar-track"><div class="score-bar-fill" style="width:${pct}%;background:${color}"></div></div>
            </div>`;
        }).join('') + '</div>';

        // POI info
        let poiHtml = '<div class="card-poi-info">';

        // Top 3 schools
        const schools = (listing.nearby_schools || []).slice(0, 3);
        if (schools.length > 0) {
            poiHtml += schools.map(s =>
                `<div class="card-poi-row"><span class="poi-icon">🏫</span><span class="poi-text">${s.name}</span><span style="color:var(--text-muted);font-size:11px">${formatDistance(s.distance_m)}</span></div>`
            ).join('');
        }

        // Nearest station
        const stations = (listing.nearby_stations || []).slice(0, 1);
        if (stations.length > 0) {
            poiHtml += `<div class="card-poi-row"><span class="poi-icon">🚉</span><span class="poi-text">${stations[0].name} Station</span><span style="color:var(--text-muted);font-size:11px">${formatDistance(stations[0].distance_m)}</span></div>`;
        }

        poiHtml += '</div>';

        // Road type
        let roadHtml = '';
        if (listing.road_type && listing.road_type !== 'Unknown') {
            const rc = roadClass(listing.road_type);
            roadHtml = `<span class="road-indicator ${rc}"><i class="fas fa-road"></i> ${listing.road_type}${listing.road_name ? ' — ' + listing.road_name : ''}</span>`;
        }

        // Flags: location + growth + development
        let flagsHtml = '';
        const allFlags = [];
        if (listing.location_flags && Array.isArray(listing.location_flags)) {
            listing.location_flags.forEach(f => allFlags.push({ text: f, cls: 'location-flag' }));
        }
        if (listing.growth_flags && Array.isArray(listing.growth_flags)) {
            listing.growth_flags.forEach(f => allFlags.push({ text: f, cls: 'growth-flag' }));
        }
        if (listing.development_flags && Array.isArray(listing.development_flags)) {
            listing.development_flags.forEach(f => {
                // Don't duplicate flags that are already in location/growth
                if (!allFlags.find(af => af.text === f)) {
                    allFlags.push({ text: f, cls: '' });
                }
            });
        }
        if (allFlags.length > 0) {
            flagsHtml = '<div class="card-flags">' + allFlags.slice(0, 5).map(f =>
                `<span class="flag-tag ${f.cls}">${f.text}</span>`
            ).join('') + (allFlags.length > 5 ? `<span class="flag-tag" style="opacity:0.5">+${allFlags.length - 5} more</span>` : '') + '</div>';
        }

        // Feasibility summary
        let feasHtml = '';
        if (listing.feasibility_json && typeof listing.feasibility_json === 'object') {
            const f = listing.feasibility_json;
            const isProfit = f.profit >= 0;
            const cls = isProfit ? 'profit' : 'loss';
            const devType = (f.dev_type || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            feasHtml = `
                <div class="card-feasibility ${cls}">
                    ${devType}: ${formatCurrency(f.total_cost)} → ${formatCurrency(f.end_value)} = 
                    <strong>${isProfit ? '+' : ''}${formatCurrency(f.profit)}</strong> (${f.profit_margin_pct}%)
                </div>`;
        }

        // New badge
        const newBadge = listing.is_new ? `<span class="new-badge">NEW</span>` : '';

        return `
            <div class="listing-card" data-id="${listing.id}" onclick="openDetailPanel('${listing.id}')">
                ${newBadge}
                <div class="card-header">
                    <div class="card-address">
                        ${listing.address || 'Unknown Address'}
                        <div class="card-suburb">${listing.suburb || ''}${listing.postcode ? ' ' + listing.postcode : ''}</div>
                    </div>
                    <div class="score-badge ${badgeClass}">${score.toFixed(0)}</div>
                </div>
                ${barsHtml}
                <div class="card-meta">
                    <span class="card-price">${price}</span>
                    ${listing.land_size_sqm ? `<span><span class="icon">📐</span>${listing.land_size_sqm.toFixed(0)} sqm</span>` : ''}
                    ${listing.bedrooms ? `<span><span class="icon">🛏</span>${listing.bedrooms}</span>` : ''}
                    ${listing.bathrooms ? `<span><span class="icon">🚿</span>${listing.bathrooms}</span>` : ''}
                    ${listing.parking ? `<span><span class="icon">🚗</span>${listing.parking}</span>` : ''}
                </div>
                ${poiHtml}
                ${roadHtml ? `<div style="margin-bottom:6px">${roadHtml}</div>` : ''}
                ${flagsHtml}
                ${feasHtml}
                ${listing.url ? `<a class="card-link" href="${listing.url}" target="_blank" onclick="event.stopPropagation()">View on REA →</a>` : ''}
            </div>`;
    }).join('');
}

function highlightCard(id) {
    document.querySelectorAll('.listing-card').forEach(el => el.classList.remove('active'));
    const card = document.querySelector(`.listing-card[data-id="${id}"]`);
    if (card) {
        card.classList.add('active');
        card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// ---- Detail Side Panel ----
async function openDetailPanel(id) {
    selectedListingId = id;
    const panel = document.getElementById('detail-panel');
    const body = document.getElementById('detail-panel-body');
    const title = document.getElementById('detail-panel-title');

    panel.classList.add('open');
    detailPanelOpen = true;
    body.innerHTML = '<div class="loading-spinner">Loading...</div>';
    title.textContent = 'Loading...';

    // Find listing in local data first for instant render
    const local = filteredListings.find(l => l.id === id) || allListings.find(l => l.id === id);
    if (local) {
        renderDetailPanel(local);
    }

    // Also fetch full detail from API for complete data
    try {
        const resp = await fetch(`/api/listings/${encodeURIComponent(id)}`);
        if (resp.ok) {
            const listing = await resp.json();
            renderDetailPanel(listing);
        }
    } catch (e) {
        if (!local) {
            body.innerHTML = `<div class="empty-state"><h3>Error loading listing</h3><p>${e.message}</p></div>`;
        }
    }

    highlightCard(id);
}

function closeDetailPanel() {
    const panel = document.getElementById('detail-panel');
    panel.classList.remove('open');
    detailPanelOpen = false;
    selectedListingId = null;
    document.querySelectorAll('.listing-card').forEach(el => el.classList.remove('active'));
}

function renderDetailPanel(listing) {
    const body = document.getElementById('detail-panel-body');
    const title = document.getElementById('detail-panel-title');

    title.textContent = listing.address || 'Unknown Address';

    const score = listing.development_score || 0;
    const price = formatPrice(listing.price_display, listing.price_low, listing.price_high);
    const badgeClass = scoreBadgeClass(score);
    const color = scoreColor(score);

    // Score breakdown chart
    const sb = listing.score_breakdown || {};
    const scoreItems = [
        { label: 'Land', value: sb.land_development || 0, max: 35 },
        { label: 'Price', value: sb.price_value || 0, max: 20 },
        { label: 'Location', value: sb.location_quality || 0, max: 30 },
        { label: 'Growth', value: sb.growth_potential || 0, max: 15 },
    ];

    let chartHtml = '<div class="dp-score-chart">';
    scoreItems.forEach(item => {
        const pct = item.max > 0 ? Math.min(100, (item.value / item.max) * 100) : 0;
        const c = barColor(item.value, item.max);
        chartHtml += `
            <div class="dp-bar-row">
                <div class="dp-bar-label">${item.label}</div>
                <div class="dp-bar-track">
                    <div class="dp-bar-fill" style="width:${pct}%;background:${c}">
                        <span class="dp-bar-value">${item.value.toFixed(1)}/${item.max}</span>
                    </div>
                </div>
            </div>`;
    });
    chartHtml += '</div>';

    // Google Maps / Street View
    let streetViewHtml = '';
    if (listing.lat && listing.lng) {
        const mapsUrl = `https://www.google.com/maps/@${listing.lat},${listing.lng},3a,75y,0h,90t/data=!3m6!1e1!3m4!1s!2e0!7i16384!8i8192`;
        streetViewHtml = `
            <div class="dp-streetview">
                <a href="${mapsUrl}" target="_blank">
                    <i class="fas fa-street-view"></i>
                    <span>Open Street View</span>
                </a>
            </div>`;
    }

    // POI lists
    let poisHtml = '';
    const poiCategories = [
        { key: 'nearby_schools', icon: '🏫', label: 'Schools', items: listing.nearby_schools || [] },
        { key: 'nearby_stations', icon: '🚉', label: 'Stations', items: listing.nearby_stations || [] },
        { key: 'nearby_supermarkets', icon: '🛒', label: 'Shops', items: listing.nearby_supermarkets || [] },
        { key: 'nearby_hospitals', icon: '🏥', label: 'Hospitals', items: listing.nearby_hospitals || [] },
        { key: 'nearby_parks', icon: '🌳', label: 'Parks', items: listing.nearby_parks || [] },
    ];

    poisHtml = '<div class="dp-section"><div class="dp-section-title"><i class="fas fa-map-marker-alt"></i> Nearby POIs</div><div class="dp-poi-list">';
    poiCategories.forEach(cat => {
        cat.items.forEach(item => {
            const name = item.name || 'Unknown';
            if (name === 'Unknown') return;
            poisHtml += `
                <div class="dp-poi-item">
                    <span class="dp-poi-icon">${cat.icon}</span>
                    <span class="dp-poi-name">${name}${item.type ? ` (${item.type})` : ''}</span>
                    <span class="dp-poi-dist">${formatDistance(item.distance_m)}</span>
                </div>`;
        });
    });
    poisHtml += '</div></div>';

    // Road classification
    let roadHtml = '';
    if (listing.road_type && listing.road_type !== 'Unknown') {
        const rc = roadClass(listing.road_type);
        roadHtml = `<div class="dp-row"><span class="label"><i class="fas fa-road"></i> Road</span><span class="value"><span class="road-indicator ${rc}">${listing.road_type}</span>${listing.road_name ? ' — ' + listing.road_name : ''}</span></div>`;
    }

    // Flags
    let flagsHtml = '';
    const allFlags = [];
    if (listing.location_flags && Array.isArray(listing.location_flags)) {
        listing.location_flags.forEach(f => allFlags.push({ text: f, cls: 'location-flag' }));
    }
    if (listing.growth_flags && Array.isArray(listing.growth_flags)) {
        listing.growth_flags.forEach(f => allFlags.push({ text: f, cls: 'growth-flag' }));
    }
    if (listing.development_flags && Array.isArray(listing.development_flags)) {
        listing.development_flags.forEach(f => {
            if (!allFlags.find(af => af.text === f)) allFlags.push({ text: f, cls: '' });
        });
    }
    if (allFlags.length > 0) {
        flagsHtml = '<div class="dp-section"><div class="dp-section-title"><i class="fas fa-tags"></i> Flags</div><div class="card-flags">' +
            allFlags.map(f => `<span class="flag-tag ${f.cls}">${f.text}</span>`).join('') +
            '</div></div>';
    }

    // Feasibility data for pre-filling calculator
    const feas = listing.feasibility_json || {};
    const purchasePrice = listing.price_low || listing.price_high || 0;
    const buildCostSqm = feas.build_cost_per_sqm || 2800;
    const numDwellings = feas.dev_type === 'duplex' ? 2 : 1;
    const endValueEach = feas.end_value ? Math.round(feas.end_value / numDwellings) : 0;
    const landSize = listing.land_size_sqm || 0;

    // Build HTML
    body.innerHTML = `
        ${streetViewHtml}

        <!-- Score Header -->
        <div class="dp-score-header">
            <div class="dp-score-big ${badgeClass}" style="background:${color}22;color:${color}">${score.toFixed(0)}</div>
            <div>
                <div style="font-weight:600;font-size:15px">${scoreLabel(score)} Development Potential</div>
                <div class="dp-score-label">${listing.suburb || ''} · ${listing.property_type || ''}</div>
            </div>
        </div>

        <!-- Score Breakdown Chart -->
        ${chartHtml}

        <!-- Property Details -->
        <div class="dp-section">
            <div class="dp-section-title"><i class="fas fa-home"></i> Property</div>
            <div class="dp-row"><span class="label">Price</span><span class="value" style="font-weight:700">${price}</span></div>
            <div class="dp-row"><span class="label">Type</span><span class="value">${listing.property_type || '—'}</span></div>
            <div class="dp-row"><span class="label">Land</span><span class="value">${listing.land_size_sqm ? listing.land_size_sqm.toFixed(0) + ' sqm' : '—'}</span></div>
            ${listing.frontage_m ? `<div class="dp-row"><span class="label">Frontage</span><span class="value">${listing.frontage_m.toFixed(1)}m</span></div>` : ''}
            <div class="dp-row"><span class="label">Beds / Bath / Park</span><span class="value">${listing.bedrooms || '—'} / ${listing.bathrooms || '—'} / ${listing.parking || '—'}</span></div>
            ${listing.zoning ? `<div class="dp-row"><span class="label">Zoning</span><span class="value">${listing.zoning}</span></div>` : ''}
            ${roadHtml}
            <div class="dp-row"><span class="label">Listed</span><span class="value">${listing.listing_date || '—'}</span></div>
            ${listing.agent_name ? `<div class="dp-row"><span class="label">Agent</span><span class="value">${listing.agent_name}</span></div>` : ''}
        </div>

        <!-- Flags -->
        ${flagsHtml}

        <!-- Nearby POIs -->
        ${poisHtml}

        <!-- Feasibility Calculator -->
        <div class="dp-section">
            <div class="dp-section-title"><i class="fas fa-calculator"></i> Feasibility Calculator</div>
            <div class="dp-calc">
                <!-- Scenario Tabs -->
                <div class="dp-calc-tabs">
                    <div class="dp-calc-tab active" data-scenario="development" onclick="switchScenario('development', '${listing.id}')">🏗️ Development</div>
                    <div class="dp-calc-tab" data-scenario="granny" onclick="switchScenario('granny', '${listing.id}')">🏠 Granny Flat</div>
                    <div class="dp-calc-tab" data-scenario="reno" onclick="switchScenario('reno', '${listing.id}')">🔨 Renovation</div>
                </div>

                <!-- Development Scenario -->
                <div id="calc-scenario-development" class="calc-scenario">
                    <div class="dp-calc-grid">
                        <div class="dp-calc-field">
                            <label>Purchase Price ($)</label>
                            <input type="number" id="calc-price" value="${purchasePrice}" oninput="updateDevCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Build Cost ($/sqm)</label>
                            <input type="number" id="calc-build-cost" value="${buildCostSqm}" oninput="updateDevCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label># Dwellings</label>
                            <input type="number" id="calc-dwellings" value="${numDwellings}" min="1" max="10" oninput="updateDevCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Size Each (sqm)</label>
                            <input type="number" id="calc-dwelling-size" value="180" oninput="updateDevCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>End Value/Dwelling ($)</label>
                            <input type="number" id="calc-end-value" value="${endValueEach}" oninput="updateDevCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Holding (months)</label>
                            <input type="number" id="calc-months" value="18" oninput="updateDevCalc()">
                        </div>
                    </div>
                    <div class="dp-calc-result">
                        <div class="result-label">Estimated Profit</div>
                        <div class="result-value" id="calc-dev-profit">—</div>
                        <div class="result-detail" id="calc-dev-detail"></div>
                    </div>
                </div>

                <!-- Granny Flat Scenario -->
                <div id="calc-scenario-granny" class="calc-scenario" style="display:none">
                    <div class="dp-calc-grid">
                        <div class="dp-calc-field">
                            <label>Purchase Price ($)</label>
                            <input type="number" id="calc-gf-price" value="${purchasePrice}" oninput="updateGrannyCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>GF Build Cost ($)</label>
                            <input type="number" id="calc-gf-build" value="150000" oninput="updateGrannyCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Main Rent ($/wk)</label>
                            <input type="number" id="calc-gf-main-rent" value="550" oninput="updateGrannyCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>GF Rent ($/wk)</label>
                            <input type="number" id="calc-gf-rent" value="450" oninput="updateGrannyCalc()">
                        </div>
                    </div>
                    <div class="dp-calc-result">
                        <div class="result-label">Combined Yield</div>
                        <div class="result-value" id="calc-gf-yield">—</div>
                        <div class="result-detail" id="calc-gf-detail"></div>
                    </div>
                    <div class="dp-yield-box" id="calc-gf-breakdown">
                        <div class="dp-yield-row"><span class="label">Total Investment</span><span class="value" id="gf-total-invest">—</span></div>
                        <div class="dp-yield-row"><span class="label">Total Weekly Rent</span><span class="value" id="gf-total-rent">—</span></div>
                        <div class="dp-yield-row"><span class="label">Annual Gross Income</span><span class="value" id="gf-annual">—</span></div>
                        <div class="dp-yield-row"><span class="label">Yield WITHOUT GF</span><span class="value" id="gf-yield-without">—</span></div>
                        <div class="dp-yield-row"><span class="label">Yield WITH GF</span><span class="value" style="color:var(--green)" id="gf-yield-with">—</span></div>
                    </div>
                </div>

                <!-- Renovation Scenario -->
                <div id="calc-scenario-reno" class="calc-scenario" style="display:none">
                    <div class="dp-calc-grid">
                        <div class="dp-calc-field">
                            <label>Purchase Price ($)</label>
                            <input type="number" id="calc-reno-price" value="${purchasePrice}" oninput="updateRenoCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Reno Cost ($)</label>
                            <input type="number" id="calc-reno-cost" value="80000" oninput="updateRenoCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Uplift % of Purchase</label>
                            <input type="number" id="calc-reno-uplift" value="20" min="0" max="100" oninput="updateRenoCalc()">
                        </div>
                        <div class="dp-calc-field">
                            <label>Holding (months)</label>
                            <input type="number" id="calc-reno-months" value="6" oninput="updateRenoCalc()">
                        </div>
                    </div>
                    <div class="dp-calc-result">
                        <div class="result-label">Estimated Profit</div>
                        <div class="result-value" id="calc-reno-profit">—</div>
                        <div class="result-detail" id="calc-reno-detail"></div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Actions -->
        <div class="dp-actions">
            ${listing.url ? `<a class="btn btn-primary" href="${listing.url}" target="_blank"><i class="fas fa-external-link-alt"></i> REA</a>` : ''}
            ${listing.lat && listing.lng ? `<a class="btn btn-outline" href="https://www.google.com/maps/@${listing.lat},${listing.lng},3a,75y,0h,90t/data=!3m6!1e1!3m4!1s!2e0!7i16384!8i8192" target="_blank"><i class="fas fa-street-view"></i> Street View</a>` : ''}
            <a class="btn btn-outline" href="https://www.google.com/maps/search/${encodeURIComponent((listing.address || '') + ' ' + (listing.suburb || '') + ' NSW')}" target="_blank"><i class="fas fa-map"></i> Maps</a>
        </div>
    `;

    // Run calculators
    updateDevCalc();
    updateGrannyCalc();
    updateRenoCalc();
}

// ---- Feasibility Calculators ----
function switchScenario(scenario, listingId) {
    document.querySelectorAll('.dp-calc-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.calc-scenario').forEach(s => s.style.display = 'none');

    document.querySelector(`.dp-calc-tab[data-scenario="${scenario}"]`).classList.add('active');
    document.getElementById(`calc-scenario-${scenario}`).style.display = 'block';
}

function updateDevCalc() {
    const price = parseFloat(document.getElementById('calc-price')?.value) || 0;
    const buildCostSqm = parseFloat(document.getElementById('calc-build-cost')?.value) || 0;
    const dwellings = parseInt(document.getElementById('calc-dwellings')?.value) || 1;
    const dwellingSize = parseFloat(document.getElementById('calc-dwelling-size')?.value) || 180;
    const endValueEach = parseFloat(document.getElementById('calc-end-value')?.value) || 0;
    const months = parseInt(document.getElementById('calc-months')?.value) || 18;

    const stampDuty = price * 0.055;
    const legals = 5000;
    const purchaseTotal = price + stampDuty + legals;

    const buildCost = dwellings * dwellingSize * buildCostSqm;
    const demolition = 40000;
    const daCosts = 35000;
    const infrastructure = 50000;
    const totalBuild = buildCost + demolition + daCosts + infrastructure;

    const totalInvested = purchaseTotal + totalBuild;
    const holdingCost = totalInvested * 0.005 * months;
    const totalCost = purchaseTotal + totalBuild + holdingCost;

    const endValue = endValueEach * dwellings;
    const sellingCosts = endValue * 0.03;
    const netProceeds = endValue - sellingCosts;
    const profit = netProceeds - totalCost;
    const margin = totalCost > 0 ? ((profit / totalCost) * 100).toFixed(1) : 0;

    const profitEl = document.getElementById('calc-dev-profit');
    const detailEl = document.getElementById('calc-dev-detail');

    if (profitEl) {
        const isProfit = profit >= 0;
        profitEl.style.color = isProfit ? 'var(--profit)' : 'var(--loss)';
        profitEl.textContent = `${isProfit ? '+' : ''}${formatCurrency(profit)}`;
        detailEl.style.color = isProfit ? 'var(--profit)' : 'var(--loss)';
        detailEl.textContent = `${margin}% margin · Cost: ${formatCurrency(totalCost)} · Value: ${formatCurrency(endValue)}`;
    }
}

function updateGrannyCalc() {
    const price = parseFloat(document.getElementById('calc-gf-price')?.value) || 0;
    const gfBuild = parseFloat(document.getElementById('calc-gf-build')?.value) || 150000;
    const mainRent = parseFloat(document.getElementById('calc-gf-main-rent')?.value) || 0;
    const gfRent = parseFloat(document.getElementById('calc-gf-rent')?.value) || 0;

    const stampDuty = price * 0.055;
    const totalInvestment = price + stampDuty + gfBuild;
    const totalWeeklyRent = mainRent + gfRent;
    const annualIncome = totalWeeklyRent * 52;
    const grossYield = totalInvestment > 0 ? ((annualIncome / totalInvestment) * 100).toFixed(2) : 0;

    // Yield without GF
    const investWithout = price + stampDuty;
    const annualWithout = mainRent * 52;
    const yieldWithout = investWithout > 0 ? ((annualWithout / investWithout) * 100).toFixed(2) : 0;

    const yieldEl = document.getElementById('calc-gf-yield');
    const detailEl = document.getElementById('calc-gf-detail');

    if (yieldEl) {
        yieldEl.style.color = 'var(--green)';
        yieldEl.textContent = `${grossYield}%`;
        detailEl.textContent = `$${totalWeeklyRent.toLocaleString()}/wk · $${annualIncome.toLocaleString()}/yr`;
    }

    const fields = {
        'gf-total-invest': formatCurrency(totalInvestment),
        'gf-total-rent': `$${totalWeeklyRent}/wk`,
        'gf-annual': formatCurrency(annualIncome),
        'gf-yield-without': `${yieldWithout}%`,
        'gf-yield-with': `${grossYield}%`,
    };

    Object.entries(fields).forEach(([id, val]) => {
        const el = document.getElementById(id);
        if (el) el.textContent = val;
    });
}

function updateRenoCalc() {
    const price = parseFloat(document.getElementById('calc-reno-price')?.value) || 0;
    const renoCost = parseFloat(document.getElementById('calc-reno-cost')?.value) || 0;
    const upliftPct = parseFloat(document.getElementById('calc-reno-uplift')?.value) || 0;
    const months = parseInt(document.getElementById('calc-reno-months')?.value) || 6;

    const stampDuty = price * 0.055;
    const purchaseTotal = price + stampDuty + 5000; // legals
    const totalCost = purchaseTotal + renoCost;

    const holdingCost = totalCost * 0.005 * months;
    const allInCost = totalCost + holdingCost;

    const endValue = price * (1 + upliftPct / 100);
    const sellingCosts = endValue * 0.03;
    const profit = endValue - sellingCosts - allInCost;
    const margin = allInCost > 0 ? ((profit / allInCost) * 100).toFixed(1) : 0;

    const profitEl = document.getElementById('calc-reno-profit');
    const detailEl = document.getElementById('calc-reno-detail');

    if (profitEl) {
        const isProfit = profit >= 0;
        profitEl.style.color = isProfit ? 'var(--profit)' : 'var(--loss)';
        profitEl.textContent = `${isProfit ? '+' : ''}${formatCurrency(profit)}`;
        detailEl.style.color = isProfit ? 'var(--profit)' : 'var(--loss)';
        detailEl.textContent = `${margin}% margin · Cost: ${formatCurrency(allInCost)} · End Value: ${formatCurrency(endValue)}`;
    }
}

// ---- Stats Bar ----
function renderStats(data) {
    stats = data;
    document.getElementById('stat-total').textContent = data.active || 0;
    document.getElementById('stat-avg-score').textContent = data.avg_score || '—';
    document.getElementById('stat-new').textContent = data.new_24h || 0;

    const topSuburb = data.top_suburb;
    document.getElementById('stat-top-suburb').textContent = topSuburb
        ? `${topSuburb.suburb} (${topSuburb.avg_score})`
        : '—';

    document.getElementById('stat-last-scan').textContent = data.last_scan
        ? new Date(data.last_scan + 'Z').toLocaleDateString('en-AU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
        : '—';

    populateFilters(data);
}

// ---- Filters ----
function populateFilters(data) {
    const suburbSelect = document.getElementById('filter-suburb');
    const current = Array.from(suburbSelect.selectedOptions).map(o => o.value);
    suburbSelect.innerHTML = '<option value="">All Suburbs</option>';
    (data.suburbs || []).forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = s;
        if (current.includes(s)) opt.selected = true;
        suburbSelect.appendChild(opt);
    });

    const typeSelect = document.getElementById('filter-type');
    const currentType = typeSelect.value;
    typeSelect.innerHTML = '<option value="">All Types</option>';
    (data.property_types || []).forEach(t => {
        const opt = document.createElement('option');
        opt.value = t;
        opt.textContent = t.charAt(0).toUpperCase() + t.slice(1);
        if (currentType === t) opt.selected = true;
        typeSelect.appendChild(opt);
    });
}

function getFilterParams() {
    const params = new URLSearchParams();

    const suburbSelect = document.getElementById('filter-suburb');
    const selectedSuburbs = Array.from(suburbSelect.selectedOptions).map(o => o.value).filter(v => v);
    if (selectedSuburbs.length) params.set('suburbs', selectedSuburbs.join(','));

    const minPrice = document.getElementById('filter-min-price').value;
    if (minPrice) params.set('min_price', minPrice);

    const maxPrice = document.getElementById('filter-max-price').value;
    if (maxPrice) params.set('max_price', maxPrice);

    const minLand = document.getElementById('filter-min-land').value;
    if (minLand) params.set('min_land', minLand);

    const minScore = document.getElementById('filter-min-score').value;
    if (minScore) params.set('min_score', minScore);

    const propType = document.getElementById('filter-type').value;
    if (propType) params.set('property_type', propType);

    const newOnly = document.getElementById('filter-new-only').checked;
    if (newOnly) params.set('new_only', 'true');

    return params;
}

async function applyFilters() {
    const params = getFilterParams();
    try {
        const resp = await fetch(`/api/listings?${params.toString()}`);
        const data = await resp.json();
        filteredListings = data;
        renderCards();
        updateMapMarkers();
        if (heatmapActive) buildHeatmap();
    } catch (e) {
        console.error('Filter error:', e);
    }
}

function resetFilters() {
    document.getElementById('filter-suburb').selectedIndex = 0;
    document.getElementById('filter-min-price').value = '';
    document.getElementById('filter-max-price').value = '';
    document.getElementById('filter-min-land').value = '';
    document.getElementById('filter-min-score').value = '';
    document.getElementById('filter-type').selectedIndex = 0;
    document.getElementById('filter-new-only').checked = false;
    applyFilters();
}

// POI coordinates are now included directly in the API response (lat/lng per POI)

// ---- Mobile UI ----
function toggleMobileFilters() {
    const filtersBar = document.getElementById('filters-bar');
    filtersBar.classList.toggle('mobile-visible');
}

function toggleMobileCards() {
    const sidebar = document.getElementById('sidebar');
    mobileCardsExpanded = !mobileCardsExpanded;
    sidebar.classList.toggle('mobile-expanded', mobileCardsExpanded);
}

// ---- Init ----
async function init() {
    initMap();

    // Load stats
    try {
        const statsResp = await fetch('/api/stats');
        const statsData = await statsResp.json();
        renderStats(statsData);
    } catch (e) {
        console.error('Stats error:', e);
    }

    // Load listings
    try {
        const listingsResp = await fetch('/api/listings');
        allListings = await listingsResp.json();
        filteredListings = allListings;
        renderCards();
        updateMapMarkers();
    } catch (e) {
        console.error('Listings error:', e);
    }

    // Filter event listeners
    const filterEls = ['filter-suburb', 'filter-min-price', 'filter-max-price',
                        'filter-min-land', 'filter-min-score', 'filter-type', 'filter-new-only'];

    filterEls.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const event = el.type === 'checkbox' ? 'change' : (el.tagName === 'SELECT' ? 'change' : 'input');
        if (el.type === 'number') {
            let timeout;
            el.addEventListener('input', () => {
                clearTimeout(timeout);
                timeout = setTimeout(applyFilters, 500);
            });
        } else {
            el.addEventListener(event, applyFilters);
        }
    });

    // Escape key closes detail panel
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDetailPanel();
    });
}

document.addEventListener('DOMContentLoaded', init);
