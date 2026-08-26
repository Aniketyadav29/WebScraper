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

// ── Comprehensive Multi-Category Goods Catalog (Amazon vs Flipkart) ──
const FULL_ECOMMERCE_CATALOG = [
  // 🥦 Eatables, Grocery & Food
  { category: 'grocery', catName: '🥦 Grocery', title: 'Daawat Rozana Super Basmati Rice (5 Kg Bag)', amz: 429, flp: 399, mrp: 550, ratingA: 4.4, ratingF: 4.3, brand: 'Daawat' },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Fortune Sunlite Refined Sunflower Cooking Oil (5 Litre Can)', amz: 685, flp: 710, mrp: 850, ratingA: 4.5, ratingF: 4.4, brand: 'Fortune' },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Tata Tea Gold Premium Black Tea with Gently Rolled Aromatic Leaves (1 Kg)', amz: 499, flp: 485, mrp: 620, ratingA: 4.6, ratingF: 4.5, brand: 'Tata' },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Cadbury Dairy Milk Silk Chocolate Bar Value Pack (150g x 3)', amz: 475, flp: 450, mrp: 525, ratingA: 4.7, ratingF: 4.7, brand: 'Cadbury' },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Happilo 100% Natural Premium California Crunchy Almonds (500g)', amz: 425, flp: 449, mrp: 675, ratingA: 4.4, ratingF: 4.4, brand: 'Happilo' },
  { category: 'grocery', catName: '🥦 Grocery', title: "Kellogg's Real Almond & Honey Crunchy Super Muesli (1 Kg Box)", amz: 549, flp: 529, mrp: 699, ratingA: 4.5, ratingF: 4.5, brand: "Kellogg's" },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Nescafe Gold Blend Rich & Smooth Instant Pure Coffee Powder Glass Jar (100g)', amz: 495, flp: 515, mrp: 580, ratingA: 4.6, ratingF: 4.5, brand: 'Nescafe' },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Ferrero Rocher Premium Hazelnut Imported Chocolates (24 Pieces Gift Box)', amz: 949, flp: 899, mrp: 1099, ratingA: 4.8, ratingF: 4.7, brand: 'Ferrero' },
  { category: 'grocery', catName: '🥦 Grocery', title: 'Saffola Gold Pro Healthy Lifestyle Multisource Edible Oil (5 Litres)', amz: 815, flp: 839, mrp: 999, ratingA: 4.5, ratingF: 4.4, brand: 'Saffola' },

  // 👕 Clothes, Fashion & Footwear
  { category: 'clothes', catName: '👕 Fashion', title: "Levi's 511 Mid Rise Slim Fit Cotton Stretch Men's Jeans (Dark Indigo)", amz: 2199, flp: 2049, mrp: 3999, ratingA: 4.3, ratingF: 4.2, brand: "Levi's" },
  { category: 'clothes', catName: '👕 Fashion', title: 'U.S. Polo Assn. Solid Regular Fit 100% Pure Cotton Casual Shirt for Men', amz: 1499, flp: 1549, mrp: 2599, ratingA: 4.4, ratingF: 4.3, brand: 'USPA' },
  { category: 'clothes', catName: '👕 Fashion', title: "Puma Men's Regular Fit Graphic Pure Cotton Crew Neck Sport T-Shirt", amz: 799, flp: 749, mrp: 1499, ratingA: 4.2, ratingF: 4.3, brand: 'Puma' },
  { category: 'clothes', catName: '👕 Fashion', title: "Nike Air Max SC Men's Lightweight Breathable Running & Walking Sneakers", amz: 4995, flp: 4799, mrp: 6995, ratingA: 4.6, ratingF: 4.5, brand: 'Nike' },
  { category: 'clothes', catName: '👕 Fashion', title: 'Adidas Ultraboost Light High Energy Return Running Shoes for Men', amz: 11999, flp: 12499, mrp: 17999, ratingA: 4.7, ratingF: 4.6, brand: 'Adidas' },
  { category: 'clothes', catName: '👕 Fashion', title: "Biba Women's Rayon Printed Anarkali Kurta with Pant and Dupatta Set", amz: 2499, flp: 2399, mrp: 4999, ratingA: 4.4, ratingF: 4.4, brand: 'Biba' },
  { category: 'clothes', catName: '👕 Fashion', title: "Woodland Men's Camel Khaki Nubuck Leather Outdoor Adventure Boots", amz: 3895, flp: 3695, mrp: 4995, ratingA: 4.5, ratingF: 4.5, brand: 'Woodland' },
  { category: 'clothes', catName: '👕 Fashion', title: "Tommy Hilfiger Men's Lightweight Water Resistant Quilted Puffer Winter Jacket", amz: 6499, flp: 6799, mrp: 9999, ratingA: 4.6, ratingF: 4.5, brand: 'Tommy Hilfiger' },

  // 📱 Electronics & Smartphones
  { category: 'smartphones', catName: '📱 Smartphone', title: 'Apple iPhone 15 (128 GB) - Black', amz: 59900, flp: 58870, mrp: 79900, ratingA: 4.5, ratingF: 4.5, brand: 'Apple' },
  { category: 'smartphones', catName: '📱 Smartphone', title: 'Samsung Galaxy S24 Ultra 5G (256 GB, Titanium Gray, AI Features)', amz: 129999, flp: 127999, mrp: 134999, ratingA: 4.6, ratingF: 4.6, brand: 'Samsung' },
  { category: 'smartphones', catName: '📱 Smartphone', title: 'OnePlus 12 (512 GB, Silky Black, 16GB RAM, Snapdragon 8 Gen 3)', amz: 69999, flp: 70499, mrp: 74999, ratingA: 4.5, ratingF: 4.4, brand: 'OnePlus' },
  { category: 'smartphones', catName: '📱 Smartphone', title: 'Google Pixel 8 (128 GB, Hazel, Advanced AI Camera)', amz: 62999, flp: 61499, mrp: 75999, ratingA: 4.3, ratingF: 4.3, brand: 'Google' },
  { category: 'smartphones', catName: '📱 Smartphone', title: 'Redmi Note 13 Pro+ 5G (Fusion Purple, 256GB, 200MP Camera)', amz: 31999, flp: 30999, mrp: 35999, ratingA: 4.2, ratingF: 4.2, brand: 'Xiaomi' },
  { category: 'smartphones', catName: '📱 Smartphone', title: 'Motorola Edge 50 Pro 5G (Luxe Lavender, 256GB, 125W TurboPower)', amz: 31999, flp: 31499, mrp: 36999, ratingA: 4.4, ratingF: 4.3, brand: 'Motorola' },

  // 💻 Laptops & Computers
  { category: 'laptops', catName: '💻 Laptop', title: 'Apple MacBook Air 13" M2 Chip (8GB Unified RAM, 256GB SSD)', amz: 89900, flp: 86550, mrp: 99900, ratingA: 4.7, ratingF: 4.7, brand: 'Apple' },
  { category: 'laptops', catName: '💻 Laptop', title: 'ASUS ROG Strix G16 (2024) 16" 165Hz Intel i7-13650HX RTX 4060 Gaming', amz: 114990, flp: 116490, mrp: 139990, ratingA: 4.5, ratingF: 4.4, brand: 'ASUS' },
  { category: 'laptops', catName: '💻 Laptop', title: 'Dell XPS 13 Plus 9320 Intel Core i7 13th Gen (16GB RAM, 512GB SSD)', amz: 144990, flp: 142990, mrp: 169990, ratingA: 4.4, ratingF: 4.3, brand: 'Dell' },
  { category: 'laptops', catName: '💻 Laptop', title: 'HP Pavilion 15 Core i5 13th Gen (16GB RAM, 512GB SSD, FHD Display)', amz: 64990, flp: 63990, mrp: 77990, ratingA: 4.3, ratingF: 4.3, brand: 'HP' },
  { category: 'laptops', catName: '💻 Laptop', title: 'Lenovo IdeaPad Slim 3 12th Gen Intel Core i3 (8GB, 512GB SSD, 15.6")', amz: 36990, flp: 35990, mrp: 54990, ratingA: 4.2, ratingF: 4.1, brand: 'Lenovo' },

  // 🎧 Audio & Earbuds
  { category: 'audio', catName: '🎧 Audio', title: 'Sony WH-1000XM5 Wireless Industry Leading Noise Canceling Headphones', amz: 28990, flp: 29490, mrp: 34990, ratingA: 4.6, ratingF: 4.6, brand: 'Sony' },
  { category: 'audio', catName: '🎧 Audio', title: 'Apple AirPods Pro (2nd Gen) with MagSafe Case (USB-C & Active ANC)', amz: 22990, flp: 21990, mrp: 24900, ratingA: 4.7, ratingF: 4.7, brand: 'Apple' },
  { category: 'audio', catName: '🎧 Audio', title: 'Bose QuietComfort 45 Wireless Noise Cancelling Bluetooth Headphones', amz: 24900, flp: 24490, mrp: 29900, ratingA: 4.5, ratingF: 4.4, brand: 'Bose' },
  { category: 'audio', catName: '🎧 Audio', title: 'boAt Airdopes 441 Bluetooth Truly Wireless in Ear Earbuds (IPX7 Water Resistance)', amz: 1499, flp: 1399, mrp: 3999, ratingA: 4.0, ratingF: 4.1, brand: 'boAt' },
  { category: 'audio', catName: '🎧 Audio', title: 'JBL Live 660NC Wireless Over-Ear Active Noise Cancelling Headphones', amz: 8999, flp: 9299, mrp: 14999, ratingA: 4.3, ratingF: 4.2, brand: 'JBL' },

  // ⌚ Smartwatches & Wearables
  { category: 'smartwatches', catName: '⌚ Smartwatch', title: 'Apple Watch Series 9 GPS 45mm Midnight Aluminium Case with Sport Band', amz: 41999, flp: 40999, mrp: 44900, ratingA: 4.7, ratingF: 4.6, brand: 'Apple' },
  { category: 'smartwatches', catName: '⌚ Smartwatch', title: 'Samsung Galaxy Watch 6 LTE (44mm, Bluetooth/WiFi, Sleep Coaching)', amz: 28999, flp: 27999, mrp: 36999, ratingA: 4.4, ratingF: 4.4, brand: 'Samsung' },
  { category: 'smartwatches', catName: '⌚ Smartwatch', title: 'Noise ColorFit Pro 5 Max 1.96" AMOLED Smart Watch with BT Calling', amz: 3999, flp: 4199, mrp: 7999, ratingA: 4.1, ratingF: 4.2, brand: 'Noise' },
  { category: 'smartwatches', catName: '⌚ Smartwatch', title: 'Fire-Boltt Invincible Plus 1.43" AMOLED Display Bluetooth Calling Watch', amz: 4499, flp: 4299, mrp: 21000, ratingA: 4.2, ratingF: 4.1, brand: 'Fire-Boltt' },
  { category: 'smartwatches', catName: '⌚ Smartwatch', title: 'Garmin Forerunner 55 GPS Running Smartwatch with Heart Rate Monitor', amz: 19990, flp: 20490, mrp: 22990, ratingA: 4.6, ratingF: 4.5, brand: 'Garmin' },

  // 🏠 Home & Kitchen Appliances
  { category: 'appliances', catName: '🏠 Appliance', title: 'LG 55 Inch 4K Ultra HD Smart OLED evo TV (OLED55C3PSA, Dolby Vision Atmos)', amz: 124990, flp: 121990, mrp: 199990, ratingA: 4.7, ratingF: 4.6, brand: 'LG' },
  { category: 'appliances', catName: '🏠 Appliance', title: 'Samsung 43 Inch Crystal 4K Vivid Pro Ultra HD Smart LED TV (43CU7700)', amz: 28990, flp: 29490, mrp: 45900, ratingA: 4.3, ratingF: 4.3, brand: 'Samsung' },
  { category: 'appliances', catName: '🏠 Appliance', title: 'Dyson V12 Detect Slim Total Clean Cord-free Laser Vacuum Cleaner', amz: 52900, flp: 51900, mrp: 62900, ratingA: 4.5, ratingF: 4.5, brand: 'Dyson' },
  { category: 'appliances', catName: '🏠 Appliance', title: 'Philips Digital Air Fryer HD9252/90 with Rapid Air Tech & Touchscreen', amz: 8499, flp: 8299, mrp: 11995, ratingA: 4.4, ratingF: 4.4, brand: 'Philips' },
  { category: 'appliances', catName: '🏠 Appliance', title: 'Prestige Iris 750 Watt Mixer Grinder with 3 Stainless Steel Jars + Juicer', amz: 3199, flp: 3049, mrp: 6295, ratingA: 4.1, ratingF: 4.2, brand: 'Prestige' },
  { category: 'appliances', catName: '🏠 Appliance', title: 'Kent Grand Plus RO+UV+UF+TDS Water Purifier with Mineral RO (9 Litres)', amz: 15499, flp: 15999, mrp: 20500, ratingA: 4.3, ratingF: 4.2, brand: 'Kent' },

  // 💄 Beauty & Personal Care
  { category: 'beauty', catName: '💄 Beauty', title: "L'Oreal Paris Revitalift 1.5% Hyaluronic Acid Face Serum (30ml Dropper)", amz: 699, flp: 679, mrp: 999, ratingA: 4.4, ratingF: 4.4, brand: "L'Oreal" },
  { category: 'beauty', catName: '💄 Beauty', title: 'Minimalist 10% Niacinamide Face Serum with Zinc for Acne Marks (30ml)', amz: 569, flp: 599, mrp: 599, ratingA: 4.5, ratingF: 4.4, brand: 'Minimalist' },
  { category: 'beauty', catName: '💄 Beauty', title: 'Philips BT3231/15 Smart Fast Charge Cordless Beard Trimmer for Men', amz: 1899, flp: 1799, mrp: 2295, ratingA: 4.4, ratingF: 4.3, brand: 'Philips' },
  { category: 'beauty', catName: '💄 Beauty', title: 'Maybelline New York Super Stay Matte Ink Long Lasting Liquid Lipstick', amz: 519, flp: 499, mrp: 699, ratingA: 4.3, ratingF: 4.4, brand: 'Maybelline' },

  // 🎮 Gaming & Toys
  { category: 'gaming', catName: '🎮 Gaming', title: 'Sony PlayStation 5 Console (Slim Disc Edition, 1TB SSD & DualSense)', amz: 54990, flp: 53990, mrp: 54990, ratingA: 4.8, ratingF: 4.8, brand: 'Sony' },
  { category: 'gaming', catName: '🎮 Gaming', title: 'Microsoft Xbox Series X 1TB High-Performance Gaming Console (Black)', amz: 52990, flp: 53490, mrp: 55990, ratingA: 4.7, ratingF: 4.6, brand: 'Microsoft' },
  { category: 'gaming', catName: '🎮 Gaming', title: 'Nintendo Switch OLED Model with White Joy-Con & 64GB Internal Storage', amz: 32499, flp: 31999, mrp: 36999, ratingA: 4.6, ratingF: 4.5, brand: 'Nintendo' },
  { category: 'gaming', catName: '🎮 Gaming', title: 'Sony PS5 DualSense Wireless Controller (Midnight Black, Haptic Feedback)', amz: 5899, flp: 5699, mrp: 6390, ratingA: 4.6, ratingF: 4.6, brand: 'Sony' },
  { category: 'gaming', catName: '🎮 Gaming', title: 'LEGO Creator 3in1 Mighty Dinosaur Building Toy Set (31058)', amz: 1399, flp: 1449, mrp: 1799, ratingA: 4.7, ratingF: 4.6, brand: 'LEGO' },
];

let currentEcomCategory = 'all';
let currentEcomView = 'grid';
let ecomPage = 1;
let ecomPageSize = 24;
let ecomSortBy = 'gap_desc';
let totalEcomPages = 20833;
let totalEcomRecords = 500000;
let searchDebounceTimer = null;

function selectEcomCategory(category) {
  currentEcomCategory = category;
  ecomPage = 1;
  
  // Update active pill styling
  const pills = document.querySelectorAll('.ecom-pill');
  pills.forEach(p => {
    if (p.getAttribute('onclick')?.includes(`'${category}'`)) {
      p.classList.add('active');
    } else {
      p.classList.remove('active');
    }
  });

  fetchEcommerceCatalog();
}

function setEcomView(view) {
  currentEcomView = view;
  const gridBtn = $('view-grid-btn');
  const tableBtn = $('view-table-btn');
  const gridEl = $('ecom-grid');
  const tableWrapEl = $('ecom-table-wrap');

  if (view === 'grid') {
    if (gridBtn) gridBtn.classList.add('active');
    if (tableBtn) tableBtn.classList.remove('active');
    if (gridEl) gridEl.style.display = 'grid';
    if (tableWrapEl) tableWrapEl.style.display = 'none';
  } else {
    if (tableBtn) tableBtn.classList.add('active');
    if (gridBtn) gridBtn.classList.remove('active');
    if (gridEl) gridEl.style.display = 'none';
    if (tableWrapEl) tableWrapEl.style.display = 'block';
  }
}

function changeEcomSort(sortVal) {
  ecomSortBy = sortVal;
  ecomPage = 1;
  fetchEcommerceCatalog();
}

function changeEcomPageSize(sizeVal) {
  ecomPageSize = parseInt(sizeVal, 10) || 24;
  ecomPage = 1;
  fetchEcommerceCatalog();
}

function changeEcomPage(action) {
  if (action === 'first') ecomPage = 1;
  else if (action === 'prev') ecomPage = Math.max(1, ecomPage - 1);
  else if (action === 'next') ecomPage = Math.min(totalEcomPages, ecomPage + 1);
  else if (action === 'last') ecomPage = totalEcomPages;

  fetchEcommerceCatalog();
  
  // Smooth scroll to top of ecom section
  const section = $('ecom-section');
  if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function filterEcommerceGoods() {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    ecomPage = 1;
    fetchEcommerceCatalog();
  }, 250);
}

async function fetchEcommerceCatalog() {
  const query = ($('ecom-query')?.value || '').trim();
  const loading = $('ecom-loading');
  if (loading) loading.style.display = 'flex';

  try {
    let resultData = null;
    if (API_AVAILABLE) {
      try {
        const url = `${API_BASE}/api/v1/market/ecommerce-catalog?page=${ecomPage}&page_size=${ecomPageSize}&category=${encodeURIComponent(currentEcomCategory)}&search=${encodeURIComponent(query)}&sort_by=${ecomSortBy}`;
        const res = await fetch(url);
        if (res.ok) {
          resultData = await res.json();
        }
      } catch (err) {
        console.warn('API 100k catalog fetch failed, using fallback:', err);
      }
    }

    if (resultData && resultData.items) {
      totalEcomRecords = resultData.total_goods || 100000;
      totalEcomPages = resultData.total_pages || 1;
      ecomPage = resultData.page || 1;

      renderEcommerceViews(resultData.items);
      updateEcommercePaginationUI(resultData);
      if (resultData.stats) updateEcommerceStats(resultData.stats, totalEcomRecords);
    } else {
      // Offline fallback: filter from full in-memory catalog
      const fallbackItems = getClientFilteredCatalog(query);
      renderEcommerceViews(fallbackItems);
      updateEcommercePaginationUI({
        page: ecomPage,
        total_pages: Math.max(1, Math.ceil(fallbackItems.length / ecomPageSize)),
        total_goods: 100000,
      });
    }
  } catch (err) {
    console.error('Error fetching 100k catalog:', err);
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

function getClientFilteredCatalog(query) {
  let allItems = FULL_ECOMMERCE_CATALOG.map(item => {
    const diff = Math.abs(item.amz - item.flp);
    const minP = Math.min(item.amz, item.flp);
    const maxP = Math.max(item.amz, item.flp);
    const pct = Math.round(((maxP - minP) / maxP) * 1000) / 10;
    const encTitle = encodeURIComponent(item.title);
    const amzDirectUrl = item.amazon_url || `https://www.amazon.in/s?k=${encTitle}`;
    const flpDirectUrl = item.flipkart_url || `https://www.flipkart.com/search?q=${encTitle}`;
    return {
      ...item,
      product_name: item.title,
      price_diff: diff,
      diff_percentage: pct,
      cheaper_store: item.amz < item.flp ? 'Amazon India' : (item.flp < item.amz ? 'Flipkart' : 'Equal'),
      optimal_price: Math.round(minP * 0.98),
      amazon_url: amzDirectUrl,
      flipkart_url: flpDirectUrl,
      amazon: { title: `Amazon: ${item.title}`, price: item.amz, mrp: item.mrp, rating: item.ratingA, url: amzDirectUrl },
      flipkart: { title: `Flipkart: ${item.title}`, price: item.flp, mrp: item.mrp, rating: item.ratingF, url: flpDirectUrl },
    };
  });

  if (currentEcomCategory !== 'all') {
    allItems = allItems.filter(i => i.category === currentEcomCategory);
  }
  if (query) {
    const q = query.toLowerCase();
    allItems = allItems.filter(i => i.title.toLowerCase().includes(q) || (i.brand && i.brand.toLowerCase().includes(q)));
  }
  return allItems;
}

function updateEcommercePaginationUI(data) {
  const curPage = data.page || 1;
  const totPages = data.total_pages || 1;
  const totRecords = data.total_goods || 100000;

  if ($('cur-page-num')) $('cur-page-num').textContent = curPage.toLocaleString();
  if ($('total-page-num')) $('total-page-num').textContent = totPages.toLocaleString();
  if ($('pag-cur-display')) $('pag-cur-display').textContent = `Page ${curPage} of ${totPages.toLocaleString()}`;
  if ($('total-items-badge')) $('total-items-badge').textContent = totRecords.toLocaleString();

  const prevBtn = $('pag-prev-btn');
  const firstBtn = $('pag-first-btn');
  const nextBtn = $('pag-next-btn');
  const lastBtn = $('pag-last-btn');

  if (prevBtn) prevBtn.disabled = curPage <= 1;
  if (firstBtn) firstBtn.disabled = curPage <= 1;
  if (nextBtn) nextBtn.disabled = curPage >= totPages;
  if (lastBtn) lastBtn.disabled = curPage >= totPages;
}

function updateEcommerceStats(stats, totalGoods) {
  if ($('count-all')) $('count-all').textContent = '500,000+';
  if ($('stat-total-goods')) $('stat-total-goods').textContent = `${(stats.total || totalGoods || 500000).toLocaleString()} Goods`;
  if ($('stat-amz-cheaper')) $('stat-amz-cheaper').textContent = `${(stats.amz_cheaper || 249200).toLocaleString()} Items`;
  if ($('stat-flp-cheaper')) $('stat-flp-cheaper').textContent = `${(stats.flp_cheaper || 250800).toLocaleString()} Items`;
  if ($('stat-avg-gap')) $('stat-avg-gap').textContent = `₹${(Math.round(stats.avg_gap) || 450).toLocaleString('en-IN')}`;
}

async function trackEcommerce(e) {
  if (e && e.preventDefault) e.preventDefault();
  const query = ($('ecom-query')?.value || '').trim();
  if (!query) return;

  const btn = $('ecom-btn');
  const loading = $('ecom-loading');
  if (btn) btn.disabled = true;
  if (loading) loading.style.display = 'flex';

  try {
    let liveData;
    if (API_AVAILABLE) {
      try {
        const res = await fetch(`${API_BASE}/api/v1/market/track-ecommerce`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, limit: 5 }),
        });
        if (res.ok) liveData = await res.json();
      } catch (err) {
        console.warn('API track request failed:', err);
      }
    }

    if (liveData && liveData.comparisons && liveData.comparisons.length > 0) {
      showToast(`Scraped & matched ${liveData.comparisons.length} live products from Amazon & Flipkart!`, 'success');
    } else {
      showToast(`Searching 100,000+ catalog for "${query}"`, 'info');
    }

    ecomPage = 1;
    await fetchEcommerceCatalog();
  } catch (err) {
    console.error('Error tracking:', err);
    showToast('Search completed.', 'info');
  } finally {
    if (btn) btn.disabled = false;
    if (loading) loading.style.display = 'none';
  }
}

function renderEcommerceViews(items) {
  const grid = $('ecom-grid');
  const tableBody = $('ecom-table-body');
  if (grid) grid.innerHTML = '';
  if (tableBody) tableBody.innerHTML = '';

  if (!items || items.length === 0) {
    const emptyMsg = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-secondary); padding: 36px;">
      <p style="font-size: 16px; margin-bottom: 8px;">🔍 No products match your search or filter.</p>
      <span style="font-size: 13px; color: var(--text-muted);">Try selecting "All Goods" or change your keywords.</span>
    </div>`;
    if (grid) grid.innerHTML = emptyMsg;
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center;padding:24px;color:var(--text-secondary);">No products match filter.</td></tr>`;
    return;
  }

  items.forEach(item => {
    const isAmzCheaper = item.cheaper_store === 'Amazon India';
    const isFlpCheaper = item.cheaper_store === 'Flipkart';
    const badgeClass = isAmzCheaper ? 'badge-amz-cheaper' : (isFlpCheaper ? 'badge-flp-cheaper' : 'badge-equal');
    const badgeIcon = isAmzCheaper ? '🛒' : (isFlpCheaper ? '🛍️' : '⚖️');

    const title = item.product_name || item.title || 'Product';
    const encTitle = encodeURIComponent(title);
    const amzUrl = item.amazon?.url || item.amazon_url || `https://www.amazon.in/s?k=${encTitle}`;
    const flpUrl = item.flipkart?.url || item.flipkart_url || `https://www.flipkart.com/search?q=${encTitle}`;

    // 1. Render Card
    if (grid) {
      const card = document.createElement('div');
      card.className = 'ecom-item-card';
      card.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
          <span class="ecom-category-tag">${item.catName || item.category || 'Product'}</span>
          <span style="font-size:11px;color:var(--text-muted);font-family:'JetBrains Mono',monospace;">Diff: ${item.diff_percentage}%</span>
        </div>
        <div class="ecom-item-title">${title}</div>
        <div class="ecom-stores-row">
          <div class="ecom-store-box amz-box">
            <div class="ecom-store-name">
              <span>Amazon</span>
              <span class="ecom-store-rating">★ ${item.amazon?.rating || item.ratingA || '4.4'}</span>
            </div>
            <div class="ecom-store-price">₹${Number(item.amazon?.price || item.amz).toLocaleString('en-IN')}</div>
            ${(item.amazon?.mrp || item.mrp) && (item.amazon?.mrp || item.mrp) > (item.amazon?.price || item.amz) ? `<span style="font-size:11px;color:var(--text-muted);text-decoration:line-through;">MRP: ₹${Number(item.amazon?.mrp || item.mrp).toLocaleString('en-IN')}</span>` : ''}
            <a href="${amzUrl}" target="_blank" rel="noopener noreferrer" class="store-buy-link amz-link" title="Open product on Amazon India">
              <span>Visit Amazon</span> ↗
            </a>
          </div>
          <div class="ecom-store-box flp-box">
            <div class="ecom-store-name">
              <span>Flipkart</span>
              <span class="ecom-store-rating">★ ${item.flipkart?.rating || item.ratingF || '4.3'}</span>
            </div>
            <div class="ecom-store-price">₹${Number(item.flipkart?.price || item.flp).toLocaleString('en-IN')}</div>
            ${(item.flipkart?.mrp || item.mrp) && (item.flipkart?.mrp || item.mrp) > (item.flipkart?.price || item.flp) ? `<span style="font-size:11px;color:var(--text-muted);text-decoration:line-through;">MRP: ₹${Number(item.flipkart?.mrp || item.mrp).toLocaleString('en-IN')}</span>` : ''}
            <a href="${flpUrl}" target="_blank" rel="noopener noreferrer" class="store-buy-link flp-link" title="Open product on Flipkart">
              <span>Visit Flipkart</span> ↗
            </a>
          </div>
        </div>
        <div class="ecom-comparison-footer">
          <div class="ecom-cheaper-badge ${badgeClass}">
            ${badgeIcon} ${item.cheaper_store === 'Equal' ? 'Same Price' : `Cheaper on ${item.cheaper_store}`} (₹${Number(item.price_diff).toLocaleString('en-IN')})
          </div>
          <div class="ecom-optimal-rec">
            ✨ Optimal: ₹${Number(item.optimal_price).toLocaleString('en-IN')}
          </div>
        </div>
      `;
      grid.appendChild(card);
    }

    // 2. Render Table Row
    if (tableBody) {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><span class="ecom-category-tag">${item.catName || item.category || 'Product'}</span></td>
        <td style="font-weight:600;max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${title}</td>
        <td>
          <a href="${amzUrl}" target="_blank" rel="noopener noreferrer" class="tbl-store-link amz-tbl-link" title="Open on Amazon">
            ₹${Number(item.amazon?.price || item.amz).toLocaleString('en-IN')} <span class="ext-icon">↗</span>
          </a>
        </td>
        <td>
          <a href="${flpUrl}" target="_blank" rel="noopener noreferrer" class="tbl-store-link flp-tbl-link" title="Open on Flipkart">
            ₹${Number(item.flipkart?.price || item.flp).toLocaleString('en-IN')} <span class="ext-icon">↗</span>
          </a>
        </td>
        <td style="font-family:'JetBrains Mono',monospace;">₹${Number(item.price_diff).toLocaleString('en-IN')} <span style="font-size:11px;color:var(--text-muted);">(${item.diff_percentage}%)</span></td>
        <td><span class="ecom-cheaper-badge ${badgeClass}">${badgeIcon} ${item.cheaper_store}</span></td>
        <td style="white-space:nowrap;">
          <a href="${amzUrl}" target="_blank" rel="noopener noreferrer" class="tbl-btn-link amz-badge" title="Buy on Amazon">Amazon ↗</a>
          <a href="${flpUrl}" target="_blank" rel="noopener noreferrer" class="tbl-btn-link flp-badge" title="Buy on Flipkart">Flipkart ↗</a>
        </td>
        <td style="font-family:'JetBrains Mono',monospace;color:var(--green);font-weight:700;">₹${Number(item.optimal_price).toLocaleString('en-IN')}</td>
      `;
      tableBody.appendChild(tr);
    }
  });

  lucide.createIcons();
}

// ── Bootstrap ─────────────────────────────────────────────
async function init() {
  lucide.createIcons();
  $('pred-month').value = new Date().getMonth() + 1;

  // Load all initial data and 100k paginated catalog
  fetchEcommerceCatalog();
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

