/* ============================================
   QA COMMAND CENTER - Dashboard Logic
   ============================================ */

(function () {
  'use strict';

  // ---- State ----
  let wsConnected = false;
  let pollInterval = null;
  let costChart = null;

  // ---- Bootstrap ----
  document.addEventListener('DOMContentLoaded', () => {
    startTimestampClock();
    refreshAllData();
    connectWebSocket();
  });

  // ============================================
  // Timestamp clock
  // ============================================
  function startTimestampClock() {
    const el = document.getElementById('timestamp');
    function tick() {
      const now = new Date();
      el.textContent = now.toISOString().replace('T', '  ').split('.')[0] + ' UTC';
    }
    tick();
    setInterval(tick, 1000);
  }

  // ============================================
  // Data fetching
  // ============================================
  function refreshAllData() {
    fetchHealth();
    fetchEvalSummary();
    fetchRunHistory();
    fetchAuditSummary();
  }

  async function fetchHealth() {
    try {
      const res = await fetch('/api/health/latest');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      renderHealthGauge(data.health_score ?? data.score ?? 0, data.status ?? 'unknown');
      updateHealthMeta(data);
      if (data.domains) {
        renderDomainCards(data.domains);
      }
    } catch (err) {
      console.warn('Health fetch failed:', err);
      renderHealthGauge(0, 'unknown');
      document.getElementById('domain-grid').innerHTML =
        '<div class="no-data">No health data available</div>';
    }
  }

  async function fetchEvalSummary() {
    try {
      const res = await fetch('/api/eval/summary');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      renderEvalCards(data);
    } catch (err) {
      console.warn('Eval fetch failed:', err);
      document.getElementById('eval-grid').innerHTML =
        '<div class="no-data">No evaluation data available</div>';
    }
  }

  async function fetchRunHistory() {
    try {
      const res = await fetch('/api/health/history');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      const history = Array.isArray(data) ? data : (data.history ?? []);
      renderRunHistory(history);
    } catch (err) {
      console.warn('History fetch failed:', err);
      document.getElementById('run-table-body').innerHTML =
        '<tr><td colspan="6" class="no-data">No run history available</td></tr>';
    }
  }

  async function fetchAuditSummary() {
    try {
      const res = await fetch('/api/audit/summary');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      renderCostSummary(data);
      renderCostChart(data);
    } catch (err) {
      console.warn('Audit fetch failed:', err);
      document.getElementById('total-cost').textContent = '--';
      document.getElementById('total-tokens').textContent = '--';
      document.getElementById('total-api-calls').textContent = '--';
    }
  }

  // ============================================
  // Health Gauge (SVG)
  // ============================================
  function renderHealthGauge(score, status) {
    const arc = document.getElementById('gauge-arc');
    const scoreEl = document.getElementById('gauge-score');
    const statusEl = document.getElementById('gauge-status');

    const circumference = 2 * Math.PI * 85; // ~534
    const normalizedScore = Math.max(0, Math.min(100, score));
    const offset = circumference - (normalizedScore / 100) * circumference;

    // Color based on status
    const statusLower = (status || '').toLowerCase();
    let color = 'var(--neon-cyan)';
    let statusClass = 'status-healthy';
    if (statusLower === 'degraded') {
      color = 'var(--neon-amber)';
      statusClass = 'status-degraded';
    } else if (statusLower === 'critical') {
      color = 'var(--neon-red)';
      statusClass = 'status-critical';
    }

    arc.style.stroke = color;
    statusEl.style.fill = color;

    // Animate arc
    requestAnimationFrame(() => {
      arc.setAttribute('stroke-dashoffset', offset);
    });

    // Animate score text
    animateCountUp(scoreEl, normalizedScore);
    statusEl.textContent = (status || 'UNKNOWN').toUpperCase();
  }

  function updateHealthMeta(data) {
    const totalTests = data.total_tests ?? data.total ?? '--';
    const passed = data.passed ?? data.tests_passed ?? '--';
    const failed = data.failed ?? data.tests_failed ?? '--';

    document.getElementById('total-tests').textContent = totalTests;
    document.getElementById('total-passed').textContent = passed;
    document.getElementById('total-failed').textContent = failed;
  }

  // ============================================
  // Domain Cards
  // ============================================
  function renderDomainCards(domains) {
    const grid = document.getElementById('domain-grid');

    if (!domains || domains.length === 0) {
      grid.innerHTML = '<div class="no-data">No domain data available</div>';
      return;
    }

    // Sort: critical first, then by score ascending
    const sorted = [...domains].sort((a, b) => {
      if (a.is_critical && !b.is_critical) return -1;
      if (!a.is_critical && b.is_critical) return 1;
      const scoreA = a.score ?? a.health_score ?? 100;
      const scoreB = b.score ?? b.health_score ?? 100;
      return scoreA - scoreB;
    });

    grid.innerHTML = sorted.map(domain => {
      const name = domain.name || domain.domain || 'Unknown';
      const score = domain.score ?? domain.health_score ?? 0;
      const passed = domain.passed ?? domain.tests_passed ?? 0;
      const total = domain.total ?? domain.total_tests ?? 0;
      const status = (domain.status || classifyScore(score)).toLowerCase();
      const isCritical = domain.is_critical ?? false;

      const cardClass = status === 'healthy' ? 'status-healthy-card'
        : status === 'degraded' ? 'status-degraded-card'
        : 'status-critical-card';

      const badgeClass = status === 'healthy' ? 'badge-healthy'
        : status === 'degraded' ? 'badge-degraded'
        : 'badge-critical';

      const scoreClass = status === 'healthy' ? 'status-healthy'
        : status === 'degraded' ? 'status-degraded'
        : 'status-critical';

      return `
        <div class="domain-card ${cardClass}" data-domain="${name}">
          <div class="domain-name">
            ${isCritical ? '<span class="critical-badge">&#9733;</span>' : ''}
            ${escapeHtml(name)}
          </div>
          <div class="domain-stats">
            <span class="domain-score ${scoreClass}">${score.toFixed(1)}%</span>
            <span class="domain-ratio">${passed}/${total}</span>
          </div>
          <span class="domain-status-badge ${badgeClass}">${status.toUpperCase()}</span>
        </div>
      `;
    }).join('');
  }

  // ============================================
  // Agent Eval Cards
  // ============================================
  function renderEvalCards(evalSummary) {
    const grid = document.getElementById('eval-grid');
    const agents = ['triage', 'planner', 'generator', 'healer'];

    const cards = agents.map(agent => {
      const agentData = evalSummary[agent] ?? evalSummary[agent + '_agent'] ?? null;

      if (!agentData) {
        return `
          <div class="eval-card" data-agent="${agent}">
            <div class="eval-agent-name">${agent}</div>
            <div class="eval-score score-pass">--</div>
            <span class="eval-badge badge-pass">NO DATA</span>
          </div>
        `;
      }

      const score = agentData.score ?? agentData.accuracy ?? 0;
      const pass = agentData.pass ?? (score >= 70);
      const scoreClass = pass ? 'score-pass' : 'score-fail';
      const badgeClass = pass ? 'badge-pass' : 'badge-fail';
      const badgeText = pass ? 'PASS' : 'FAIL';

      return `
        <div class="eval-card" data-agent="${agent}">
          <div class="eval-agent-name">${agent}</div>
          <div class="eval-score ${scoreClass}">${typeof score === 'number' ? score.toFixed(1) + '%' : score}</div>
          <span class="eval-badge ${badgeClass}">${badgeText}</span>
        </div>
      `;
    });

    grid.innerHTML = cards.join('');
  }

  // ============================================
  // Run History Table
  // ============================================
  function renderRunHistory(history) {
    const tbody = document.getElementById('run-table-body');

    if (!history || history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="no-data">No run history available</td></tr>';
      return;
    }

    // Most recent first
    const sorted = [...history].sort((a, b) => {
      const tA = new Date(a.timestamp || a.created_at || 0);
      const tB = new Date(b.timestamp || b.created_at || 0);
      return tB - tA;
    });

    tbody.innerHTML = sorted.map(run => {
      const ts = run.timestamp || run.created_at || '--';
      const total = run.total_tests ?? run.total ?? '--';
      const passed = run.passed ?? run.tests_passed ?? '--';
      const failed = run.failed ?? run.tests_failed ?? '--';
      const health = run.health_score ?? run.score ?? '--';
      const status = (run.status || classifyScore(health)).toLowerCase();

      const rowClass = status === 'healthy' ? 'row-healthy'
        : status === 'degraded' ? 'row-degraded'
        : 'row-critical';

      const statusClass = status === 'healthy' ? 'status-healthy'
        : status === 'degraded' ? 'status-degraded'
        : 'status-critical';

      const badgeClass = status === 'healthy' ? 'badge-healthy'
        : status === 'degraded' ? 'badge-degraded'
        : 'badge-critical';

      const formattedTs = formatTimestamp(ts);
      const healthDisplay = typeof health === 'number' ? health.toFixed(1) + '%' : health;

      return `
        <tr class="${rowClass}">
          <td>${formattedTs}</td>
          <td>${total}</td>
          <td class="status-healthy">${passed}</td>
          <td class="status-critical">${failed}</td>
          <td class="${statusClass}">${healthDisplay}</td>
          <td><span class="table-status-badge domain-status-badge ${badgeClass}">${status.toUpperCase()}</span></td>
        </tr>
      `;
    }).join('');
  }

  // ============================================
  // Cost / Audit Summary
  // ============================================
  function renderCostSummary(data) {
    const totalCost = data.total_cost ?? data.cost ?? 0;
    const totalTokens = data.total_tokens ?? data.tokens ?? 0;
    const apiCalls = data.total_api_calls ?? data.api_calls ?? 0;

    document.getElementById('total-cost').textContent = '$' + Number(totalCost).toFixed(4);
    document.getElementById('total-tokens').textContent = formatNumber(totalTokens);
    document.getElementById('total-api-calls').textContent = formatNumber(apiCalls);
  }

  function renderCostChart(data) {
    const canvas = document.getElementById('cost-chart');
    const ctx = canvas.getContext('2d');

    const breakdown = data.breakdown ?? data.history ?? data.by_run ?? [];

    if (costChart) {
      costChart.destroy();
    }

    if (!breakdown || breakdown.length === 0) {
      // Render a placeholder chart with no data
      costChart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['No Data'],
          datasets: [{
            label: 'Cost ($)',
            data: [0],
            backgroundColor: 'rgba(0, 255, 200, 0.2)',
            borderColor: 'rgba(0, 255, 200, 0.6)',
            borderWidth: 1
          }]
        },
        options: chartOptions('Cost per Run')
      });
      return;
    }

    const labels = breakdown.map((item, i) => item.label ?? item.run_id ?? `Run ${i + 1}`);
    const costs = breakdown.map(item => item.cost ?? item.total_cost ?? 0);
    const tokens = breakdown.map(item => item.tokens ?? item.total_tokens ?? 0);

    costChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Cost ($)',
            data: costs,
            backgroundColor: 'rgba(0, 255, 200, 0.2)',
            borderColor: 'rgba(0, 255, 200, 0.6)',
            borderWidth: 1,
            yAxisID: 'y'
          },
          {
            label: 'Tokens',
            data: tokens,
            type: 'line',
            borderColor: 'rgba(255, 184, 0, 0.8)',
            backgroundColor: 'rgba(255, 184, 0, 0.1)',
            pointBackgroundColor: 'rgba(255, 184, 0, 1)',
            pointRadius: 3,
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            yAxisID: 'y1'
          }
        ]
      },
      options: chartOptions('Cost & Token Usage')
    });
  }

  function chartOptions(title) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: '#7a7a8a',
            font: { family: 'JetBrains Mono', size: 11 }
          }
        },
        title: {
          display: false
        }
      },
      scales: {
        x: {
          ticks: { color: '#7a7a8a', font: { family: 'JetBrains Mono', size: 10 } },
          grid: { color: 'rgba(255,255,255,0.03)' }
        },
        y: {
          type: 'linear',
          position: 'left',
          ticks: { color: '#00ffc8', font: { family: 'JetBrains Mono', size: 10 } },
          grid: { color: 'rgba(0,255,200,0.05)' },
          title: { display: true, text: 'Cost ($)', color: '#00ffc8', font: { family: 'Orbitron', size: 10 } }
        },
        y1: {
          type: 'linear',
          position: 'right',
          ticks: { color: '#ffb800', font: { family: 'JetBrains Mono', size: 10 } },
          grid: { drawOnChartArea: false },
          title: { display: true, text: 'Tokens', color: '#ffb800', font: { family: 'Orbitron', size: 10 } }
        }
      }
    };
  }

  // ============================================
  // WebSocket live updates
  // ============================================
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

    let ws;
    try {
      ws = new WebSocket(wsUrl);
    } catch (err) {
      console.warn('WebSocket connection failed, falling back to polling:', err);
      startPolling();
      return;
    }

    ws.onopen = () => {
      console.log('WebSocket connected');
      wsConnected = true;
      stopPolling();
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.event) {
          case 'test:pass':
            updateDomainCard(data.suite || data.domain, true);
            break;
          case 'test:fail':
            flashDomainRed(data.suite || data.domain);
            break;
          case 'run:end':
            refreshAllData();
            break;
          default:
            break;
        }
      } catch (err) {
        console.warn('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (err) => {
      console.warn('WebSocket error:', err);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting in 3s...');
      wsConnected = false;
      startPolling();
      setTimeout(connectWebSocket, 3000);
    };
  }

  // ============================================
  // Polling fallback
  // ============================================
  function startPolling() {
    if (pollInterval) return;
    pollInterval = setInterval(() => {
      fetchHealth();
    }, 5000);
  }

  function stopPolling() {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  // ============================================
  // Live update helpers
  // ============================================
  function updateDomainCard(domainName, passed) {
    if (!domainName) return;
    const card = document.querySelector(`.domain-card[data-domain="${domainName}"]`);
    if (!card) return;

    if (passed) {
      card.style.boxShadow = '0 0 20px rgba(0, 255, 200, 0.3)';
      setTimeout(() => { card.style.boxShadow = ''; }, 1000);
    }
  }

  function flashDomainRed(domainName) {
    if (!domainName) return;
    const card = document.querySelector(`.domain-card[data-domain="${domainName}"]`);
    if (!card) return;

    card.style.boxShadow = '0 0 25px rgba(255, 0, 60, 0.5)';
    card.style.borderColor = 'rgba(255, 0, 60, 0.6)';
    setTimeout(() => {
      card.style.boxShadow = '';
      card.style.borderColor = '';
    }, 2000);
  }

  // ============================================
  // Count-up animation
  // ============================================
  function animateCountUp(element, target, duration) {
    duration = duration || 1500;
    let start = null;
    const step = (timestamp) => {
      if (!start) start = timestamp;
      const progress = Math.min((timestamp - start) / duration, 1);
      const current = progress * target;
      element.textContent = current.toFixed(1) + '%';
      if (progress < 1) {
        requestAnimationFrame(step);
      }
    };
    requestAnimationFrame(step);
  }

  // ============================================
  // Utilities
  // ============================================
  function classifyScore(score) {
    if (typeof score !== 'number') return 'unknown';
    if (score >= 80) return 'healthy';
    if (score >= 50) return 'degraded';
    return 'critical';
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function formatTimestamp(ts) {
    if (!ts || ts === '--') return '--';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toISOString().replace('T', ' ').split('.')[0];
    } catch {
      return ts;
    }
  }

  function formatNumber(n) {
    if (typeof n !== 'number') return String(n);
    if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

})();
