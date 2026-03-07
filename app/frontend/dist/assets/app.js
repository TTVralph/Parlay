(function () {
  const state = { mode: 'login', token: localStorage.getItem('parlaybot_token') || '', me: null };

  async function api(path, options = {}) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
    if (state.token) headers.Authorization = 'Bearer ' + state.token;
    const resp = await fetch(path, Object.assign({}, options, { headers }));
    if (!resp.ok) {
      let detail = resp.statusText;
      try { const data = await resp.json(); detail = data.detail || JSON.stringify(data); } catch (err) {}
      throw new Error(detail);
    }
    const contentType = resp.headers.get('content-type') || '';
    if (contentType.includes('application/json')) return resp.json();
    return resp.text();
  }

  function $(id) { return document.getElementById(id); }
  function setText(id, value) { $(id).textContent = value; }
  function renderAuth() {
    $('authState').textContent = state.me ? JSON.stringify(state.me, null, 2) : 'Not signed in';
  }

  async function loadMe() {
    if (!state.token) { state.me = null; renderAuth(); return; }
    try {
      state.me = await api('/auth/me');
      renderAuth();
    } catch (err) {
      state.me = null;
      state.token = '';
      localStorage.removeItem('parlaybot_token');
      renderAuth();
    }
  }

  async function loadPlans() {
    const data = await api('/billing/plans');
    $('plansState').textContent = JSON.stringify(data, null, 2);
  }

  async function loadBilling() {
    const data = await api('/billing/account');
    $('billingState').textContent = JSON.stringify(data, null, 2);
  }

  async function openPortal() {
    const data = await api('/billing/portal', { method: 'POST', body: JSON.stringify({ return_url: window.location.origin + '/app' }) });
    $('billingState').textContent = JSON.stringify(data, null, 2);
  }

  async function startCheckout() {
    const data = await api('/billing/stripe/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan_code: $('planCode').value, success_url: window.location.origin + '/app', cancel_url: window.location.origin + '/app' })
    });
    $('billingState').textContent = JSON.stringify(data, null, 2);
  }

  async function cancelAtPeriodEnd() {
    const data = await api('/billing/cancel', { method: 'POST', body: JSON.stringify({ immediate: false }) });
    $('billingState').textContent = JSON.stringify(data, null, 2);
  }

  async function resumeSubscription() {
    const data = await api('/billing/resume', { method: 'POST' });
    $('billingState').textContent = JSON.stringify(data, null, 2);
  }

  async function loadLeaderboard() {
    const data = await api('/public/leaderboard');
    const rows = data.rows || [];
    const tbody = $('leaderboardBody');
    tbody.innerHTML = rows.length ? rows.map(function (row) {
      const roi = row.roi === null ? '—' : (row.roi * 100).toFixed(1) + '%';
      return '<tr><td><a href="/cappers/' + row.username + '">@' + row.username + '</a></td><td>' + (row.hit_rate * 100).toFixed(1) + '%</td><td>' + roi + '</td><td>' + row.settled_tickets + '</td></tr>';
    }).join('') : '<tr><td colspan="4">No public cappers yet.</td></tr>';

    const settled = rows.reduce((sum, row) => sum + (row.settled_tickets || 0), 0);
    const avgHit = rows.length ? rows.reduce((sum, row) => sum + (row.hit_rate || 0), 0) / rows.length : 0;
    const best = rows.filter(r => r.roi !== null).sort((a, b) => b.roi - a.roi)[0];
    setText('metricCappers', String(rows.length));
    setText('metricSettled', String(settled));
    setText('metricHitRate', (avgHit * 100).toFixed(1) + '%');
    setText('metricBestRoi', best ? '@' + best.username + ' ' + (best.roi * 100).toFixed(1) + '%' : '—');
  }

  async function submitAuth() {
    const payload = {
      username: $('username').value,
      password: $('password').value,
      email: $('email').value || null,
      role: $('role').value,
      linked_capper_username: $('linkedCapper').value || null,
    };
    const path = state.mode === 'register' ? '/auth/register' : '/auth/login';
    const body = state.mode === 'register' ? payload : { username: payload.username, password: payload.password };
    const data = await api(path, { method: 'POST', body: JSON.stringify(body) });
    state.token = data.access_token;
    localStorage.setItem('parlaybot_token', state.token);
    state.me = data.user;
    renderAuth();
    await loadBilling().catch(err => $('billingState').textContent = err.message);
  }

  async function logout() {
    if (state.token) {
      try { await api('/auth/logout', { method: 'POST' }); } catch (err) {}
    }
    state.token = '';
    state.me = null;
    localStorage.removeItem('parlaybot_token');
    renderAuth();
    $('billingState').textContent = 'Not signed in';
  }

  async function loadCapper() {
    const data = await api('/capper/me');
    $('displayName').value = data.display_name || '';
    $('bio').value = data.bio || '';
    $('isPublic').checked = !!data.is_public;
    $('capperState').textContent = JSON.stringify(data, null, 2);
  }

  async function saveCapper() {
    const data = await api('/capper/me', {
      method: 'PATCH',
      body: JSON.stringify({ display_name: $('displayName').value || null, bio: $('bio').value || null, is_public: $('isPublic').checked })
    });
    $('capperState').textContent = JSON.stringify(data, null, 2);
    await loadLeaderboard();
  }

  document.querySelectorAll('.tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      state.mode = btn.getAttribute('data-mode');
      document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
      btn.classList.add('active');
    });
  });
  $('submitAuth').addEventListener('click', () => submitAuth().catch(err => $('authState').textContent = err.message));
  $('logoutBtn').addEventListener('click', () => logout());
  $('refreshBtn').addEventListener('click', () => Promise.all([loadLeaderboard(), loadPlans()]).catch(err => setText('metricBestRoi', err.message)));
  $('loadCapperBtn').addEventListener('click', () => loadCapper().catch(err => $('capperState').textContent = err.message));
  $('saveCapperBtn').addEventListener('click', () => saveCapper().catch(err => $('capperState').textContent = err.message));
  $('loadBillingBtn').addEventListener('click', () => loadBilling().catch(err => $('billingState').textContent = err.message));
  $('openPortalBtn').addEventListener('click', () => openPortal().catch(err => $('billingState').textContent = err.message));
  $('startCheckoutBtn').addEventListener('click', () => startCheckout().catch(err => $('billingState').textContent = err.message));
  $('cancelEndBtn').addEventListener('click', () => cancelAtPeriodEnd().catch(err => $('billingState').textContent = err.message));
  $('resumeBtn').addEventListener('click', () => resumeSubscription().catch(err => $('billingState').textContent = err.message));

  loadLeaderboard().catch(err => setText('metricBestRoi', err.message));
  loadPlans().catch(err => $('plansState').textContent = err.message);
  loadMe();
  renderAuth();
})();
