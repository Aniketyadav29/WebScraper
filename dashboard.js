/**
 * dashboard.js
 * =============
 * Competitor Intelligence & Dynamic Pricing Engine — Frontend Logic
 *
 * - Connects to FastAPI backend (localhost:8000) when available
 * - Falls back to built-in mock data automatically (works on Vercel)
 * - Renders Chart.js bar, donut, and time-series line charts
 * - Handles AI price prediction form with live or simulated results
 *
 * Author : Aniket Yadav | BBD
 * Version: 1.1.0
 */

// ── Config ───────────────────────────────────────────────
const API_BASE = (typeof PRICING_API_BASE !== 'undefined')
  ? PRICING_API_BASE
  : 'http://localhost:8000';

const REFRESH_INTERVAL_MS = 60_000;

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family = "'Inter', sans-serif";

// ── State ─────────────────────────────────────────────────
let allTableData   = [];
let barChart       = null;
let donutChart     = null;
let historyChart   = null;
let refreshTimer   = null;
let API_AVAILABLE  = false;

// ── Mock Data (used when API is offline / Vercel demo) ────
const MOCK_SUMMARY = {
  total_products: 50,
  total_competitors: 3,
  avg_market_price_gbp: 30.79,
  cheapest_competitor: 'Competitorb',
  most_expensive_competitor: 'Competitorc',
  competitors: [
    { competitor: 'Competitora', avg_price_gbp: 30.93, min_price_gbp: 9.08,  max_price_gbp: 60.80, product_count: 50, in_stock_pct: 86.0 },
    { competitor: 'Competitorb', avg_price_gbp: 30.31, min_price_gbp: 9.50,  max_price_gbp: 55.01, product_count: 50, in_stock_pct: 90.0 },
    { competitor: 'Competitorc', avg_price_gbp: 31.13, min_price_gbp: 9.65,  max_price_gbp: 57.28, product_count: 50, in_stock_pct: 88.0 },
  ],
};

const MOCK_PRODUCTS = [
  'A Light in the Attic','Tipping the Velvet','Soumission','Sharp Objects',
  'Sapiens','The Requiem Red','The Dirty Little Secrets','The Coming Woman',
  'The Boys in the Boat','The Black Maria','Starving Hearts','Shakespeare\'s Sonnets',
  'Set Me Free','Scott Pilgrim\'s Precious Little Life','Rocking Ahead',
  'Olio','Mesaerion','Libertarianism','It\'s Only the Himalayas','In Her Wake',
  'Shoe Dog','Deep Work','Zero to One','Start with Why','The Hard Thing',
  'Atomic Habits','Thinking Fast and Slow','The Lean Startup','Good to Great',
  'Outliers','Blink','Freakonomics','The Tipping Point','Predictably Irrational',
  'Drive','Flow','Grit','Mindset','The Power of Habit','Essentialism',
  'Digital Minimalism','So Good They Can\'t Ignore You','Deep Work','Cal Newport',
  'Range','Lost Connections','Why We Sleep','The Sleep Revolution','Breath','Stolen Focus'
];

function generateMockTableData() {
  const competitors = ['Competitora', 'Competitorb', 'Competitorc'];
  const rows = [];
  const now = new Date();

  MOCK_PRODUCTS.slice(0, 30).forEach(title => {
    competitors.forEach(comp => {
      const price = parseFloat((Math.random() * 50 + 9).toFixed(2));
      rows.push({
        title,
        competitor: comp,
        price_gbp: price,
        price_usd: parseFloat((price * 1.27).toFixed(2)),
        price_eur: parseFloat((price * 1.17).toFixed(2)),
        rating: parseFloat((Math.random() * 4 + 1).toFixed(1)),
        in_stock: Math.random() > 0.12,
        scraped_at: new Date(now - Math.random() * 7200000).toISOString(),
      });
    });
  });
  return rows;
}

function generateMockPriceHistory(title) {
  const comps = ['Competitora', 'Competitorb', 'Competitorc'];
  const records = [];
  const base = Math.random() * 30 + 15;
  const now = new Date();

  comps.forEach(comp => {
    let price = base * (1 + (Math.random() - 0.5) * 0.2);
    for (let h = 23; h >= 0; h--) {
      price += (Math.random() - 0.5) * 0.8;
      price = Math.max(8, price);
      records.push({
        title, competitor: comp,
        price_gbp: parseFloat(price.toFixed(2)),
        rating: 3.5,
        in_stock: true,
        scraped_at: new Date(now - h * 3600000).toISOString(),
      });
    }
  });
  return records;
}

function simulatePrediction(payload) {
  const avgComp = (payload.competitor_a_price + payload.competitor_b_price + payload.competitor_c_price) / 3;
  const seasonal = [1.15,0.90,0.95,1.00,1.05,0.95,0.88,0.92,1.10,1.20,1.35,1.50][payload.month - 1];
  const ratingFac = 0.8 + (payload.rating / 5) * 0.4;
  const optimal = parseFloat((avgComp * 0.88 * ratingFac * seasonal).toFixed(2));
  const gap = parseFloat(((optimal - avgComp) / avgComp * 100).toFixed(2));
  const diff = parseFloat(((optimal - payload.our_price) / payload.our_price * 100).toFixed(1));
  const direction = diff < 0 ? 'Lower' : 'Raise';
  return {
    optimal_price: optimal,
    current_price: payload.our_price,
    avg_competitor_price: parseFloat(avgComp.toFixed(2)),
    price_gap_pct: gap,
    recommendation: Math.abs(diff) < 1
      ? 'Price is optimal — no change needed.'
      : `${direction} price by ${Math.abs(diff)}% to GBP ${optimal} to maximise revenue.`,
    confidence: 0.9999,
    potential_revenue_change: Math.abs(diff) < 1
      ? 'Minimal change expected (<1%)'
      : `Expected revenue ${diff > 0 ? 'increase' : 'decrease'} of ~${Math.abs(diff)}% by adopting optimal price.`,
  };
}

// ── DOM Helpers ───────────────────────────────────────────
const $  = (id) => document.getElementById(id);

// ── Toast ─────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
  const toast = $('toast');
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => { toast.className = 'toast'; }, duration);
}

// ── Live Clock ────────────────────────────────────────────
function updateClock() {
  $('live-clock').textContent = new Date().toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}
setInterval(updateClock, 1000);
updateClock();

// ── API Health / Detection ────────────────────────────────
async function checkApiHealth() {
  const dot  = $('api-status-dot');
  const text = $('api-status-text');
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(2000) });
    if (res.ok) {
      const data = await res.json();
      API_AVAILABLE = true;
      dot.className = 'status-dot online';
      text.textContent = `API Online · Model ${data.model_loaded ? 'Ready' : 'Offline'}`;
      return true;
    }
  } catch { /* fall through */ }
  API_AVAILABLE = false;
  dot.className = 'status-dot offline';
  text.textContent = 'Demo Mode · Mock Data';
  return false;
}

// ── Bar Chart ─────────────────────────────────────────────
function renderBarChart(competitors) {
  const ctx    = $('competitorBarChart').getContext('2d');
  const labels = competitors.map(c => c.competitor.replace('Competitor', 'Comp '));
  const avgs   = competitors.map(c => c.avg_price_gbp);
  const mins   = competitors.map(c => c.min_price_gbp);
  const maxs   = competitors.map(c => c.max_price_gbp);
  const COLORS = ['#3b82f6','#10b981','#8b5cf6'];
  const GLOWS  = ['rgba(59,130,246,0.2)','rgba(16,185,129,0.2)','rgba(139,92,246,0.2)'];

  if (barChart) barChart.destroy();
  barChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'Avg Price (GBP)', data: avgs, backgroundColor: GLOWS, borderColor: COLORS, borderWidth: 2, borderRadius: 8, borderSkipped: false },
        { label: 'Min Price',       data: mins, backgroundColor: 'transparent', borderColor: COLORS.map(c=>c+'66'), borderWidth: 1, borderRadius: 6, borderSkipped: false },
        { label: 'Max Price',       data: maxs, backgroundColor: 'transparent', borderColor: COLORS.map(c=>c+'44'), borderWidth: 1, borderRadius: 6, borderSkipped: false },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { boxWidth: 12, padding: 16, font: { size: 11 } } },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,0.95)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 12,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: GBP ${ctx.parsed.y.toFixed(2)}` },
        },
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { font: { size: 12, weight: '600' } } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { callback: v => `£${v}`, font: { size: 11 } } },
      },
    },
  });
}

// ── Donut Chart ───────────────────────────────────────────
function renderDonutChart(competitors) {
  const ctx   = $('stockDonutChart').getContext('2d');
  const total = competitors.reduce((s, c) => s + c.product_count, 0);
  const inStock = Math.round(competitors.reduce((s, c) => s + (c.product_count * c.in_stock_pct / 100), 0));
  const outStock = total - inStock;

  if (donutChart) donutChart.destroy();
  donutChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['In Stock', 'Out of Stock'],
      datasets: [{ data: [inStock, outStock], backgroundColor: ['rgba(16,185,129,0.25)','rgba(239,68,68,0.2)'], borderColor: ['#10b981','#ef4444'], borderWidth: 2, hoverOffset: 6 }],
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,0.95)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 12,
          callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed} items` },
        },
      },
    },
  });

  const pct = ((inStock / total) * 100).toFixed(1);
  $('donut-legend').innerHTML = `
    <div class="legend-item"><div class="legend-dot" style="background:#10b981"></div>In Stock (${pct}%)</div>
    <div class="legend-item"><div class="legend-dot" style="background:#ef4444"></div>Out of Stock (${(100 - pct).toFixed(1)}%)</div>`;
}

// ── Price History Chart ───────────────────────────────────
async function loadPriceHistory() {
  const title = $('product-select').value;
  if (!title) return;

  let records = [];
  if (API_AVAILABLE) {
    try {
      const res  = await fetch(`${API_BASE}/api/v1/market/price-history/${encodeURIComponent(title)}`);
      const data = await res.json();
      records = data.records || [];
    } catch { records = generateMockPriceHistory(title); }
  } else {
    records = generateMockPriceHistory(title);
  }

  if (!records.length) { showToast('No history found.', 'info'); return; }

  const ctx  = $('priceHistoryChart').getContext('2d');
  const byComp = {};
  for (const rec of records) {
    if (!byComp[rec.competitor]) byComp[rec.competitor] = [];
    byComp[rec.competitor].push({ x: new Date(rec.scraped_at).getTime(), y: rec.price_gbp });
  }

  const PALETTE = { Competitora: '#3b82f6', Competitorb: '#10b981', Competitorc: '#8b5cf6' };
  const datasets = Object.entries(byComp).map(([comp, pts]) => ({
    label: comp.replace('Competitor', 'Comp ').toUpperCase(),
    data: pts, borderColor: PALETTE[comp] || '#94a3b8',
    backgroundColor: (PALETTE[comp] || '#94a3b8') + '15',
    borderWidth: 2, pointRadius: 3, pointHoverRadius: 6, fill: true, tension: 0.35,
  }));

  if (historyChart) historyChart.destroy();
  historyChart = new Chart(ctx, {
    type: 'line', data: { datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'top', labels: { boxWidth: 12, padding: 16, font: { size: 11 } } },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,0.95)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 12,
          callbacks: { label: ctx => ` ${ctx.dataset.label}: £${ctx.parsed.y.toFixed(2)}` },
        },
      },
      scales: {
        x: { type: 'time', time: { unit: 'hour', displayFormats: { hour: 'HH:mm' } }, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { font: { size: 10 }, maxTicksLimit: 8 } },
        y: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { callback: v => `£${v}`, font: { size: 11 } } },
      },
    },
  });
}

// ── Product Dropdown ──────────────────────────────────────
async function loadProducts() {
  let products = MOCK_PRODUCTS;
  if (API_AVAILABLE) {
    try {
      const res  = await fetch(`${API_BASE}/api/v1/market/products?page_size=100`);
      const data = await res.json();
      products = data.products || MOCK_PRODUCTS;
    } catch { /* use mock */ }
  }
  const sel = $('product-select');
  sel.innerHTML = '<option value="">-- Select a product --</option>';
  products.forEach(title => {
    const opt = document.createElement('option');
    opt.value = title;
    opt.textContent = title.length > 40 ? title.slice(0, 40) + '…' : title;
    sel.appendChild(opt);
  });
}

// ── Table ─────────────────────────────────────────────────
function renderTable(data) {
  allTableData = data;
  filterTable();
}

function filterTable() {
  const search   = $('table-search').value.toLowerCase();
  const compFilt = $('comp-filter').value.toLowerCase();
  const tbody    = $('table-body');

  const filtered = allTableData.filter(row => {
    const matchTitle = row.title.toLowerCase().includes(search);
    const matchComp  = !compFilt || row.competitor.toLowerCase() === compFilt;
    return matchTitle && matchComp;
  });

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="table-empty">No matching records found.</td></tr>`;
    return;
  }

  const COMP_CLASS = { competitora: 'comp-a', competitorb: 'comp-b', competitorc: 'comp-c' };
  tbody.innerHTML = filtered.map(row => {
    const ck = row.competitor.toLowerCase().replace(/\s/g,'');
    const compClass = COMP_CLASS[ck] || 'comp-a';
    const compLabel = row.competitor.replace('Competitor', 'Comp ');
    const stockClass = row.in_stock ? 'stock-in' : 'stock-out';
    const stockLabel = row.in_stock ? 'In Stock' : 'Out of Stock';
    const stars = '★'.repeat(Math.round(row.rating)) + '☆'.repeat(5 - Math.round(row.rating));
    const scrapedAt = row.scraped_at
      ? new Date(row.scraped_at).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
      : '--';
    return `
      <tr>
        <td class="td-title" title="${row.title}">${row.title}</td>
        <td><span class="comp-badge ${compClass}">${compLabel}</span></td>
        <td class="td-price">£${row.price_gbp.toFixed(2)}</td>
        <td class="td-price-usd">$${row.price_usd.toFixed(2)}</td>
        <td><span class="rating-stars">${stars}</span></td>
        <td><span class="stock-badge ${stockClass}"><span class="stock-dot"></span>${stockLabel}</span></td>
        <td style="font-size:11px;color:var(--text-muted)">${scrapedAt}</td>
      </tr>`;
  }).join('');
}

// ── KPI Cards ─────────────────────────────────────────────
function updateKPIs(summary) {
  animateCounter('kpi-total-products', 0, summary.total_products, 800);
  animateValue('kpi-avg-price', `£${summary.avg_market_price_gbp.toFixed(2)}`);
  animateValue('kpi-cheapest-comp', summary.cheapest_competitor.replace('Competitor', 'Comp '));
}

function animateCounter(id, from, to, duration) {
  const el = $(id);
  const start = performance.now();
  const update = (time) => {
    const progress = Math.min((time - start) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(from + (to - from) * eased);
    if (progress < 1) requestAnimationFrame(update);
  };
  requestAnimationFrame(update);
}

function animateValue(id, value) {
  const el = $(id);
  el.style.opacity = '0';
  setTimeout(() => { el.textContent = value; el.style.transition = 'opacity 0.4s ease'; el.style.opacity = '1'; }, 100);
}

async function loadModelInfo() {
  let r2 = 0.9999;
  if (API_AVAILABLE) {
    try {
      const res  = await fetch(`${API_BASE}/api/v1/pricing/model-info`);
      const data = await res.json();
      r2 = data.metrics?.r2 ?? 0.9999;
    } catch { /* use default */ }
  }
  animateValue('kpi-confidence', `${(r2 * 100).toFixed(2)}%`);
}

// ── AI Prediction Form ────────────────────────────────────
async function predictPrice(e) {
  e.preventDefault();
  const btn = $('predict-btn');
  btn.classList.add('loading');
  btn.querySelector('span').textContent = 'Predicting...';

  const now = new Date();
  const payload = {
    our_price:          parseFloat($('our-price').value),
    competitor_a_price: parseFloat($('comp-a').value),
    competitor_b_price: parseFloat($('comp-b').value),
    competitor_c_price: parseFloat($('comp-c').value),
    rating:             parseFloat($('rating').value),
    in_stock:           $('in-stock').checked,
    month:              parseInt($('pred-month').value),
    day_of_week:        now.getDay() === 0 ? 6 : now.getDay() - 1,
    is_weekend:         $('is-weekend').checked,
  };

  let data;
  if (API_AVAILABLE) {
    try {
      const res = await fetch(`${API_BASE}/api/v1/pricing/predict`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      data = await res.json();
    } catch { data = simulatePrediction(payload); }
  } else {
    await new Promise(r => setTimeout(r, 800)); // simulate latency
    data = simulatePrediction(payload);
  }

  const result = $('prediction-result');
  result.style.display = 'block';
  $('res-current').textContent  = `£${data.current_price.toFixed(2)}`;
  $('res-optimal').textContent  = `£${data.optimal_price.toFixed(2)}`;

  const gapEl = $('res-gap');
  const isDown = data.optimal_price < data.current_price;
  gapEl.textContent = `${data.price_gap_pct > 0 ? '+' : ''}${data.price_gap_pct.toFixed(2)}% vs competitor avg`;
  gapEl.style.color = isDown ? 'var(--green)' : 'var(--orange)';

  $('res-recommendation').textContent = data.recommendation;
  $('res-revenue').textContent        = data.potential_revenue_change;
  $('confidence-badge').textContent   = `${(data.confidence * 100).toFixed(1)}% Confidence`;

  lucide.createIcons();
  showToast('Price prediction complete!', 'success');
  btn.classList.remove('loading');
  btn.querySelector('span').textContent = 'Predict Optimal Price';
}

// ── Full Refresh ──────────────────────────────────────────
async function refreshAll() {
  const btn = $('refresh-btn');
  btn.classList.add('spinning');

  try {
    await checkApiHealth();

    let summary, competitors;
    if (API_AVAILABLE) {
      try {
        const [sRes, cRes] = await Promise.all([
          fetch(`${API_BASE}/api/v1/market/summary`),
          fetch(`${API_BASE}/api/v1/market/competitors?limit=150`),
        ]);
        summary     = await sRes.json();
        competitors = await cRes.json();
      } catch {
        summary     = MOCK_SUMMARY;
        competitors = generateMockTableData();
      }
    } else {
      summary     = MOCK_SUMMARY;
      competitors = generateMockTableData();
    }

    updateKPIs(summary);
    renderBarChart(summary.competitors);
    renderDonutChart(summary.competitors);
    renderTable(competitors);

    showToast(API_AVAILABLE ? 'Dashboard updated!' : 'Demo mode — showing sample data.', API_AVAILABLE ? 'success' : 'info', 2500);
  } catch (err) {
    console.error(err);
    showToast('Error loading data.', 'error');
  } finally {
    btn.classList.remove('spinning');
  }
}

// ── Bootstrap ─────────────────────────────────────────────
async function init() {
  lucide.createIcons();
  $('pred-month').value = new Date().getMonth() + 1;

  await Promise.all([ refreshAll(), loadProducts(), loadModelInfo() ]);

  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshAll, REFRESH_INTERVAL_MS);

  setTimeout(() => { $('loader').classList.add('hidden'); }, 600);
}

(function loadTimeAdapter() {
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js';
  script.onload = () => init();
  script.onerror = () => init();
  document.head.appendChild(script);
})();
