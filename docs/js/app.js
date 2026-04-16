/* =================================================================
   Nordic Bench Map – App Logic
   =================================================================
   Loads per-city GeoJSON from data/ and renders:
     - Leaflet map with bench markers (colour-coded by city)
     - Sidebar stats panel with counts and Chart.js bar chart
     - City tab / card filtering
   ================================================================= */

'use strict';

// ── City metadata ────────────────────────────────────────────────
const CITIES = {
  helsinki:   { label: 'Helsinki',   color: '#2563eb', country: 'Finland' },
  stockholm:  { label: 'Stockholm',  color: '#16a34a', country: 'Sweden'  },
  copenhagen: { label: 'Copenhagen', color: '#dc2626', country: 'Denmark' },
  oslo:       { label: 'Oslo',       color: '#9333ea', country: 'Norway'  },
};

const SOURCE_COLORS = {
  'municipal':     '#f59e0b',
  'osm':           '#06b6d4',
  'municipal+osm': '#8b5cf6',
};

// ── State ────────────────────────────────────────────────────────
let activeCity   = 'all';    // 'all' | city key
let summary      = {};       // loaded from data/summary.json
let layers       = {};       // city key → Leaflet LayerGroup
let allLayers    = null;     // combined LayerGroup for 'all' view
let densityChart = null;

// ── Map init ─────────────────────────────────────────────────────
const map = L.map('map', { zoomControl: true }).setView([58.5, 15.5], 5);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://openstreetmap.org">OpenStreetMap</a>',
  subdomains:  'abcd',
  maxZoom:     19,
}).addTo(map);

// ── Helpers ──────────────────────────────────────────────────────
function markerOptions(feature) {
  const city   = feature.properties?.city   || 'unknown';
  const source = feature.properties?.source || 'osm';
  const color  = CITIES[city]?.color || '#888';

  // Source indicated by border colour
  const borderColor = SOURCE_COLORS[source] || '#888';

  return L.circleMarker(
    [feature.geometry.coordinates[1], feature.geometry.coordinates[0]],
    {
      radius:      4,
      fillColor:   color,
      color:       borderColor,
      weight:      1.5,
      opacity:     0.9,
      fillOpacity: 0.75,
    }
  );
}

function popupContent(props) {
  const city   = CITIES[props.city]?.label || props.city || '–';
  const src    = props.source      || '–';
  const type   = props.bench_type  || props.mun_bench_type || '–';
  const mat    = props.material    || props.mun_material   || '–';
  const loc    = props.location_name || props.mun_location_name || '–';
  const br     = props.backrest    || props.osm_backrest   || '–';
  const seats  = props.seats       || props.osm_seats      || '–';

  return `
    <div class="popup-city">${city}</div>
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="color:#6b7280;padding-right:8px">Source</td><td>${src}</td></tr>
      <tr><td style="color:#6b7280">Type</td><td>${type}</td></tr>
      <tr><td style="color:#6b7280">Material</td><td>${mat}</td></tr>
      <tr><td style="color:#6b7280">Location</td><td>${loc}</td></tr>
      <tr><td style="color:#6b7280">Backrest</td><td>${br}</td></tr>
      <tr><td style="color:#6b7280">Seats</td><td>${seats}</td></tr>
    </table>`;
}

// ── Data loading ─────────────────────────────────────────────────
async function loadCity(cityKey) {
  const resp = await fetch(`data/${cityKey}_benches.geojson`);
  if (!resp.ok) throw new Error(`${cityKey}: HTTP ${resp.status}`);
  return resp.json();
}

async function loadAll() {
  // Load summary stats first
  try {
    const r = await fetch('data/summary.json');
    if (r.ok) summary = await r.json();
  } catch (_) { /* summary optional */ }

  const results = await Promise.allSettled(
    Object.keys(CITIES).map(key => loadCity(key))
  );

  const combined = [];

  results.forEach((result, i) => {
    const cityKey = Object.keys(CITIES)[i];
    if (result.status === 'rejected') {
      console.warn(`Failed to load ${cityKey}:`, result.reason.message);
      return;
    }
    const geojson = result.value;
    const group   = L.layerGroup();

    L.geoJSON(geojson, {
      pointToLayer: (feature) => {
        const marker = markerOptions(feature);
        marker.on('click', () => showInfo(feature.properties));
        marker.bindPopup(popupContent(feature.properties), { maxWidth: 260 });
        return marker;
      },
    }).addTo(group);

    layers[cityKey] = group;
    combined.push(...(geojson.features || []));
  });

  allLayers = L.layerGroup(Object.values(layers));
  allLayers.addTo(map);

  renderSidebar();
  renderChart();
}

// ── View switching ────────────────────────────────────────────────
function setActiveCity(city) {
  activeCity = city;

  // Update tabs
  document.querySelectorAll('.city-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.city === city);
  });

  // Update cards
  document.querySelectorAll('.city-card').forEach(card => {
    card.classList.toggle('active', card.dataset.city === city || city === 'all');
  });

  // Update map layers
  Object.entries(layers).forEach(([key, layer]) => {
    if (city === 'all' || city === key) {
      if (!map.hasLayer(layer)) layer.addTo(map);
    } else {
      if (map.hasLayer(layer)) map.removeLayer(layer);
    }
  });

  // Fly to city bounding box if single city selected
  const BBOXES = {
    helsinki:   [[60.10, 24.82], [60.35, 25.25]],
    stockholm:  [[59.20, 17.80], [59.45, 18.20]],
    copenhagen: [[55.60, 12.45], [55.75, 12.65]],
    oslo:       [[59.82, 10.65], [59.98, 10.88]],
  };
  if (city !== 'all' && BBOXES[city]) {
    map.flyToBounds(BBOXES[city], { padding: [30, 30], duration: 0.8 });
  } else {
    map.flyTo([58.5, 15.5], 5, { duration: 0.8 });
  }
}

// ── Sidebar rendering ─────────────────────────────────────────────
function renderSidebar() {
  const container = document.getElementById('city-cards');
  container.innerHTML = '';

  Object.entries(CITIES).forEach(([key, meta]) => {
    const s = summary[key] || {};
    const total = s.total ?? '–';
    const dens  = s.density_per_km2 != null ? s.density_per_km2.toFixed(1) : '–';
    const munPct = total > 0
      ? Math.round(100 * ((s.municipal_only || 0) + (s.municipal_osm || 0)) / total)
      : 0;
    const osmPct    = total > 0 ? Math.round(100 * (s.osm_only || 0) / total) : 0;
    const mergedPct = total > 0 ? Math.round(100 * (s.municipal_osm || 0) / total) : 0;

    const card = document.createElement('div');
    card.className = 'city-card active';
    card.dataset.city = key;
    card.innerHTML = `
      <div class="city-card-header">
        <span class="city-dot"></span>
        <span class="city-card-name">${meta.label}</span>
        <span class="city-card-total">${total.toLocaleString()}</span>
      </div>
      <div class="stat-row"><span>Density (benches/km²)</span><span>${dens}</span></div>
      <div class="stat-row"><span>Municipal only</span><span>${(s.municipal_only ?? 0).toLocaleString()}</span></div>
      <div class="stat-row"><span>OSM only</span><span>${(s.osm_only ?? 0).toLocaleString()}</span></div>
      <div class="stat-row"><span>In both sources</span><span>${(s.municipal_osm ?? 0).toLocaleString()}</span></div>
      <div class="source-bar" title="Yellow=municipal, Cyan=OSM only, Purple=both">
        <div class="source-bar-seg" style="width:${munPct}%;background:${SOURCE_COLORS['municipal']}"></div>
        <div class="source-bar-seg" style="width:${osmPct}%;background:${SOURCE_COLORS['osm']}"></div>
        <div class="source-bar-seg" style="width:${mergedPct}%;background:${SOURCE_COLORS['municipal+osm']}"></div>
      </div>`;

    card.addEventListener('click', () => setActiveCity(activeCity === key ? 'all' : key));
    container.appendChild(card);
  });
}

// ── Chart.js density comparison ───────────────────────────────────
function renderChart() {
  const ctx = document.getElementById('density-chart').getContext('2d');
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
        backgroundColor: colors.map(c => c + 'cc'),
        borderColor:     colors,
        borderWidth:     1.5,
        borderRadius:    4,
      }],
    },
    options: {
      responsive:          true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.parsed.y.toFixed(1)} benches/km²`,
          },
        },
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { font: { size: 10 } },
          grid:  { color: '#eee' },
        },
        x: { ticks: { font: { size: 11 } }, grid: { display: false } },
      },
    },
  });
}

// ── Info panel ────────────────────────────────────────────────────
function showInfo(props) {
  const panel = document.getElementById('info-content');
  const rows = [
    ['City',       CITIES[props.city]?.label || props.city],
    ['Source',     props.source],
    ['Type',       props.bench_type  || props.mun_bench_type],
    ['Material',   props.material    || props.mun_material],
    ['Location',   props.location_name || props.mun_location_name],
    ['Backrest',   props.backrest    || props.osm_backrest],
    ['Seats',      props.seats       || props.osm_seats],
    ['Maintenance',props.maintenance_class || props.mun_maintenance_class],
    ['Updated',    props.updated_date || props.mun_updated_date],
  ].filter(([, v]) => v != null && v !== '');

  panel.innerHTML = rows.map(([k, v]) =>
    `<div><strong>${k}:</strong> ${v}</div>`
  ).join('');
}

// ── Tab wiring ────────────────────────────────────────────────────
document.querySelectorAll('.city-tab').forEach(tab => {
  tab.addEventListener('click', () => setActiveCity(tab.dataset.city));
});

// ── Boot ──────────────────────────────────────────────────────────
loadAll().catch(err => console.error('Failed to load data:', err));
