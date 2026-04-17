/* =================================================================
   Nordic Bench Map – App Logic
   =================================================================
   Three view modes:
     Points    – individual bench markers, colour by city
     Heatmap   – leaflet.heat density layer
     Districts – choropleth by bench density per district
   ================================================================= */

'use strict';

// ── City metadata ────────────────────────────────────────────────────
const CITIES = {
  helsinki:   { label: 'Helsinki',   color: '#2563eb', country: 'Finland'  },
  tallinn:    { label: 'Tallinn',    color: '#16a34a', country: 'Estonia'  },
  copenhagen: { label: 'Copenhagen', color: '#dc2626', country: 'Denmark'  },
  oslo:       { label: 'Oslo',       color: '#9333ea', country: 'Norway'   },
};

const BBOXES = {
  helsinki:   [[60.10, 24.82], [60.35, 25.25]],
  tallinn:    [[59.35, 24.55], [59.52, 24.95]],
  copenhagen: [[55.60, 12.45], [55.75, 12.65]],
  oslo:       [[59.82, 10.65], [59.98, 10.88]],
};

// ── State ────────────────────────────────────────────────────────────
let activeCity = 'all';
let activeView = 'points';   // 'points' | 'heatmap' | 'districts'
let summary    = {};
let allFeatures = [];        // flat array of all bench GeoJSON features

// Layer groups for Points view
const pointLayers = {};     // city key → L.layerGroup

// Heatmap layer (single, rebuilt on city switch)
let heatLayer = null;

// District choropleth layers
const districtLayers = {};  // city key → L.geoJSON layer
let districtData = {};       // city key → GeoJSON FeatureCollection
let densityChart  = null;

// ── Map init ─────────────────────────────────────────────────────────
const map = L.map('map', { zoomControl: true }).setView([59.0, 20.0], 5);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
  subdomains: 'abcd',
  maxZoom: 19,
}).addTo(map);

// ── Choropleth colour scale ──────────────────────────────────────────
function densityColor(density, max) {
  // White → city colour gradient
  const t = Math.min(density / max, 1);
  // Use a perceptual scale
  const stops = [
    [1.0, 1.0, 1.0],        // white
    [0.95, 0.87, 0.55],     // light yellow
    [0.98, 0.60, 0.20],     // orange
    [0.84, 0.19, 0.15],     // red
    [0.40, 0.02, 0.35],     // dark purple
  ];
  const n   = stops.length - 1;
  const idx = Math.min(Math.floor(t * n), n - 1);
  const frac = t * n - idx;
  const a = stops[idx], b = stops[idx + 1];
  const r = Math.round((a[0] + (b[0] - a[0]) * frac) * 255);
  const g = Math.round((a[1] + (b[1] - a[1]) * frac) * 255);
  const bl = Math.round((a[2] + (b[2] - a[2]) * frac) * 255);
  return `rgb(${r},${g},${bl})`;
}

// ── Points view helpers ──────────────────────────────────────────────
function markerOptions(feature) {
  const city  = feature.properties?.city || 'unknown';
  const color = CITIES[city]?.color || '#888';
  return L.circleMarker(
    [feature.geometry.coordinates[1], feature.geometry.coordinates[0]],
    { radius: 3.5, fillColor: color, color: color, weight: 0, opacity: 0.9, fillOpacity: 0.65 }
  );
}

function popupContent(props) {
  const city  = CITIES[props.city]?.label || props.city || '–';
  const type  = props.bench_type  || props.mun_bench_type || '–';
  const mat   = props.material    || props.mun_material   || '–';
  const loc   = props.location_name || props.mun_location_name || '–';
  const br    = props.backrest    || props.osm_backrest   || '–';
  const seats = props.seats       || props.osm_seats      || '–';
  const src   = props.source      || '–';
  return `
    <div class="popup-city">${city}</div>
    <table class="popup-table">
      <tr><td>Type</td><td>${type}</td></tr>
      <tr><td>Material</td><td>${mat}</td></tr>
      <tr><td>Location</td><td>${loc}</td></tr>
      <tr><td>Backrest</td><td>${br}</td></tr>
      <tr><td>Seats</td><td>${seats}</td></tr>
      <tr><td>Source</td><td>${src}</td></tr>
    </table>`;
}

function showBenchInfo(props) {
  const rows = [
    ['City',     CITIES[props.city]?.label || props.city],
    ['Type',     props.bench_type  || props.mun_bench_type],
    ['Material', props.material    || props.mun_material],
    ['Location', props.location_name || props.mun_location_name],
    ['Backrest', props.backrest    || props.osm_backrest],
    ['Seats',    props.seats       || props.osm_seats],
    ['Source',   props.source],
  ].filter(([, v]) => v != null && v !== '');
  document.getElementById('info-content').innerHTML =
    rows.map(([k, v]) => `<div><strong>${k}:</strong> ${v}</div>`).join('');
}

// ── Data loading ─────────────────────────────────────────────────────
async function loadCity(cityKey) {
  const r = await fetch(`data/${cityKey}_benches.geojson`);
  if (!r.ok) throw new Error(`${cityKey} benches: HTTP ${r.status}`);
  return r.json();
}

async function loadDistricts(cityKey) {
  const r = await fetch(`data/${cityKey}_districts.geojson`);
  if (!r.ok) throw new Error(`${cityKey} districts: HTTP ${r.status}`);
  return r.json();
}

async function loadAll() {
  // Summary stats
  try {
    const r = await fetch('data/summary.json');
    if (r.ok) summary = await r.json();
  } catch (_) {}

  // Bench points + district data in parallel
  const cityKeys = Object.keys(CITIES);

  const [benchResults, districtResults] = await Promise.all([
    Promise.allSettled(cityKeys.map(k => loadCity(k))),
    Promise.allSettled(cityKeys.map(k => loadDistricts(k))),
  ]);

  benchResults.forEach((result, i) => {
    const key = cityKeys[i];
    if (result.status === 'rejected') {
      console.warn(`Bench load failed (${key}):`, result.reason.message);
      return;
    }
    const geojson = result.value;
    const group   = L.layerGroup();

    L.geoJSON(geojson, {
      pointToLayer: (feat) => {
        const m = markerOptions(feat);
        m.on('click', () => showBenchInfo(feat.properties));
        m.bindPopup(popupContent(feat.properties), { maxWidth: 240 });
        return m;
      },
    }).addTo(group);

    pointLayers[key] = group;
    allFeatures.push(...(geojson.features || []));
  });

  districtResults.forEach((result, i) => {
    const key = cityKeys[i];
    if (result.status === 'rejected') {
      console.warn(`District load failed (${key}):`, result.reason.message);
      return;
    }
    districtData[key] = result.value;
  });

  // Default: show all point layers
  Object.values(pointLayers).forEach(g => g.addTo(map));

  renderSidebar();
  renderChart();
}

// ── View switching ────────────────────────────────────────────────────
function setView(view) {
  activeView = view;

  // Update toggle buttons
  document.querySelectorAll('.view-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.view === view);
  });

  // Show/hide district detail panel
  document.getElementById('section-district').style.display =
    view === 'districts' ? '' : 'none';

  // Show/hide choropleth legend
  const legend = document.getElementById('district-legend');
  if (legend) legend.classList.toggle('visible', view === 'districts');

  applyLayers();
}

function setActiveCity(city) {
  activeCity = city;

  document.querySelectorAll('.city-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.city === city);
  });
  document.querySelectorAll('.city-card').forEach(card => {
    card.classList.toggle('active', card.dataset.city === city || city === 'all');
  });

  // Fly to bbox
  if (city !== 'all' && BBOXES[city]) {
    map.flyToBounds(BBOXES[city], { padding: [30, 30], duration: 0.8 });
  } else {
    map.flyTo([59.0, 20.0], 5, { duration: 0.8 });
  }

  applyLayers();
}

function applyLayers() {
  const view = activeView;
  const city = activeCity;

  // 1. Remove all managed layers
  Object.values(pointLayers).forEach(g => { if (map.hasLayer(g)) map.removeLayer(g); });
  if (heatLayer && map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
  Object.values(districtLayers).forEach(g => { if (map.hasLayer(g)) map.removeLayer(g); });

  // 2. Determine active city keys
  const keys = city === 'all' ? Object.keys(CITIES) : [city];

  if (view === 'points') {
    keys.forEach(k => { if (pointLayers[k]) pointLayers[k].addTo(map); });

  } else if (view === 'heatmap') {
    const pts = allFeatures
      .filter(f => city === 'all' || f.properties?.city === city)
      .map(f => {
        const [lon, lat] = f.geometry.coordinates;
        return [lat, lon, 1];
      });
    if (heatLayer) heatLayer.remove();
    heatLayer = L.heatLayer(pts, {
      radius: 18,
      blur:   20,
      maxZoom: 17,
      gradient: { 0.0: '#f0f9ff', 0.3: '#38bdf8', 0.6: '#f59e0b', 0.85: '#ef4444', 1.0: '#7c3aed' },
    }).addTo(map);

  } else if (view === 'districts') {
    keys.forEach(k => {
      if (!districtData[k]) return;
      if (!districtLayers[k]) {
        buildDistrictLayer(k);
      }
      if (districtLayers[k]) districtLayers[k].addTo(map);
    });
    updateLegend();
  }
}

// ── District choropleth ───────────────────────────────────────────────
function buildDistrictLayer(cityKey) {
  const data = districtData[cityKey];
  if (!data) return;

  const densities = data.features
    .map(f => f.properties.bench_density || 0)
    .filter(d => d > 0);
  const maxDensity = densities.length ? Math.max(...densities) : 1;

  const layer = L.geoJSON(data, {
    style: (feat) => {
      const d = feat.properties.bench_density || 0;
      return {
        fillColor:   densityColor(d, maxDensity),
        fillOpacity: 0.75,
        color:       '#fff',
        weight:      1,
        opacity:     0.8,
      };
    },
    onEachFeature: (feat, lyr) => {
      lyr.on('click', () => showDistrictInfo(feat.properties));
      lyr.on('mouseover', function() {
        this.setStyle({ weight: 2, color: '#333' });
      });
      lyr.on('mouseout', function() {
        layer.resetStyle(this);
      });
    },
  });

  districtLayers[cityKey] = layer;
}

function showDistrictInfo(props) {
  const city    = CITIES[props.city]?.label || props.city || '–';
  const name    = props.name || '–';
  const count   = props.bench_count ?? '–';
  const density = props.bench_density != null ? props.bench_density.toFixed(1) : '–';
  const area    = props.area_km2 != null ? props.area_km2.toFixed(1) : '–';
  const pop     = props.population != null ? props.population.toLocaleString() : '–';
  const popDens = props.pop_density != null ? props.pop_density.toFixed(0) : '–';

  const hasPopData = props.population != null;
  let benchPerPop = '–';
  if (props.population && props.bench_count) {
    benchPerPop = (props.bench_count / props.population * 1000).toFixed(1);
  }

  document.getElementById('district-content').innerHTML = `
    <div class="district-name">${name} <span style="color:var(--muted);font-weight:400;font-size:0.75rem">(${city})</span></div>
    <div class="stat-row"><span>Benches</span><span>${count.toLocaleString()}</span></div>
    <div class="stat-row"><span>Bench density (per km²)</span><span>${density}</span></div>
    <div class="stat-row"><span>Area</span><span>${area} km²</span></div>
    ${hasPopData ? `
    <div class="stat-row"><span>Population</span><span>${pop}</span></div>
    <div class="stat-row"><span>Pop. density (per km²)</span><span>${popDens}</span></div>
    <div class="stat-row"><span>Benches per 1,000 people</span><span>${benchPerPop}</span></div>` : ''}
  `;
}

function updateLegend() {
  let legend = document.getElementById('district-legend');
  if (!legend) {
    legend = document.createElement('div');
    legend.id = 'district-legend';
    document.getElementById('map').appendChild(legend);
  }
  legend.className = 'visible';

  const steps = 5;
  const labels = ['Low', '', 'Mid', '', 'High'];
  const rows = Array.from({ length: steps }, (_, i) => {
    const t = i / (steps - 1);
    const color = densityColor(t, 1);
    return `<div class="legend-row">
      <div class="legend-swatch" style="background:${color}"></div>
      <span>${labels[i]}</span>
    </div>`;
  }).join('');

  legend.innerHTML = `<div class="legend-title">Bench density</div>${rows}`;
}

// ── Sidebar ───────────────────────────────────────────────────────────
function renderSidebar() {
  const container = document.getElementById('city-cards');
  container.innerHTML = '';

  Object.entries(CITIES).forEach(([key, meta]) => {
    const s     = summary[key] || {};
    const total = s.total ?? '–';
    const dens  = s.density_per_km2 != null ? s.density_per_km2.toFixed(1) : '–';
    const munPct = (total > 0)
      ? Math.round(100 * ((s.municipal_only || 0) + (s.municipal_osm || 0)) / total) : 0;

    const card = document.createElement('div');
    card.className = 'city-card active';
    card.dataset.city = key;
    card.innerHTML = `
      <div class="city-card-header">
        <span class="city-dot"></span>
        <span class="city-card-name">${meta.label}</span>
        <span class="city-card-total">${(total).toLocaleString()}</span>
      </div>
      <div class="stat-row"><span>Density (benches/km²)</span><span>${dens}</span></div>
      <div class="stat-row"><span>Municipal data</span><span>${munPct}%</span></div>
      <div class="stat-row"><span>Area</span><span>${s.area_km2 ?? '–'} km²</span></div>`;

    card.addEventListener('click', () => setActiveCity(activeCity === key ? 'all' : key));
    container.appendChild(card);
  });
}

// ── Chart.js density bar ──────────────────────────────────────────────
function renderChart() {
  const ctx      = document.getElementById('density-chart').getContext('2d');
  const cityKeys = Object.keys(CITIES);
  const labels   = cityKeys.map(k => CITIES[k].label);
  const densities = cityKeys.map(k => summary[k]?.density_per_km2 ?? 0);
  const colors    = cityKeys.map(k => CITIES[k].color);

  if (densityChart) densityChart.destroy();
  densityChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Benches / km²',
        data:  densities,
        backgroundColor: colors.map(c => c + 'bb'),
        borderColor:     colors,
        borderWidth:     1.5,
        borderRadius:    4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y.toFixed(1)} benches/km²` } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: '#eee' } },
        x: { ticks: { font: { size: 11 } }, grid: { display: false } },
      },
    },
  });
}

// ── Tab + button wiring ───────────────────────────────────────────────
document.querySelectorAll('.city-tab').forEach(tab => {
  tab.addEventListener('click', () => setActiveCity(tab.dataset.city));
});

document.querySelectorAll('.view-btn').forEach(btn => {
  btn.addEventListener('click', () => setView(btn.dataset.view));
});

// ── Boot ──────────────────────────────────────────────────────────────
loadAll().catch(err => console.error('Failed to load data:', err));
