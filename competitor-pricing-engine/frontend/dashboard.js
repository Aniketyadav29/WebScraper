/**
 * dashboard.js
 * =============
 * Competitor Intelligence & Dynamic Pricing Engine — Frontend Logic
 *
 * Responsibilities:
 *  - Connect to FastAPI backend and fetch live market data
 *  - Render Chart.js visualizations (bar, donut, line charts)
 *  - Populate KPI cards with real market stats
 *  - Handle AI price prediction form submission
 *  - Live-filter the competitor price table
 *  - Auto-refresh every 60 seconds
 *
 * Author : Aniket Yadav | BBD
 * Version: 1.0.0
 */

// ── Config ───────────────────────────────────────────────
const API_BASE = 'http://localhost:8000';
const REFRESH_INTERVAL_MS = 60_000;

// Chart.js global defaults — dark theme
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family = "'Inter', sans-serif";

// ── State ─────────────────────────────────────────────────
let allTableData   = [];
let barChart       = null;
let donutChart     = null;
let historyChart   = null;
let refreshTimer   = null;

// ── DOM Helpers ───────────────────────────────────────────
const $  = (id) => document.getElementById(id);
const el = (sel) => document.querySelector(sel);

// ── Toast Notification ────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
  const toast = $('toast');
  toast.textContent = message;
  toast.className = `toast ${type} show`;
  setTimeout(() => { toast.className = 'toast'; }, duration);
}

// ── Live Clock ────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  $('live-clock').textContent = now.toLocaleTimeString('en-GB', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
}
setInterval(updateClock, 1000);
updateClock();

// ── API Status ────────────────────────────────────────────
async function checkApiHealth() {
  const dot  = $('api-status-dot');
  const text = $('api-status-text');
  try {
    const res  = await fetch(`${API_BASE}/health`);
    const data = await res.json();
    dot.className  = 'status-dot online';
    text.textContent = `API Online · Model ${data.model_loaded ? 'Ready' : 'Offline'}`;
    return true;
  } catch {
    dot.className  = 'status-dot offline';
    text.textContent = 'API Offline';
    return false;
  }
}

// ── Competitor Bar Chart ──────────────────────────────────
function renderBarChart(competitors) {
  const ctx = $('competitorBarChart').getContext('2d');
  const labels = competitors.map(c => c.competitor.replace('Competitor', 'Comp '));
  const avgs   = competitors.map(c => c.avg_price_gbp);
  const mins   = competitors.map(c => c.min_price_gbp);
  const maxs   = competitors.map(c => c.max_price_gbp);

  const COLORS = ['#3b82f6', '#10b981', '#8b5cf6'];
  const GLOWS  = ['rgba(59,130,246,0.2)', 'rgba(16,185,129,0.2)', 'rgba(139,92,246,0.2)'];

  if (barChart) barChart.destroy();

  barChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: 'Avg Price (GBP)',
          data: avgs,
          backgroundColor: COLORS.map((c, i) => GLOWS[i]),
          borderColor: COLORS,
          borderWidth: 2,
          borderRadius: 8,
          borderSkipped: false,
        },
        {
          label: 'Min Price',
          data: mins,
          backgroundColor: 'transparent',
          borderColor: COLORS.map(c => c + '66'),
          borderWidth: 1,
          borderRadius: 6,
          borderSkipped: false,
          type: 'bar',
        },
        {
          label: 'Max Price',
          data: maxs,
          backgroundColor: 'transparent',
          borderColor: COLORS.map(c => c + '44'),
          borderWidth: 1,
          borderDash: [4, 4],
          borderRadius: 6,
          borderSkipped: false,
          type: 'bar',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { boxWidth: 12, padding: 16, font: { size: 11 } },
        },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,0.95)',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: GBP ${ctx.parsed.y.toFixed(2)}`,
          },
        },
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { font: { size: 12, weight: '600' } },
        },
        y: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            callback: v => `£${v}`,
            font: { size: 11 },
          },
        },
      },
    },
  });
}

// ── Stock Donut Chart ─────────────────────────────────────
function renderDonutChart(competitors) {
  const ctx = $('stockDonutChart').getContext('2d');

  const totalProducts = competitors.reduce((s, c) => s + c.product_count, 0);
  const inStockCount  = Math.round(
    competitors.reduce((s, c) => s + (c.product_count * c.in_stock_pct / 100), 0)
  );
  const outStockCount = totalProducts - inStockCount;

  if (donutChart) donutChart.destroy();

  donutChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: ['In Stock', 'Out of Stock'],
      datasets: [{
        data: [inStockCount, outStockCount],
        backgroundColor: ['rgba(16,185,129,0.25)', 'rgba(239,68,68,0.2)'],
        borderColor:     ['#10b981', '#ef4444'],
        borderWidth: 2,
        hoverOffset: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '72%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15,23,42,0.95)',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          padding: 12,
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} items`,
          },
        },
      },
    },
  });

  // Custom legend
  const legend = $('donut-legend');
  const pct = ((inStockCount / totalProducts) * 100).toFixed(1);
  legend.innerHTML = `
    <div class="legend-item">
      <div class="legend-dot" style="background:#10b981"></div>
      In Stock (${pct}%)
    </div>
    <div class="legend-item">
      <div class="legend-dot" style="background:#ef4444"></div>
      Out of Stock (${(100 - pct).toFixed(1)}%)
    </div>`;
}

// ── Price History Line Chart ──────────────────────────────
async function loadPriceHistory() {
  const title = $('product-select').value;
  if (!title) return;

  try {
    const encoded = encodeURIComponent(title);
    const res  = await fetch(`${API_BASE}/api/v1/market/price-history/${encoded}`);
    const data = await res.json();

    if (!data.records || !data.records.length) {
      showToast('No price history found for this product.', 'info');
      return;
    }

    const ctx = $('priceHistoryChart').getContext('2d');

    // Group by competitor
    const byComp = {};
    for (const rec of data.records) {
      if (!byComp[rec.competitor]) byComp[rec.competitor] = [];
      byComp[rec.competitor].push({
        x: new Date(rec.scraped_at).getTime(),
        y: rec.price_gbp,
      });
    }

    const PALETTE = { Competitora: '#3b82f6', Competitorb: '#10b981', Competitorc: '#8b5cf6' };
    const datasets = Object.entries(byComp).map(([comp, pts]) => ({
      label: comp.replace('Competitor', 'Competitor ').toUpperCase(),
      data: pts,
      borderColor: PALETTE[comp] || '#94a3b8',
      backgroundColor: (PALETTE[comp] || '#94a3b8') + '15',
      borderWidth: 2,
      pointRadius: 3,
      pointHoverRadius: 6,
      fill: true,
      tension: 0.35,
    }));

    if (historyChart) historyChart.destroy();

    historyChart = new Chart(ctx, {
      type: 'line',
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            position: 'top',
            labels: { boxWidth: 12, padding: 16, font: { size: 11 } },
          },
          tooltip: {
            backgroundColor: 'rgba(15,23,42,0.95)',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
            padding: 12,
            callbacks: {
              label: ctx => ` ${ctx.dataset.label}: £${ctx.parsed.y.toFixed(2)}`,
            },
          },
        },
        scales: {
          x: {
            type: 'time',
            time: { unit: 'hour', displayFormats: { hour: 'HH:mm' } },
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { font: { size: 10 }, maxTicksLimit: 8 },
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { callback: v => `£${v}`, font: { size: 11 } },
          },
        },
      },
    });
  } catch (err) {
    showToast('Failed to load price history.', 'error');
    console.error(err);
  }
}

// ── Product Dropdown ──────────────────────────────────────
async function loadProducts() {
  try {
    const res  = await fetch(`${API_BASE}/api/v1/market/products?page_size=100`);
    const data = await res.json();
    const sel  = $('product-select');
    sel.innerHTML = '<option value="">-- Select a product --</option>';
    for (const title of data.products) {
      const opt = document.createElement('option');
      opt.value = title;
      opt.textContent = title.length > 40 ? title.slice(0, 40) + '…' : title;
      sel.appendChild(opt);
    }
  } catch (err) {
    console.error('Failed to load products:', err);
  }
}

// ── Competitor Price Table ────────────────────────────────
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
  const compKey = (c) => c.toLowerCase().replace(/\s/g, '');

  tbody.innerHTML = filtered.map(row => {
    const compClass  = COMP_CLASS[compKey(row.competitor)] || 'comp-a';
    const compLabel  = row.competitor.replace('Competitor', 'Comp ');
    const stockClass = row.in_stock ? 'stock-in' : 'stock-out';
    const stockLabel = row.in_stock ? 'In Stock'  : 'Out of Stock';
    const stars      = '★'.repeat(Math.round(row.rating)) + '☆'.repeat(5 - Math.round(row.rating));
    const scrapedAt  = row.scraped_at
      ? new Date(row.scraped_at).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })
      : '--';

    return `
      <tr>
        <td class="td-title" title="${row.title}">${row.title}</td>
        <td><span class="comp-badge ${compClass}">${compLabel}</span></td>
        <td class="td-price">£${row.price_gbp.toFixed(2)}</td>
        <td class="td-price-usd">$${row.price_usd.toFixed(2)}</td>
        <td><span class="rating-stars" title="${row.rating} stars">${stars}</span></td>
        <td>
          <span class="stock-badge ${stockClass}">
            <span class="stock-dot"></span>${stockLabel}
          </span>
        </td>
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
  const el   = $(id);
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
  setTimeout(() => {
    el.textContent = value;
    el.style.transition = 'opacity 0.4s ease';
    el.style.opacity = '1';
  }, 100);
}

// ── Model Info KPI ────────────────────────────────────────
async function loadModelInfo() {
  try {
    const res  = await fetch(`${API_BASE}/api/v1/pricing/model-info`);
    const data = await res.json();
    const r2   = data.metrics?.r2 ?? 0;
    animateValue('kpi-confidence', `${(r2 * 100).toFixed(2)}%`);
  } catch {
    $('kpi-confidence').textContent = 'N/A';
  }
}

// ── AI Price Prediction ───────────────────────────────────
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

  try {
    const res  = await fetch(`${API_BASE}/api/v1/pricing/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    // Show result panel
    const result = $('prediction-result');
    result.style.display = 'block';

    $('res-current').textContent = `£${data.current_price.toFixed(2)}`;
    $('res-optimal').textContent = `£${data.optimal_price.toFixed(2)}`;

    const gap     = data.price_gap_pct;
    const gapEl   = $('res-gap');
    const isDown  = data.optimal_price < data.current_price;
    gapEl.textContent = `${gap > 0 ? '+' : ''}${gap.toFixed(2)}% vs competitor avg`;
    gapEl.style.color = isDown ? 'var(--green)' : 'var(--orange)';

    $('res-recommendation').textContent = data.recommendation;
    $('res-revenue').textContent = data.potential_revenue_change;
    $('confidence-badge').textContent   = `${(data.confidence * 100).toFixed(1)}% Confidence`;

    // Re-initialise lucide icons in result panel
    lucide.createIcons();
    showToast('Price prediction complete!', 'success');
  } catch (err) {
    showToast('Prediction failed. Is the API running?', 'error');
    console.error(err);
  } finally {
    btn.classList.remove('loading');
    btn.querySelector('span').textContent = 'Predict Optimal Price';
  }
}

// ── Full Data Refresh ─────────────────────────────────────
async function refreshAll() {
  const btn = $('refresh-btn');
  btn.classList.add('spinning');

  try {
    const [healthOk, summaryRes, competitorsRes] = await Promise.all([
      checkApiHealth(),
      fetch(`${API_BASE}/api/v1/market/summary`),
      fetch(`${API_BASE}/api/v1/market/competitors?limit=150`),
    ]);

    if (!healthOk) {
      showToast('API is offline. Displaying cached data.', 'error');
      return;
    }

    const summary     = await summaryRes.json();
    const competitors = await competitorsRes.json();

    updateKPIs(summary);
    renderBarChart(summary.competitors);
    renderDonutChart(summary.competitors);
    renderTable(competitors);

    showToast('Dashboard updated!', 'success', 2000);
  } catch (err) {
    showToast('Failed to refresh data.', 'error');
    console.error(err);
  } finally {
    btn.classList.remove('spinning');
  }
}

// ── Bootstrap ─────────────────────────────────────────────
async function init() {
  // Initialise Lucide icons
  lucide.createIcons();

  // Set current month in form
  $('pred-month').value = new Date().getMonth() + 1;

  // Load all data
  await Promise.all([
    refreshAll(),
    loadProducts(),
    loadModelInfo(),
  ]);

  // Auto-refresh
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshAll, REFRESH_INTERVAL_MS);

  // Hide loader
  setTimeout(() => {
    $('loader').classList.add('hidden');
  }, 600);
}

// Wait for Chart.js adapters (time scale needs date-fns or built-in)
// Using built-in time adapter via chartjs-adapter-date-fns from CDN
(function loadTimeAdapter() {
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js';
  script.onload = () => init();
  script.onerror = () => init(); // Fallback: init without time adapter
  document.head.appendChild(script);
})();
