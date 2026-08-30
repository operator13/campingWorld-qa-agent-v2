/* ============================================
   QA COMMAND CENTER - Dashboard Logic
   ============================================ */

(function () {
  'use strict';

  let wsConnected = false;
  let pollInterval = null;
  let costChart = null;
  let runnerTestCount = 0, runnerPassCount = 0, runnerFailCount = 0;

  document.addEventListener('DOMContentLoaded', () => {
    startTimestampClock();
    refreshAllData();
    connectWebSocket();
    initRunnerControls();
  });

  function startTimestampClock() {
    const el = document.getElementById('timestamp');
    function tick() {
      const now = new Date();
      el.textContent = now.toISOString().replace('T', '  ').split('.')[0] + ' UTC';
    }
    tick();
    setInterval(tick, 1000);
  }

  function refreshAllData() {
    fetchHealth();
    fetchEvalSummary();
    fetchRunHistory();
    fetchAuditSummary();
    syncRunnerStatus();
  }

  function syncRunnerStatus() {
    fetch('/api/tests/status').then(r => r.json()).then(status => {
      const state = status.state || 'idle';
      if (state === 'running' || state === 'healing') {
        setRunnerState(state);
        document.getElementById('runner-log-container').style.display = 'block';
        document.getElementById('btn-run-selected').style.display = 'none';
        document.getElementById('btn-run-all').style.display = 'none';
        document.getElementById('btn-stop').style.display = 'inline-block';
        document.getElementById('btn-clear').disabled = true;
      } else if (state === 'idle' || state === 'complete') {
        // If we were showing RUNNING but server says idle, sync to idle
        const currentStatus = document.getElementById('runner-status')?.textContent;
        if (currentStatus === 'RUNNING' || currentStatus === 'HEALING') {
          setRunnerState(state === 'complete' ? 'complete' : 'idle');
          document.getElementById('btn-run-selected').style.display = 'inline-block';
          document.getElementById('btn-run-all').style.display = 'inline-block';
          document.getElementById('btn-stop').style.display = 'none';
          document.getElementById('btn-clear').disabled = false;
        }
      }
    }).catch(() => {});
  }

  // ============================================
  // Health data
  // ============================================
  async function fetchHealth() {
    try {
      const res = await fetch('/api/health/latest');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      // API returns: overall_score (0-1), overall_status, total_passed, total_failed, total_tests, domains[]
      const score = (data.overall_score ?? 0) * 100;
      const status = data.overall_status ?? 'UNKNOWN';
      renderHealthGauge(score, status);
      document.getElementById('total-tests').textContent = data.total_tests ?? '--';
      document.getElementById('total-passed').textContent = data.total_passed ?? '--';
      document.getElementById('total-failed').textContent = data.total_failed ?? '--';
      if (data.domains) renderDomainCards(data.domains);
    } catch (err) {
      console.warn('Health fetch failed:', err);
      renderHealthGauge(0, 'UNKNOWN');
    }
  }

  async function fetchEvalSummary() {
    try {
      const res = await fetch('/api/eval/summary');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      // API returns: {triage: {score: 0.9, passed: true}, planner: {...}, ...}
      renderEvalCards(data);
    } catch (err) {
      console.warn('Eval fetch failed:', err);
    }
  }

  async function fetchRunHistory() {
    try {
      const res = await fetch('/api/health/history');
      if (!res.ok) throw new Error(res.statusText);
      const history = await res.json();
      renderRunHistory(Array.isArray(history) ? history : []);
    } catch (err) {
      console.warn('History fetch failed:', err);
    }
  }

  async function fetchAuditSummary() {
    try {
      const res = await fetch('/api/audit/summary');
      if (!res.ok) throw new Error(res.statusText);
      const data = await res.json();
      // API returns: total_runs, total_input_tokens, total_output_tokens, total_cost, per_node_avg
      const totalTokens = (data.total_input_tokens ?? 0) + (data.total_output_tokens ?? 0);
      document.getElementById('total-cost').textContent = '$' + (data.total_cost ?? 0).toFixed(4);
      document.getElementById('total-tokens').textContent = formatNumber(totalTokens);
      document.getElementById('total-api-calls').textContent = data.total_runs ?? '--';
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

    const circumference = 2 * Math.PI * 85;
    const normalizedScore = Math.max(0, Math.min(100, score));
    const offset = circumference - (normalizedScore / 100) * circumference;

    const statusLower = (status || '').toLowerCase();
    let color = 'var(--neon-cyan)';
    if (statusLower === 'degraded') color = 'var(--neon-amber)';
    else if (statusLower === 'critical' || statusLower === 'unknown') color = 'var(--neon-red)';

    arc.style.stroke = color;
    statusEl.style.fill = color;

    requestAnimationFrame(() => {
      arc.setAttribute('stroke-dashoffset', offset);
    });

    animateCountUp(scoreEl, normalizedScore);
    statusEl.textContent = status.toUpperCase();
  }

  // ============================================
  // Domain Cards
  // ============================================
  function renderDomainCards(domains) {
    const grid = document.getElementById('domain-grid');
    if (!domains || domains.length === 0) {
      grid.innerHTML = '<div class="no-data">No domain data</div>';
      return;
    }

    // Sort: critical first, then by score ascending
    const sorted = [...domains].sort((a, b) => {
      if (a.is_critical && !b.is_critical) return -1;
      if (!a.is_critical && b.is_critical) return 1;
      return (a.score ?? 0) - (b.score ?? 0);
    });

    grid.innerHTML = sorted.map(d => {
      const name = d.name || 'Unknown';
      const score = (d.score ?? 0) * 100; // API returns 0-1
      const passed = d.passed ?? 0;
      const total = d.total ?? 0;
      const status = (d.status || 'UNKNOWN').toLowerCase();
      const isCritical = d.is_critical ?? false;

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
        <div class="domain-card ${cardClass}" data-domain="${escapeHtml(name)}">
          <div class="domain-name">
            ${isCritical ? '<span class="critical-badge">&#9733;</span>' : ''}
            ${escapeHtml(name)}
          </div>
          <div class="domain-stats">
            <span class="domain-score ${scoreClass}">${score.toFixed(0)}%</span>
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

    grid.innerHTML = agents.map(agent => {
      const data = evalSummary[agent];
      if (!data || data.score === null) {
        return `
          <div class="eval-card" data-agent="${agent}">
            <div class="eval-agent-name">${agent.toUpperCase()}</div>
            <div class="eval-score">--</div>
            <span class="eval-badge">NO DATA</span>
          </div>
        `;
      }

      const score = (data.score ?? 0) * 100; // API returns 0-1
      const passed = data.passed ?? false;
      const scoreClass = passed ? 'score-pass' : 'score-fail';
      const badgeClass = passed ? 'badge-pass' : 'badge-fail';
      const badgeText = passed ? 'PASS' : 'FAIL';

      const tokens = data.tokens != null ? formatNumber(data.tokens) : '--';
      const cost = data.cost != null ? '$' + data.cost.toFixed(4) : '--';

      return `
        <div class="eval-card" data-agent="${agent}">
          <div class="eval-agent-name">${agent.toUpperCase()}</div>
          <div class="eval-score ${scoreClass}">${score.toFixed(1)}%</div>
          <span class="eval-badge ${badgeClass}">${badgeText}</span>
          <div class="eval-cost-row">
            <span class="eval-cost-item"><span class="eval-cost-label">Tokens</span> <span class="eval-cost-value">${tokens}</span></span>
            <span class="eval-cost-item"><span class="eval-cost-label">Cost</span> <span class="eval-cost-value">${cost}</span></span>
          </div>
        </div>
      `;
    }).join('');
  }

  // ============================================
  // Run History Table
  // ============================================
  function renderRunHistory(history) {
    const tbody = document.getElementById('run-table-body');
    if (!history || history.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="no-data">No run history</td></tr>';
      return;
    }

    // API returns: [{run_id, timestamp, overall_score, overall_status, total_passed, total_failed, total_tests}]
    const sorted = [...history].sort((a, b) => {
      return new Date(b.timestamp || 0) - new Date(a.timestamp || 0);
    });

    tbody.innerHTML = sorted.map(run => {
      const ts = formatTimestamp(run.timestamp);
      const total = run.total_tests ?? '--';
      const passed = run.total_passed ?? '--';
      const failed = run.total_failed ?? '--';
      const health = run.overall_score != null ? (run.overall_score * 100).toFixed(1) + '%' : '--';
      const status = (run.overall_status || 'UNKNOWN').toLowerCase();

      const badgeClass = status === 'healthy' ? 'badge-healthy'
        : status === 'degraded' ? 'badge-degraded'
        : 'badge-critical';
      const statusClass = status === 'healthy' ? 'status-healthy'
        : status === 'degraded' ? 'status-degraded'
        : 'status-critical';

      return `
        <tr>
          <td>${ts}</td>
          <td>${total}</td>
          <td class="status-healthy">${passed}</td>
          <td class="status-critical">${failed}</td>
          <td class="${statusClass}">${health}</td>
          <td><span class="domain-status-badge ${badgeClass}">${status.toUpperCase()}</span></td>
        </tr>
      `;
    }).join('');
  }

  // ============================================
  // Cost Chart
  // ============================================
  function renderCostChart(data) {
    const canvas = document.getElementById('cost-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (costChart) costChart.destroy();

    const runs = data.runs ?? [];
    if (runs.length === 0) {
      costChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: ['No Data'], datasets: [{ label: 'Cost ($)', data: [0], backgroundColor: 'rgba(0,255,200,0.2)', borderColor: 'rgba(0,255,200,0.6)', borderWidth: 1 }] },
        options: chartOptions()
      });
      return;
    }

    const labels = runs.map(r => r.run_id ?? 'run');
    const costs = runs.map(r => r.estimated_cost_usd ?? 0);
    const tokens = runs.map(r => (r.total_input_tokens ?? 0) + (r.total_output_tokens ?? 0));

    costChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Cost ($)', data: costs, backgroundColor: 'rgba(0,255,200,0.2)', borderColor: 'rgba(0,255,200,0.6)', borderWidth: 1, yAxisID: 'y' },
          { label: 'Tokens', data: tokens, type: 'line', borderColor: 'rgba(255,184,0,0.8)', backgroundColor: 'rgba(255,184,0,0.1)', pointBackgroundColor: 'rgba(255,184,0,1)', pointRadius: 3, borderWidth: 2, fill: true, tension: 0.3, yAxisID: 'y1' }
        ]
      },
      options: chartOptions()
    });
  }

  function chartOptions() {
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#7a7a8a', font: { family: 'JetBrains Mono', size: 11 } } } },
      scales: {
        x: { ticks: { color: '#7a7a8a', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
        y: { type: 'linear', position: 'left', ticks: { color: '#00ffc8', font: { family: 'JetBrains Mono', size: 10 } }, grid: { color: 'rgba(0,255,200,0.05)' }, title: { display: true, text: 'Cost ($)', color: '#00ffc8', font: { family: 'Orbitron', size: 10 } } },
        y1: { type: 'linear', position: 'right', ticks: { color: '#ffb800', font: { family: 'JetBrains Mono', size: 10 } }, grid: { drawOnChartArea: false }, title: { display: true, text: 'Tokens', color: '#ffb800', font: { family: 'Orbitron', size: 10 } } }
      }
    };
  }

  // ============================================
  // WebSocket
  // ============================================
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;
    let ws;
    try { ws = new WebSocket(wsUrl); } catch (err) { startPolling(); return; }

    ws.onopen = () => {
      wsConnected = true;
      stopPolling();
      // Sync runner state on connect (in case we joined mid-run)
      fetch('/api/tests/status').then(r => r.json()).then(status => {
        if (status.state === 'running' || status.state === 'healing') {
          setRunnerState(status.state);
          document.getElementById('runner-log-container').style.display = 'block';
          document.getElementById('btn-run-selected').style.display = 'none';
          document.getElementById('btn-run-all').style.display = 'none';
          document.getElementById('btn-stop').style.display = 'inline-block';
          document.getElementById('btn-clear').disabled = true;
        }
      }).catch(() => {});
    };
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.event) {
          case 'test:pass':
            updateDomainCard(data.suite, true);
            break;
          case 'test:fail':
            flashDomainRed(data.suite);
            break;
          case 'run:end':
            refreshAllData();
            break;
          case 'runner:start':
            setRunnerState('running');
            document.getElementById('runner-log').innerHTML = '';
            document.getElementById('runner-log-container').style.display = 'block';
            document.getElementById('btn-run-selected').style.display = 'none';
            document.getElementById('btn-run-all').style.display = 'none';
            document.getElementById('btn-stop').style.display = 'inline-block';
            document.getElementById('btn-clear').disabled = true;
            resetDomainProgress();
            runnerPassCount = 0;
            runnerFailCount = 0;
            break;
          case 'runner:log':
            document.getElementById('runner-log-container').style.display = 'block';
            appendRunnerLog(data.line);
            // Parse per-domain progress from log lines like "  ✓  1 [chromium] › tests_generated/cart.spec.ts:12..."
            const specMatch = data.line.match(/([a-z0-9-]+\.spec\.ts)/);
            if (specMatch && (data.line.includes('✓') || data.line.includes('✘') || data.line.includes('·'))) {
              const spec = specMatch[1];
              const passed = data.line.includes('✓');
              if (passed) { runnerPassCount++; updateDomainProgress(spec, true); }
              else { runnerFailCount++; updateDomainProgress(spec, false); }
              updateProgress();
            }
            break;
          case 'runner:end':
            setRunnerState('complete');
            document.getElementById('btn-run-selected').style.display = 'inline-block';
            document.getElementById('btn-run-all').style.display = 'inline-block';
            document.getElementById('btn-stop').style.display = 'none';
            document.getElementById('btn-clear').disabled = false;
            refreshAllData();
            break;
          case 'runner:healing':
            setRunnerState('healing');
            appendRunnerLog('[HEAL] ' + data.message);
            break;
          case 'runner:healed':
            appendRunnerLog('[HEAL] Done: ' + data.healed + ' healed, ' + data.skipped + ' skipped');
            break;
          case 'runner:clear':
            doClearRunner();
            break;
          default:
            break;
        }
      } catch (err) { console.warn('WS parse error:', err); }
    };
    ws.onclose = () => { wsConnected = false; startPolling(); setTimeout(connectWebSocket, 3000); };
  }

  function startPolling() { if (!pollInterval) pollInterval = setInterval(refreshAllData, 5000); }
  function stopPolling() { if (pollInterval) { clearInterval(pollInterval); pollInterval = null; } }

  function updateDomainCard(name, passed) {
    const card = document.querySelector(`.domain-card[data-domain="${name}"]`);
    if (!card) return;
    card.style.boxShadow = '0 0 20px rgba(0,255,200,0.3)';
    setTimeout(() => { card.style.boxShadow = ''; }, 1000);
  }

  function flashDomainRed(name) {
    const card = document.querySelector(`.domain-card[data-domain="${name}"]`);
    if (!card) return;
    card.style.boxShadow = '0 0 25px rgba(255,0,60,0.5)';
    card.style.borderColor = 'rgba(255,0,60,0.6)';
    setTimeout(() => { card.style.boxShadow = ''; card.style.borderColor = ''; }, 2000);
  }

  // ============================================
  // Utilities
  // ============================================
  function animateCountUp(el, target, duration) {
    duration = duration || 1500;
    let start = null;
    const step = (ts) => {
      if (!start) start = ts;
      const progress = Math.min((ts - start) / duration, 1);
      el.textContent = (progress * target).toFixed(1) + '%';
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function formatTimestamp(ts) {
    if (!ts) return '--';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toISOString().replace('T', ' ').split('.')[0];
    } catch { return ts; }
  }

  function formatNumber(n) {
    if (typeof n !== 'number') return '--';
    if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return String(n);
  }

  // ============================================
  // Test Runner
  // ============================================
  const DOMAINS = [
    {spec: "cart.spec.ts", label: "Cart", tests: 8, critical: true},
    {spec: "checkout.spec.ts", label: "Checkout", tests: 4, critical: true},
    {spec: "sign-in.spec.ts", label: "Sign In", tests: 10, critical: true},
    {spec: "search.spec.ts", label: "Search", tests: 9, critical: false},
    {spec: "product.spec.ts", label: "Product", tests: 9, critical: false},
    {spec: "homepage.spec.ts", label: "Homepage", tests: 13, critical: false},
    {spec: "nav.spec.ts", label: "Nav", tests: 14, critical: false},
    {spec: "register.spec.ts", label: "Register", tests: 6, critical: false},
    {spec: "store-locator.spec.ts", label: "Store Locator", tests: 10, critical: false},
    {spec: "rvs-for-sale.spec.ts", label: "RVs For Sale", tests: 10, critical: false},
    {spec: "rvs-for-sale-detail.spec.ts", label: "RV Detail", tests: 10, critical: false},
    {spec: "good-sam.spec.ts", label: "Good Sam", tests: 6, critical: false},
    {spec: "rv-parts.spec.ts", label: "RV Parts", tests: 5, critical: false},
    {spec: "footer.spec.ts", label: "Footer", tests: 13, critical: false},
  ];

  function initRunnerControls() {
    // Populate domain list rows
    const list = document.getElementById('runner-domain-list');
    if (list) {
      list.innerHTML = DOMAINS.map(d => `
        <div class="domain-row selected" data-spec="${d.spec}" data-tests="${d.tests}">
          <div class="domain-row-left">
            <div class="domain-row-select"></div>
            <span class="domain-row-name">${d.critical ? '<span class="domain-row-star">★</span>' : '<span class="domain-row-star-spacer"></span>'}${escapeHtml(d.label)}</span>
            <span class="domain-row-count">${d.tests} tests</span>
          </div>
          <div class="domain-row-right">
            <div class="domain-row-progress">
              <div class="domain-row-bar" data-domain-bar="${d.spec}"></div>
            </div>
            <span class="domain-row-pct" data-domain-pct="${d.spec}"></span>
            <span class="domain-row-result" data-domain-result="${d.spec}"></span>
          </div>
        </div>
      `).join('');

      // Click row to toggle selection
      list.addEventListener('click', (e) => {
        const row = e.target.closest('.domain-row');
        if (!row) return;
        row.classList.toggle('selected');
      });
    }

    // Heal toggle pills
    const healOn = document.getElementById('heal-on');
    const healOff = document.getElementById('heal-off');
    const healCheckbox = document.getElementById('heal-toggle');
    if (healOn && healOff) {
      healOn.addEventListener('click', () => { healOn.classList.add('active'); healOff.classList.remove('active'); if (healCheckbox) healCheckbox.checked = true; });
      healOff.addEventListener('click', () => { healOff.classList.add('active'); healOn.classList.remove('active'); if (healCheckbox) healCheckbox.checked = false; });
    }

    // Pill group click handlers
    document.querySelectorAll('.pill-group').forEach(group => {
      group.addEventListener('click', (e) => {
        if (e.target.classList.contains('pill')) {
          group.querySelectorAll('.pill').forEach(p => p.classList.remove('active'));
          e.target.classList.add('active');
        }
      });
    });

    // Run Selected button
    const btnRunSelected = document.getElementById('btn-run-selected');
    if (btnRunSelected) {
      btnRunSelected.addEventListener('click', () => startTestRun(false));
    }

    // Run All button
    const btnRunAll = document.getElementById('btn-run-all');
    if (btnRunAll) {
      btnRunAll.addEventListener('click', () => startTestRun(true));
    }

    // Stop button
    const btnStop = document.getElementById('btn-stop');
    if (btnStop) {
      btnStop.addEventListener('click', () => stopTestRun());
    }

    const btnClear = document.getElementById('btn-clear');
    if (btnClear) {
      btnClear.addEventListener('click', () => clearTestRunner());
    }
  }

  function clearTestRunner() {
    // Broadcast clear to all connected devices
    fetch('/api/tests/clear', { method: 'POST' });
  }

  function doClearRunner() {
    document.getElementById('runner-log').innerHTML = '';
    document.getElementById('runner-log-container').style.display = 'none';
    document.getElementById('btn-run-selected').style.display = 'inline-block';
    document.getElementById('btn-run-all').style.display = 'inline-block';
    document.getElementById('btn-stop').style.display = 'none';
    /* btn-clear always visible */
    resetDomainProgress();
    runnerPassCount = 0;
    runnerFailCount = 0;
    setRunnerState('idle');
  }

  async function startTestRun(runAll) {
    const specs = runAll ? [] : getSelectedSpecs();
    if (!runAll && specs.length === 0) { alert('Select at least one domain'); return; }

    const workers = document.querySelector('#worker-pills .pill.active')?.dataset.value || '3';
    const retries = document.querySelector('#retry-pills .pill.active')?.dataset.value || '0';
    const heal = document.getElementById('heal-toggle')?.checked || false;

    // Reset UI
    document.getElementById('runner-log').innerHTML = '';
    document.getElementById('runner-log-container').style.display = 'block';
    document.getElementById('btn-run-selected').style.display = 'none';
    resetDomainProgress();
    document.getElementById('btn-run-all').style.display = 'none';
    document.getElementById('btn-stop').style.display = 'inline-block';
    setRunnerState('running');
    runnerTestCount = 0;
    runnerPassCount = 0;
    runnerFailCount = 0;

    await fetch('/api/tests/run', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({specs, workers: parseInt(workers), retries: parseInt(retries), heal})
    });
  }

  async function stopTestRun() {
    await fetch('/api/tests/stop', {method: 'POST'});
    setRunnerState('idle');
  }

  function appendRunnerLog(line) {
    const log = document.getElementById('runner-log');
    if (!log) return;
    const el = document.createElement('div');
    el.className = 'log-line';
    if (line.includes('✓')) el.classList.add('log-pass');
    else if (line.includes('✘') || line.includes('FAIL')) el.classList.add('log-fail');
    else if (line.startsWith('[HEAL]')) el.classList.add('log-heal');
    el.textContent = line;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  function setRunnerState(state) {
    const dot = document.getElementById('runner-dot');
    const text = document.getElementById('runner-status');
    if (!dot || !text) return;
    text.textContent = state.toUpperCase();
    dot.className = 'runner-status-dot runner-state-' + state;
  }

  function getSelectedSpecs() {
    return [...document.querySelectorAll('.domain-row.selected')].map(r => r.dataset.spec);
  }

  // Track per-domain progress during a run
  const domainProgress = {};

  function resetDomainProgress() {
    DOMAINS.forEach(d => { domainProgress[d.spec] = {passed: 0, failed: 0, total: d.tests, done: false}; });
    document.querySelectorAll('.domain-row-bar').forEach(bar => { bar.style.width = '0%'; bar.className = 'domain-row-bar'; });
    document.querySelectorAll('.domain-row-pct').forEach(el => el.textContent = '');
    document.querySelectorAll('.domain-row-result').forEach(el => { el.textContent = ''; el.className = 'domain-row-result'; });
  }

  function updateDomainProgress(spec, passed) {
    if (!domainProgress[spec]) return;
    const dp = domainProgress[spec];
    if (passed) dp.passed++; else dp.failed++;
    const completed = dp.passed + dp.failed;
    const pct = Math.round((completed / dp.total) * 100);

    const bar = document.querySelector(`[data-domain-bar="${spec}"]`);
    const pctEl = document.querySelector(`[data-domain-pct="${spec}"]`);
    const resultEl = document.querySelector(`[data-domain-result="${spec}"]`);

    if (bar) {
      bar.style.width = pct + '%';
      if (dp.failed > 0) bar.classList.add('bar-has-failures');
    }
    if (pctEl) pctEl.textContent = pct + '%';

    if (completed >= dp.total) {
      dp.done = true;
      if (resultEl) {
        if (dp.failed === 0) {
          resultEl.textContent = '✓';
          resultEl.className = 'domain-row-result result-pass';
        } else {
          resultEl.textContent = dp.failed + ' failed';
          resultEl.className = 'domain-row-result result-fail';
        }
      }
    }
  }

  function updateProgress() {
    const total = runnerPassCount + runnerFailCount;
    const pct = total > 0 ? ((runnerPassCount / total) * 100).toFixed(0) : 0;
    const bar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    if (bar) bar.style.width = pct + '%';
    if (progressText) progressText.textContent = `${runnerPassCount} passed, ${runnerFailCount} failed`;
  }
})();
