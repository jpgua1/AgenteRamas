const fs = require('fs');
const path = require('path');

describe('web/dashboard.js', () => {
  it('should define renderDashboard and showLLMSections', () => {
    const dashboardJsPath = path.resolve(__dirname, '../web/dashboard.js');
    const code = fs.readFileSync(dashboardJsPath, 'utf-8');
    expect(code).toContain('function renderDashboard');
    expect(code).toContain('function showLLMSections');
  });

  it('should define escapeHtml and metric', () => {
    const dashboardJsPath = path.resolve(__dirname, '../web/dashboard.js');
    const code = fs.readFileSync(dashboardJsPath, 'utf-8');
    expect(code).toContain('function escapeHtml');
    expect(code).toContain('function metric');
  });

  it('should have window.addEventListener for load', () => {
    const dashboardJsPath = path.resolve(__dirname, '../web/dashboard.js');
    const code = fs.readFileSync(dashboardJsPath, 'utf-8');
    expect(code).toContain('window.addEventListener');
    expect(code).toContain('loadDashboard');
  });
});
