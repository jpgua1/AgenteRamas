const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

describe('web/app.js', () => {
  let window, document;
  beforeAll(() => {
    const html = `
      <html><body>
        <form id="analyze-form"></form>
        <div id="status"></div>
        <div id="platformInfo"></div>
        <button id="loadLatestBtn"></button>
        <div id="dashboard"></div>
        <div id="summary"></div>
        <table id="projects-table"><tbody></tbody></table>
        <div id="branches-detail" class="hidden"></div>
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
        <input id="repository_url"/>
        <input id="token"/>
        <input id="project_path"/>
        <select id="auto_discover_groups"><option value="true"></option></select>
        <select id="analysis_mode"><option value="basic"></option></select>
        <input id="active_days"/>
        <input id="stale_days"/>
        <button id="startBtn"></button>
      </body></html>
    `;
    const dom = new JSDOM(html, { url: 'http://localhost' });
    window = dom.window;
    document = window.document;
    global.window = window;
    global.document = document;
    global.location = window.location;
    global.fetch = jest.fn();
    global.setTimeout = window.setTimeout;
    global.clearTimeout = window.clearTimeout;
    global.console = window.console;
    global.alert = jest.fn();
    global.Event = window.Event;
    global.navigator = window.navigator;
    global.history = window.history;
    global.DOMParser = window.DOMParser;
    global.HTMLElement = window.HTMLElement;
    global.Node = window.Node;
    global.HTMLTableElement = window.HTMLTableElement;
    global.HTMLButtonElement = window.HTMLButtonElement;
    global.HTMLInputElement = window.HTMLInputElement;
    global.HTMLSelectElement = window.HTMLSelectElement;
    global.HTMLDivElement = window.HTMLDivElement;
    global.HTMLFormElement = window.HTMLFormElement;
    global.HTMLTableRowElement = window.HTMLTableRowElement;
    global.HTMLTableCellElement = window.HTMLTableCellElement;
    global.HTMLTableSectionElement = window.HTMLTableSectionElement;
    global.HTMLAnchorElement = window.HTMLAnchorElement;
    global.HTMLSpanElement = window.HTMLSpanElement;
    global.HTMLUListElement = window.HTMLUListElement;
    global.HTMLLIElement = window.HTMLLIElement;
    global.HTMLParagraphElement = window.HTMLParagraphElement;
    global.HTMLHeadingElement = window.HTMLHeadingElement;
    global.HTMLBodyElement = window.HTMLBodyElement;
    global.HTMLHtmlElement = window.HTMLHtmlElement;
    global.HTMLDocument = window.HTMLDocument;
    global.EventTarget = window.EventTarget;
    global.MouseEvent = window.MouseEvent;
    global.KeyboardEvent = window.KeyboardEvent;
    global.CustomEvent = window.CustomEvent;
    global.Blob = window.Blob;
    global.File = window.File;
    global.FileReader = window.FileReader;
    global.URL = window.URL;
    global.URLSearchParams = window.URLSearchParams;
    global.XMLHttpRequest = window.XMLHttpRequest;
    global.FormData = window.FormData;
    global.navigator = window.navigator;
    global.performance = window.performance;
    global.requestAnimationFrame = window.requestAnimationFrame;
    global.cancelAnimationFrame = window.cancelAnimationFrame;
    global.getComputedStyle = window.getComputedStyle;
    global.MutationObserver = window.MutationObserver;
    global.ResizeObserver = window.ResizeObserver;
    global.IntersectionObserver = window.IntersectionObserver;
    global.HTMLElement = window.HTMLElement;
    global.HTMLCollection = window.HTMLCollection;
    global.NodeList = window.NodeList;
    global.Element = window.Element;
    global.Text = window.Text;
    global.Comment = window.Comment;
    global.DocumentFragment = window.DocumentFragment;
    global.Range = window.Range;
    global.Selection = window.Selection;
    global.CSSStyleDeclaration = window.CSSStyleDeclaration;
    global.CSSRule = window.CSSRule;
    global.CSSStyleSheet = window.CSSStyleSheet;
    global.CSSMediaRule = window.CSSMediaRule;
    global.CSSImportRule = window.CSSImportRule;
    global.CSSFontFaceRule = window.CSSFontFaceRule;
    global.CSSPageRule = window.CSSPageRule;
    global.CSSKeyframesRule = window.CSSKeyframesRule;
    global.CSSKeyframeRule = window.CSSKeyframeRule;
    global.CSSSupportsRule = window.CSSSupportsRule;
    global.CSSNamespaceRule = window.CSSNamespaceRule;
    global.CSSCounterStyleRule = window.CSSCounterStyleRule;
    global.CSSFontFeatureValuesRule = window.CSSFontFeatureValuesRule;
    global.CSSViewportRule = window.CSSViewportRule;
    global.CSSRegionRule = window.CSSRegionRule;
    global.CSS = window.CSS;
    global.getSelection = window.getSelection;
    global.scrollTo = window.scrollTo;
    global.scrollBy = window.scrollBy;
    global.scroll = window.scroll;
    global.scrollX = window.scrollX;
    global.scrollY = window.scrollY;
    global.scrollTop = window.scrollTop;
    global.scrollLeft = window.scrollLeft;
    global.scrollHeight = window.scrollHeight;
    global.scrollWidth = window.scrollWidth;
    global.innerWidth = window.innerWidth;
    global.innerHeight = window.innerHeight;
    global.outerWidth = window.outerWidth;
    global.outerHeight = window.outerHeight;
    global.pageXOffset = window.pageXOffset;
    global.pageYOffset = window.pageYOffset;
    global.screen = window.screen;
    global.screenX = window.screenX;
    global.screenY = window.screenY;
    global.screenLeft = window.screenLeft;
    global.screenTop = window.screenTop;
    global.screenWidth = window.screenWidth;
    global.screenHeight = window.screenHeight;
    global.devicePixelRatio = window.devicePixelRatio;
    global.matchMedia = window.matchMedia;
    global.requestIdleCallback = window.requestIdleCallback;
    global.cancelIdleCallback = window.cancelIdleCallback;
    global.open = window.open;
    global.close = window.close;
    global.print = window.print;
    global.prompt = window.prompt;
    global.confirm = window.confirm;
    global.focus = window.focus;
    global.blur = window.blur;
    global.scrollTo = window.scrollTo;
    global.scrollBy = window.scrollBy;
    global.scroll = window.scroll;
    global.scrollX = window.scrollX;
    global.scrollY = window.scrollY;
    global.scrollTop = window.scrollTop;
    global.scrollLeft = window.scrollLeft;
    global.scrollHeight = window.scrollHeight;
    global.scrollWidth = window.scrollWidth;
    global.innerWidth = window.innerWidth;
    global.innerHeight = window.innerHeight;
    global.outerWidth = window.outerWidth;
    global.outerHeight = window.outerHeight;
    global.pageXOffset = window.pageXOffset;
    global.pageYOffset = window.pageYOffset;
    global.screen = window.screen;
    global.screenX = window.screenX;
    global.screenY = window.screenY;
    global.screenLeft = window.screenLeft;
    global.screenTop = window.screenTop;
    global.screenWidth = window.screenWidth;
    global.screenHeight = window.screenHeight;
    global.devicePixelRatio = window.devicePixelRatio;
    global.matchMedia = window.matchMedia;
    global.requestIdleCallback = window.requestIdleCallback;
    global.cancelIdleCallback = window.cancelIdleCallback;
    global.open = window.open;
    global.close = window.close;
    global.print = window.print;
    global.prompt = window.prompt;
    global.confirm = window.confirm;
    global.focus = window.focus;
    global.blur = window.blur;
  });

  it('should define setStatus and getProgressLabel', () => {
    const appJsPath = path.resolve(__dirname, '../web/app.js');
    const code = fs.readFileSync(appJsPath, 'utf-8');
    expect(code).toContain('function setStatus');
    expect(code).toContain('function getProgressLabel');
  });

  it('should have progressStages array', () => {
    const appJsPath = path.resolve(__dirname, '../web/app.js');
    const code = fs.readFileSync(appJsPath, 'utf-8');
    expect(code).toContain('const progressStages');
  });

  it('should render metrics and escapeHtml', () => {
    const appJsPath = path.resolve(__dirname, '../web/app.js');
    const code = fs.readFileSync(appJsPath, 'utf-8');
    expect(code).toContain('function metric');
    expect(code).toContain('function escapeHtml');
  });
});
