/**
 * PropertyFinder v2 — Dashboard App
 * Map + Cards + Filters + Detail Modal + Feasibility Calculator
 */

// ---- State ----
let allListings = [];
let filteredListings = [];
let map = null;
let markersLayer = null;
let detailMap = null;
let detailMarker = null;
let selectedListingId = null;
let stats = {};

// ---- Score Helpers ----
function scoreClass(score) {
    if (score >= 70) return 'hot';
    if (score >= 50) return 'good';
    if (score >= 30) return 'below';
    return 'poor';
}

function scoreBadgeClass(score) {
    return 'score-' + scoreClass(score);
}

function scoreColor(score) {
    if (score >= 70) return '#3fb950';
    if (score >= 50) return '#d29922';
    if (score >= 30) return '#db6d28';
    return '#f85149';
}

function scoreLabel(score) {
    if (score >= 70) return 'Hot';
    if (score >= 50) return 'Good';
    if (score >= 30) return 'Below Avg';
    return 'Poor';
}

// ---- Format Helpers ----
function formatPrice(display, low, high) {
    if (display && display !== 'Contact Agent' && display !== '') return display;
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

        popupHtml += `<br><a class="popup-link" href="#" onclick="openDetail('${listing.id}'); return false;">Full Details →</a>`;

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
}

// ---- Cards ----
function renderCards() {
    const container = document.getElementById('cards-container');
    const countEl = document.getElementById('listing-count');

    countEl.textContent = `${filteredListings.length} listing${filteredListings.length !== 1 ? 's' : ''} found`;

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

        // Development flags
        let flagsHtml = '';
        if (listing.development_flags && Array.isArray(listing.development_flags)) {
            flagsHtml = listing.development_flags.map(f =>
                `<span class="flag-tag">${f}</span>`
            ).join('');
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
            <div class="listing-card" data-id="${listing.id}" onclick="openDetail('${listing.id}')">
                ${newBadge}
                <div class="card-header">
                    <div class="card-address">
                        ${listing.address || 'Unknown Address'}
                        <div class="card-suburb">${listing.suburb || ''}${listing.postcode ? ' ' + listing.postcode : ''}</div>
                    </div>
                    <div class="score-badge ${badgeClass}">${score.toFixed(0)}</div>
                </div>
                <div class="card-meta">
                    <span class="card-price">${price}</span>
                    ${listing.land_size_sqm ? `<span><span class="icon">📐</span>${listing.land_size_sqm.toFixed(0)} sqm</span>` : ''}
                    ${listing.bedrooms ? `<span><span class="icon">🛏</span>${listing.bedrooms}</span>` : ''}
                    ${listing.bathrooms ? `<span><span class="icon">🚿</span>${listing.bathrooms}</span>` : ''}
                    ${listing.parking ? `<span><span class="icon">🚗</span>${listing.parking}</span>` : ''}
                </div>
                ${flagsHtml ? `<div class="card-flags">${flagsHtml}</div>` : ''}
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

// ---- Detail Modal ----
async function openDetail(id) {
    selectedListingId = id;
    const overlay = document.getElementById('modal-overlay');
    const body = document.getElementById('modal-body');

    overlay.classList.add('active');
    body.innerHTML = '<div class="loading-spinner">Loading...</div>';

    try {
        const resp = await fetch(`/api/listings/${encodeURIComponent(id)}`);
        if (!resp.ok) throw new Error('Not found');
        const listing = await resp.json();
        renderDetail(listing);
    } catch (e) {
        body.innerHTML = `<div class="empty-state"><h3>Error loading listing</h3><p>${e.message}</p></div>`;
    }
}

function renderDetail(listing) {
    const body = document.getElementById('modal-body');
    const header = document.getElementById('modal-title');

    header.textContent = listing.address || 'Unknown Address';

    const score = listing.development_score || 0;
    const price = formatPrice(listing.price_display, listing.price_low, listing.price_high);
    const badgeClass = scoreBadgeClass(score);

    // Flags
    let flagsHtml = '';
    if (listing.development_flags && Array.isArray(listing.development_flags)) {
        flagsHtml = listing.development_flags.map(f => `<span class="flag-tag">${f}</span>`).join('');
    }

    // Score breakdown
    let breakdownHtml = '';
    if (listing.score_breakdown && typeof listing.score_breakdown === 'object') {
        const sb = listing.score_breakdown;
        breakdownHtml = Object.entries(sb).map(([k, v]) => `
            <div class="detail-row">
                <span class="label">${k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                <span class="value">${v}</span>
            </div>`).join('');
    }

    // Feasibility data (for pre-filling calculator)
    const feas = listing.feasibility_json || {};
    const purchasePrice = listing.price_low || listing.price_high || 0;
    const buildCostSqm = feas.build_cost_per_sqm || 2800;
    const numDwellings = feas.dev_type === 'duplex' ? 2 : 1;
    const endValueEach = feas.end_value ? Math.round(feas.end_value / numDwellings) : 0;

    body.innerHTML = `
        <!-- Detail Map -->
        ${listing.lat && listing.lng ? '<div class="detail-map-container"><div id="detail-map"></div></div>' : ''}

        <div class="detail-grid">
            <!-- Property Details -->
            <div class="detail-section">
                <h3>Property Details</h3>
                <div class="detail-row"><span class="label">Price</span><span class="value">${price}</span></div>
                <div class="detail-row"><span class="label">Type</span><span class="value">${listing.property_type || '—'}</span></div>
                <div class="detail-row"><span class="label">Land Size</span><span class="value">${listing.land_size_sqm ? listing.land_size_sqm.toFixed(0) + ' sqm' : '—'}</span></div>
                ${listing.frontage_m ? `<div class="detail-row"><span class="label">Frontage</span><span class="value">${listing.frontage_m.toFixed(1)}m</span></div>` : ''}
                <div class="detail-row"><span class="label">Beds</span><span class="value">${listing.bedrooms || '—'}</span></div>
                <div class="detail-row"><span class="label">Baths</span><span class="value">${listing.bathrooms || '—'}</span></div>
                <div class="detail-row"><span class="label">Parking</span><span class="value">${listing.parking || '—'}</span></div>
                ${listing.year_built ? `<div class="detail-row"><span class="label">Year Built</span><span class="value">${listing.year_built}</span></div>` : ''}
                ${listing.zoning ? `<div class="detail-row"><span class="label">Zoning</span><span class="value">${listing.zoning}</span></div>` : ''}
                <div class="detail-row"><span class="label">Suburb</span><span class="value">${listing.suburb || '—'}, ${listing.state || ''}</span></div>
                ${listing.agent_name ? `<div class="detail-row"><span class="label">Agent</span><span class="value">${listing.agent_name}</span></div>` : ''}
                ${listing.agency ? `<div class="detail-row"><span class="label">Agency</span><span class="value">${listing.agency}</span></div>` : ''}
                <div class="detail-row"><span class="label">Listed</span><span class="value">${listing.listing_date || '—'}</span></div>
                <div class="detail-row"><span class="label">First Seen</span><span class="value">${listing.first_seen || '—'}</span></div>
            </div>

            <!-- Score Breakdown -->
            <div class="detail-section">
                <h3>Development Score: <span class="score-badge ${badgeClass}" style="font-size:16px;padding:4px 12px;">${score.toFixed(1)}</span></h3>
                ${breakdownHtml}
                ${flagsHtml ? `<div style="margin-top:12px;">${flagsHtml}</div>` : ''}
            </div>
        </div>

        <!-- Existing Feasibility -->
        ${feas.total_cost ? `
        <div class="detail-section" style="margin-bottom:16px;">
            <h3>Auto Feasibility (${(feas.dev_type || '').replace(/_/g, ' ')})</h3>
            <div class="detail-row"><span class="label">Purchase Total</span><span class="value">${formatCurrency(feas.purchase_total)}</span></div>
            <div class="detail-row"><span class="label">Build Cost</span><span class="value">${formatCurrency(feas.total_build)}</span></div>
            <div class="detail-row"><span class="label">Holding Cost (${feas.holding_months}mo)</span><span class="value">${formatCurrency(feas.holding_cost)}</span></div>
            <div class="detail-row"><span class="label">Total Cost</span><span class="value" style="font-weight:700">${formatCurrency(feas.total_cost)}</span></div>
            <div class="detail-row"><span class="label">End Value</span><span class="value">${formatCurrency(feas.end_value)}</span></div>
            <div class="detail-row"><span class="label">Selling Costs</span><span class="value">${formatCurrency(feas.selling_costs)}</span></div>
            <div class="detail-row">
                <span class="label" style="font-weight:700">Estimated Profit</span>
                <span class="value ${feas.profit >= 0 ? 'profit' : 'loss'}" style="font-weight:700">
                    ${feas.profit >= 0 ? '+' : ''}${formatCurrency(feas.profit)} (${feas.profit_margin_pct}%)
                </span>
            </div>
        </div>` : ''}

        <!-- Feasibility Calculator -->
        <div class="calc-section">
            <h3>📊 Feasibility Calculator</h3>
            <div class="calc-grid">
                <div class="calc-field">
                    <label>Purchase Price ($)</label>
                    <input type="number" id="calc-price" value="${purchasePrice}" oninput="updateCalc()">
                </div>
                <div class="calc-field">
                    <label>Build Cost ($/sqm)</label>
                    <input type="number" id="calc-build-cost" value="${buildCostSqm}" oninput="updateCalc()">
                </div>
                <div class="calc-field">
                    <label>Number of Dwellings</label>
                    <input type="number" id="calc-dwellings" value="${numDwellings}" min="1" max="10" oninput="updateCalc()">
                </div>
                <div class="calc-field">
                    <label>Dwelling Size (sqm each)</label>
                    <input type="number" id="calc-dwelling-size" value="180" oninput="updateCalc()">
                </div>
                <div class="calc-field">
                    <label>End Value per Dwelling ($)</label>
                    <input type="number" id="calc-end-value" value="${endValueEach}" oninput="updateCalc()">
                </div>
                <div class="calc-field">
                    <label>Holding Period (months)</label>
                    <input type="number" id="calc-months" value="18" oninput="updateCalc()">
                </div>
            </div>
            <div class="calc-result" id="calc-result">
                <div class="result-label">Estimated Profit</div>
                <div class="result-value" id="calc-profit-value">—</div>
                <div class="result-margin" id="calc-margin-value"></div>
            </div>
        </div>

        <!-- Actions -->
        <div class="detail-actions">
            ${listing.url ? `<a class="btn btn-primary" href="${listing.url}" target="_blank">🔗 View on REA</a>` : ''}
            ${listing.lat && listing.lng ? `<a class="btn btn-outline" href="https://www.google.com/maps/@${listing.lat},${listing.lng},3a,75y,0h,90t/data=!3m6!1e1!3m4!1s!2e0!7i16384!8i8192" target="_blank">🗺️ Street View</a>` : ''}
            <a class="btn btn-outline" href="https://www.google.com/maps/search/${encodeURIComponent((listing.address || '') + ' ' + (listing.suburb || '') + ' NSW')}" target="_blank">📍 Google Maps</a>
        </div>
    `;

    // Init detail map
    if (listing.lat && listing.lng) {
        setTimeout(() => {
            if (detailMap) {
                detailMap.remove();
            }
            detailMap = L.map('detail-map', {
                center: [listing.lat, listing.lng],
                zoom: 16,
                zoomControl: false,
            });
            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
                maxZoom: 19,
            }).addTo(detailMap);
            detailMarker = L.marker([listing.lat, listing.lng], {
                icon: createMarkerIcon(score),
            }).addTo(detailMap);
        }, 100);
    }

    // Run calc
    updateCalc();
}

function updateCalc() {
    const price = parseFloat(document.getElementById('calc-price')?.value) || 0;
    const buildCostSqm = parseFloat(document.getElementById('calc-build-cost')?.value) || 0;
    const dwellings = parseInt(document.getElementById('calc-dwellings')?.value) || 1;
    const dwellingSize = parseFloat(document.getElementById('calc-dwelling-size')?.value) || 180;
    const endValueEach = parseFloat(document.getElementById('calc-end-value')?.value) || 0;
    const months = parseInt(document.getElementById('calc-months')?.value) || 18;

    // Costs
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

    // Revenue
    const endValue = endValueEach * dwellings;
    const sellingCosts = endValue * 0.03;
    const netProceeds = endValue - sellingCosts;

    // Profit
    const profit = netProceeds - totalCost;
    const margin = totalCost > 0 ? ((profit / totalCost) * 100).toFixed(1) : 0;

    const profitEl = document.getElementById('calc-profit-value');
    const marginEl = document.getElementById('calc-margin-value');

    if (profitEl) {
        const isProfit = profit >= 0;
        profitEl.style.color = isProfit ? 'var(--profit)' : 'var(--loss)';
        profitEl.textContent = `${isProfit ? '+' : ''}${formatCurrency(profit)}`;
        marginEl.style.color = isProfit ? 'var(--profit)' : 'var(--loss)';
        marginEl.textContent = `Margin: ${margin}% | Total Cost: ${formatCurrency(totalCost)} | End Value: ${formatCurrency(endValue)}`;
    }
}

function closeDetail() {
    document.getElementById('modal-overlay').classList.remove('active');
    if (detailMap) {
        detailMap.remove();
        detailMap = null;
    }
    selectedListingId = null;
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

    // Populate filter dropdowns
    populateFilters(data);
}

// ---- Filters ----
function populateFilters(data) {
    const suburbSelect = document.getElementById('filter-suburb');
    // Save current selections
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
        filteredListings = await resp.json();
        renderCards();
        updateMapMarkers();
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
        // Debounce numeric inputs
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

    // Modal close
    document.getElementById('modal-overlay').addEventListener('click', (e) => {
        if (e.target === e.currentTarget) closeDetail();
    });

    // Escape key closes modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDetail();
    });
}

document.addEventListener('DOMContentLoaded', init);
