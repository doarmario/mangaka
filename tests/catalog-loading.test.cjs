const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const tick = () => new Promise(resolve => setImmediate(resolve));

function setup() {
    const events = {};
    const elements = {};
    const chunks = [];
    let pending;
    let updated = 0;
    for (const id of ['catalog-results', 'catalog-load-status', 'catalog-load-progress', 'catalog-retry']) {
        elements[id] = { innerHTML: '', textContent: '', attrs: {}, hidden: true,
            setAttribute(k, v) { this.attrs[k] = v; },
            addEventListener(k, v) { this[k] = v; },
            contains() { return false; },
            replaceChildren() { this.innerHTML = ''; },
        };
    }
    const document = {
        querySelector: () => ({ dataset: { catalogStream: '/api/catalog/stream' } }),
        getElementById: id => elements[id],
        addEventListener: (key, fn) => { events[key] = fn; },
        dispatchEvent() { updated++; }, activeElement: null,
    };
    vm.runInNewContext(fs.readFileSync('app/static/js/catalog.js', 'utf8'), {
        document, window: { addEventListener() {} }, TextDecoder, AbortController, Event,
        setTimeout: () => 1, clearTimeout() {},
        fetch: async () => ({ ok: true, body: { getReader: () => ({
            read: () => chunks.length ? Promise.resolve(chunks.shift()) : new Promise(resolve => { pending = resolve; }),
        }) } }),
    });
    events.DOMContentLoaded();
    function push(value) {
        if (pending) { const resolve = pending; pending = null; resolve(value); }
        else chunks.push(value);
    }
    return { elements, updated: () => updated,
        bytes: value => push({ value, done: false }),
        event: data => push({ value: new TextEncoder().encode(JSON.stringify(data) + '\n'), done: false }),
        end: () => push({ done: true }),
    };
}

test('renders early results and decodes chunks split inside a Unicode title', async () => {
    const s = setup();
    s.event({ started: true });
    const data = new TextEncoder().encode(JSON.stringify({ html: '<a>Título</a>', completed: 1,
        total_sources: 2, unavailable: [], done: false }) + '\n');
    const split = data.indexOf(0xc3) + 1;
    s.bytes(data.slice(0, split));
    s.bytes(data.slice(split));
    await tick();
    assert.equal(s.elements['catalog-results'].innerHTML, '<a>Título</a>');
    assert.match(s.elements['catalog-load-status'].textContent, /start browsing/);
    assert.equal(s.updated(), 1);
    s.event({ html: '<a>Final title</a>', completed: 2, total_sources: 2, unavailable: [], done: true });
    s.end();
    await tick();
    assert.equal(s.elements['catalog-results'].attrs['aria-busy'], 'false');
    assert.equal(s.elements['catalog-retry'].hidden, true);
});

test('keeps useful results and offers retry if the stream fails', async () => {
    const s = setup();
    s.event({ html: '<a>Available title</a>', completed: 1, total_sources: 2, unavailable: [], done: false });
    s.event({ error: 'Could not finish loading the catalog. Please try again.', done: true });
    await tick();
    assert.equal(s.elements['catalog-results'].innerHTML, '<a>Available title</a>');
    assert.equal(s.elements['catalog-retry'].hidden, false);
    assert.equal(s.elements['catalog-results'].attrs['aria-busy'], 'false');
});

test('detects an interrupted stream instead of leaving the page loading', async () => {
    const s = setup();
    s.event({ started: true });
    s.end();
    await tick();
    assert.match(s.elements['catalog-load-status'].textContent, /did not finish/);
    assert.equal(s.elements['catalog-retry'].hidden, false);
});
