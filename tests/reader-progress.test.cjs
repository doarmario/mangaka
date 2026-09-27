const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function reader(authenticated = true) {
    const events = new Map();
    const elements = new Map();
    const timers = new Map();
    const images = [];
    const requests = [];
    const storage = new Map([['mangaka-reader:chapter', JSON.stringify({ page: 1 })]]);
    let timerId = 0;
    function element() {
        return {
            checked: false, value: '100', children: [], listeners: {},
            addEventListener(name, fn) { this.listeners[name] = fn; },
            replaceChildren() { this.children = []; },
            appendChild(child) { this.children.push(child); },
            scrollIntoView() {}, setAttribute() {},
        };
    }
    class Image {
        constructor() { Object.assign(this, element()); images.push(this); }
    }
    const document = {
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, element());
            return elements.get(id);
        },
        addEventListener(name, fn) { events.set(name, fn); },
        documentElement: { style: { setProperty() {} } },
    };
    vm.runInNewContext(fs.readFileSync('app/static/js/reader.js', 'utf8'), {
        document, window: { addEventListener() {} }, Image,
        localStorage: { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value) },
        setTimeout(fn) { const id = ++timerId; timers.set(id, fn); return id; },
        clearTimeout(id) { timers.delete(id); },
        fetch: async (url, options) => { requests.push({ url, ...options }); return { ok: true }; },
        resumePage: 43, readerAuthenticated: authenticated, readerCsrf: 'csrf-test',
        pages: Array(57).fill('/image'), cap: 'chapter', console,
    });
    events.get('DOMContentLoaded')();
    return { elements, storage, requests, images, async flush() {
        for (const [id, fn] of [...timers]) { timers.delete(id); await fn(); }
    } };
}

test('authenticated reader resumes canonical page and saves with CSRF', async () => {
    const r = reader();
    r.images[0].listeners.load();
    await r.flush();
    assert.equal(r.requests.length, 1);
    assert.equal(r.requests[0].url, '/cap/chapter/progress');
    assert.equal(r.requests[0].method, 'POST');
    assert.equal(r.requests[0].headers['X-CSRFToken'], 'csrf-test');
    assert.deepEqual(JSON.parse(r.requests[0].body), { page: 43, page_count: 57 });
});

test('page navigation debounces and persists the last selected page', async () => {
    const r = reader();
    r.elements.get('changenext').listeners.click();
    r.elements.get('changenext').listeners.click();
    await r.flush();
    assert.equal(r.requests.length, 1);
    assert.equal(JSON.parse(r.requests[0].body).page, 45);
});

test('anonymous reader keeps local progress without sending user state', async () => {
    const r = reader(false);
    r.images[0].listeners.load();
    await r.flush();
    assert.equal(r.requests.length, 0);
    assert.equal(JSON.parse(r.storage.get('mangaka-reader:chapter')).page, 1);
});
