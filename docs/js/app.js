/* =================================================================
   Nordic Bench Map – App Logic
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
let activeCity   = 'all';
let activeView   = 'points';   // 'points' | 'heatmap' | 'districts'
let activeMetric = 'density';  // 'density' | 'percapita'
let summary      = {};
let allFeatures  = [];

const pointLayers   = {};   // city → L.layerGroup
const districtLayers = {};  // city → L.geoJSON (rebuilt on metric change)
let districtData    = {};
let heatLayer       = null;
let densityChart    = null;

// ── Map ──────────────────────────────────────────────────────────────
const map = L.map('map', { zoomControl: true }).setView([59.0, 20.0], 5);

L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
  attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://openstreetmap.org">OSM</a>',
  subdomains: 'abcd', maxZoom: 19,
}).addTo(map);

// Labels on top so they render above polygons
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_only_labels/{z}/{x}/{y}{r}.png', {
  subdomains: 'abcd', maxZoom: 19, pane: 'shadowPane',
}).addTo(map);

// ── Colour scale ─────────────────────────────────────────────────────
// Sequential: light yellow → orange → red → dark purple
const COLOR_STOPS = [
  [255, 255, 204],
  [254, 204,  92],
  [253, 141,  60],
  [227,  26,  28],
  [128,   0, 122],
];

function scaleColor(t) {
  const n   = COLOR_STOPS.length - 1;
  const idx = Math.min(Math.floor(t * n), n - 1);
  const f   = t * n - idx;
  const a   = COLOR_STOPS[idx], b = COLOR_STOPS[idx + 1] || a;
  const r   = Math.round(a[0] + (b[0] - a[0]) * f);
  const g   = Math.round(a[1] + (b[1] - a[1]) * f);
  const bl  = Math.round(a[2] + (b[2] - a[2]) * f);
  return `rgb(${r},${g},${bl})`;
}

// ── Points view ───────────────────────────────────────────────────────
function markerOptions(feature) {
  const city  = feature.properties?.city || 'unknown';
  const color = CITIES[city]?.color || '#888';
  return L.circleMarker(
    [feature.geometry.coordinates[1], feature.geometry.coordinates[0]],
    { radius: 3, fillColor: color, color: '#fff', weight: 0.5,
      opacity: 1, fillOpacity: 0.7 }
  );
}

function popupContent(props) {
  const rows = [
    ['City',     CITIES[props.city]?.label || props.city],
    ['Type',     props.bench_type  || props.mun_bench_type],
    ['Material', props.material    || props.mun_material],
    ['Location', props.location_name || props.mun_location_name],
    ['Backrest', props.backrest    || props.osm_backrest],
    ['Seats',    props.seats       || props.osm_seats],
  ].filter(([, v]) => v != null && v !== '' && v !== 'null');
  return `<div class="popup-city">${CITIES[props.city]?.label || props.city || '–'}</div>
    <table class="popup-table">${
      rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('')
    }</table>`;
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
  ].filter(([, v]) => v != null && v !== '' && v !== 'null');
  document.getElementById('info-content').innerHTML =
    rows.map(([k, v]) => `<div><strong>${k}:</strong> ${v}</div>`).join('') ||
    '<span class="muted">No details available.</span>';
}

// ── Data loading ─────────────────────────────────────────────────────
async function loadAll() {
  try {
    const r = await fetch('data/summary.json');
    if (r.ok) summary = await r.json();
  } catch (_) {}

  const cityKeys = Object.keys(CITIES);
  const [benchRes, districtRes] = await Promise.all([
    Promise.allSettled(cityKeys.map(k => fetch(`data/${k}_benches.geojson`).then(r => r.json()))),
    Promise.allSettled(cityKeys.map(k => fetch(`data/${k}_districts.geojson`).then(r => r.json()))),
  ]);

  benchRes.forEach((res, i) => {
    const key = cityKeys[i];
    if (res.status === 'rejected') { console.warn('bench load failed', key); return; }
    const geojson = res.value;
    const group   = L.layerGroup();
    L.geoJSON(geojson, {
      pointToLayer: feat => {
        const m = markerOptions(feat);
        m.on('click', () => showBenchInfo(feat.properties));
        m.bindPopup(popupContent(feat.properties), { maxWidth: 240 });
        return m;
      },
    }).addTo(group);
    pointLayers[key] = group;
    allFeatures.push(...(geojson.features || []));
  });

  districtRes.forEach((res, i) => {
    const key = cityKeys[i];
    if (res.status === 'rejected') { console.warn('district load failed', key); return; }
    districtData[key] = res.value;
  });

  Object.values(pointLayers).forEach(g => g.addTo(map));
  renderSidebar();
  renderChart();
  renderLegend();
}

// ── Layer management ─────────────────────────────────────────────────
function applyLayers() {
  // Remove everything
  Object.values(pointLayers).forEach(g => map.hasLayer(g) && map.removeLayer(g));
  if (heatLayer) { map.removeLayer(heatLayer); heatLayer = null; }
  Object.values(districtLayers).forEach(g => map.hasLayer(g) && map.removeLayer(g));

  const keys = activeCity === 'all' ? Object.keys(CITIES) : [activeCity];

  if (activeView === 'points') {
    keys.forEach(k => pointLayers[k] && pointLayers[k].addTo(map));

  } else if (activeView === 'heatmap') {
    const pts = allFeatures
      .filter(f => activeCity === 'all' || f.properties?.city === activeCity)
      .map(f => [f.geometry.coordinates[1], f.geometry.coordinates[0], 0.5]);
    heatLayer = L.heatLayer(pts, {
      radius: 14, blur: 18, maxZoom: 17, max: 1.0,
      gradient: { 0.1: '#ffffcc', 0.4: '#fd8d3c', 0.7: '#e31a1c', 1.0: '#7a0177' },
    }).addTo(map);

  } else if (activeView === 'districts') {
    // Compute global max for the active metric across all shown cities
    const globalMax = computeGlobalMax(keys, activeMetric);
    keys.forEach(k => {
      if (!districtData[k]) return;
      buildDistrictLayer(k, globalMax);
      districtLayers[k] && districtLayers[k].addTo(map);
    });
    renderLegend(globalMax);
  }

  // Show/hide UI panels
  document.getElementById('section-district').style.display =
    activeView === 'districts' ? '' : 'none';
  document.getElementById('info-panel').style.display =
    activeView === 'points' ? '' : 'none';
  document.getElementById('legend-box').style.display =
    activeView === 'districts' ? '' : 'none';
  document.getElementById('metric-row').style.display =
    activeView === 'districts' ? '' : 'none';
}

function computeGlobalMax(keys, metric) {
  let max = 0;
  keys.forEach(k => {
    if (!districtData[k]) return;
    districtData[k].features.forEach(f => {
      const val = metricValue(f.properties, metric);
      if (val != null && val > max) max = val;
    });
  });
  return max || 1;
}

function metricValue(props, metric) {
  if (metric === 'density') return props.bench_density || 0;
  if (metric === 'percapita') {
    if (!props.population || !props.bench_count) return null;
    return (props.bench_count / props.population) * 1000;
  }
  return 0;
}

// ── District choropleth ───────────────────────────────────────────────
function buildDistrictLayer(cityKey, globalMax) {
  // Remove old layer if exists
  if (districtLayers[cityKey]) {
    if (map.hasLayer(districtLayers[cityKey])) map.removeLayer(districtLayers[cityKey]);
    delete districtLayers[cityKey];
  }
  const data = districtData[cityKey];
  if (!data) return;

  const layer = L.geoJSON(data, {
    style: feat => {
      const val = metricValue(feat.properties, activeMetric);
      const hasVal = val != null && globalMax > 0;
      return {
        fillColor:   hasVal ? scaleColor(val / globalMax) : '#e5e7eb',
        fillOpacity: hasVal ? 0.80 : 0.3,
        color:       '#fff',
        weight:      1.5,
        opacity:     1,
      };
    },
    onEachFeature: (feat, lyr) => {
      const val = metricValue(feat.properties, activeMetric);
      const label = activeMetric === 'density'
        ? (val != null ? `${val.toFixed(1)} benches/km²` : 'no data')
        : (val != null ? `${val.toFixed(1)} benches/1k pop.` : 'no data');
      lyr.bindTooltip(
        `<strong>${feat.properties.name}</strong><br>${label}`,
        { sticky: true, className: 'district-tooltip' }
      );
      lyr.on('click', () => showDistrictInfo(feat.properties));
      lyr.on('mouseover', function () { this.setStyle({ weight: 2.5, color: '#333' }); });
      lyr.on('mouseout',  function () { layer.resetStyle(this); });
    },
  });

  districtLayers[cityKey] = layer;
}

function showDistrictInfo(props) {
  const name     = props.name || '–';
  const city     = CITIES[props.city]?.label || props.city || '';
  const count    = (props.bench_count ?? 0).toLocaleString();
  const density  = props.bench_density != null ? props.bench_density.toFixed(1) : '–';
  const area     = props.area_km2 != null ? props.area_km2.toFixed(1) : '–';
  const pop      = props.population != null ? props.population.toLocaleString() : null;
  const popDens  = props.pop_density != null ? Math.round(props.pop_density).toLocaleString() : null;
  const perCap   = (props.population && props.bench_count)
    ? (props.bench_count / props.population * 1000).toFixed(1) : null;

  let html = `
    <div class="district-name">${name}
      <span class="district-city">${city}</span>
    </div>
    <div class="stat-row"><span>Benches</span><span>${count}</span></div>
    <div class="stat-row"><span>Bench density</span><span>${density} / km²</span></div>
    <div class="stat-row"><span>Area</span><span>${area} km²</span></div>`;

  if (pop) {
    html += `
    <div class="stat-divider"></div>
    <div class="stat-row"><span>Population</span><span>${pop}</span></div>`;
    if (popDens) html += `<div class="stat-row"><span>Pop. density</span><span>${popDens} / km²</span></div>`;
    if (perCap)  html += `<div class="stat-row stat-highlight"><span>Benches per 1,000 people</span><span>${perCap}</span></div>`;
  } else {
    html += `<div class="stat-note">Population data not available for this city.</div>`;
  }

  document.getElementById('district-content').innerHTML = html;
}

// ── Legend ────────────────────────────────────────────────────────────
function renderLegend(globalMax) {
  const box = document.getElementById('legend-box');
  if (!box) return;

  const metric = activeMetric;
  const unit   = metric === 'density' ? 'benches/km²' : 'benches/1k pop.';
  const max    = globalMax ?? 1;
  const steps  = [0, 0.25, 0.5, 0.75, 1.0];

  const rows = steps.map(t => {
    const color = t === 0 ? '#e5e7eb' : scaleColor(t);
    const val   = (t * max).toFixed(t === 0 ? 0 : 1);
    return `<div class="legend-row">
      <div class="legend-swatch" style="background:${color}"></div>
      <span>${t === 0 ? '0' : val}</span>
    </div>`;
  }).reverse().join('');

  box.innerHTML = `<div class="legend-title">${unit}</div>${rows}`;
}

// ── Sidebar ───────────────────────────────────────────────────────────
function renderSidebar() {
  const container = document.getElementById('city-cards');
  container.innerHTML = '';

  Object.entries(CITIES).forEach(([key, meta]) => {
    const s       = summary[key] || {};
    const total   = s.total ?? 0;
    const dens    = s.density_per_km2 != null ? s.density_per_km2.toFixed(1) : '–';
    const area    = s.area_km2 ?? '–';
    const osmPct  = total > 0
      ? Math.round(100 * ((s.osm_only || 0) + (s.municipal_osm || 0)) / total) : 0;

    const card = document.createElement('div');
    card.className = 'city-card active';
    card.dataset.city = key;
    card.innerHTML = `
      <div class="city-card-header">
        <span class="city-dot"></span>
        <span class="city-card-name">${meta.label}</span>
        <span class="city-card-total">${total.toLocaleString()}</span>
      </div>
      <div class="stat-row"><span>Bench density</span><span>${dens} / km²</span></div>
      <div class="stat-row"><span>OSM coverage</span><span>${osmPct}%</span></div>
      <div class="stat-row"><span>City area</span><span>${area} km²</span></div>`;
    card.addEventListener('click', () => setActiveCity(activeCity === key ? 'all' : key));
    container.appendChild(card);
  });
}

// ── Density chart ─────────────────────────────────────────────────────
function renderChart() {
  const ctx       = document.getElementById('density-chart').getContext('2d');
  const cityKeys  = Object.keys(CITIES);
  const labels    = cityKeys.map(k => CITIES[k].label);
  const densities = cityKeys.map(k => summary[k]?.density_per_km2 ?? 0);
  const colors    = cityKeys.map(k => CITIES[k].color);

  if (densityChart) densityChart.destroy();
  densityChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        data: densities,
        backgroundColor: colors.map(c => c + 'cc'),
        borderColor: colors,
        borderWidth: 1.5,
        borderRadius: 4,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${c.parsed.y.toFixed(1)} / km²` } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { font: { size: 10 } }, grid: { color: '#eee' } },
        x: { ticks: { font: { size: 11 } }, grid: { display: false } },
      },
    },
  });
}

// ── View / city switching ─────────────────────────────────────────────
function setView(view) {
  activeView = view;
  document.querySelectorAll('.view-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.view === view));
  applyLayers();
}

function setActiveCity(city) {
  activeCity = city;
  document.querySelectorAll('.city-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.city === city));
  document.querySelectorAll('.city-card').forEach(c =>
    c.classList.toggle('active', c.dataset.city === city || city === 'all'));

  if (city !== 'all' && BBOXES[city]) {
    map.flyToBounds(BBOXES[city], { padding: [30, 30], duration: 0.8 });
  } else {
    map.flyTo([59.0, 20.0], 5, { duration: 0.8 });
  }
  applyLayers();
}

function setMetric(metric) {
  activeMetric = metric;
  document.querySelectorAll('.metric-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.metric === metric));
  // Rebuild district layers with new metric + new global max
  if (activeView === 'districts') applyLayers();
}

// ── Event wiring ──────────────────────────────────────────────────────
document.querySelectorAll('.city-tab').forEach(t =>
  t.addEventListener('click', () => setActiveCity(t.dataset.city)));
document.querySelectorAll('.view-btn').forEach(b =>
  b.addEventListener('click', () => setView(b.dataset.view)));
document.querySelectorAll('.metric-btn').forEach(b =>
  b.addEventListener('click', () => setMetric(b.dataset.metric)));

// ── Boot ──────────────────────────────────────────────────────────────
loadAll().catch(err => console.error('Load failed:', err));
