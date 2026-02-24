const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

describe('web/app.js UI logic', () => {
  let document, window, form, statusEl;
  beforeAll(() => {
    const html = `
      <form id="analyze-form"></form>
      <div id="status"></div>
      <div id="platformInfo"></div>
      <button id="startBtn"></button>
      <input id="repository_url" value="https://gitlab.com/org/repo" />
      <input id="token" value="token123" />
      <input id="project_path" value="" />
      <select id="auto_discover_groups"><option value="true">true</option></select>
      <select id="analysis_mode"><option value="basic">basic</option></select>
      <input id="active_days" value="30" />
      <input id="stale_days" value="90" />
      <div id="dashboard" class="hidden"></div>
      <div id="branches-detail" class="hidden"></div>
      <table id="projects-table"><tbody></tbody></table>
      <div id="summary"></div>
      <table id="branches-table"><tbody></tbody></table>
      <button id="backBtn"></button>
      <button id="reloadBtn"></button>
      <button id="downloadBtn"></button>
      <div id="dashboardPlatform"></div>
      <div id="insights-section" class="hidden"></div>
      <div id="insights-content"></div>
      <button id="loadInsightsBtn"></button>
      <div id="recommendations-section" class="hidden"></div>
      <div id="recommendations-content"></div>
      <button id="loadRecommendationsBtn"></button>
      <button id="loadLatestBtn"></button>
    `;
    const dom = new JSDOM(html, { url: 'http://localhost/' });
    window = dom.window;
    document = window.document;
    global.document = document;
    global.window = window;
    global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ job_id: 'abc', platform: 'gitlab' }) }));
    global.location = { hash: '', href: '', reload: jest.fn() };
    global.console = { log: jest.fn(), warn: jest.fn(), error: jest.fn() };
    global.setTimeout = window.setTimeout;
    global.clearTimeout = window.clearTimeout;
    global.setInterval = window.setInterval;
    global.clearInterval = window.clearInterval;
    require('../../web/app.js');
    form = document.getElementById('analyze-form');
    statusEl = document.getElementById('status');
  });

  afterAll(() => {
    jest.resetModules();
  });

  test('should show error if repository_url or token is missing', () => {
    document.getElementById('repository_url').value = '';
    document.getElementById('token').value = '';
    form.dispatchEvent(new window.Event('submit'));
    expect(statusEl.textContent).toMatch(/Repository URL y Token son requeridos/);
  });

  test('should call fetch on submit and update status', async () => {
    document.getElementById('repository_url').value = 'https://gitlab.com/org/repo';
    document.getElementById('token').value = 'token123';
    await form.dispatchEvent(new window.Event('submit'));
    expect(global.fetch).toHaveBeenCalled();
  });

  test('should render dashboard metrics', () => {
    const renderDashboard = global.renderDashboard || window.renderDashboard;
    const data = { analysis: { total_projects: 1, total_branches: 2, total_inactive_branches: 1, total_tags: 1, total_releases: 1, total_obsolete_tags: 0, artifacts_expiring_soon: 0, artifacts_expired: 0 }, projects: [{ name: 'repo', branches: [{}], inactive_count: 0 }] };
    renderDashboard(data);
    expect(document.getElementById('dashboard').classList.contains('hidden')).toBe(false);
    expect(document.getElementById('summary').innerHTML).toMatch(/Proyectos/);
  });
});
