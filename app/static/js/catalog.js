document.addEventListener('DOMContentLoaded', () => {
    const panel = document.querySelector('[data-catalog-stream]');
    if (!panel) return;
    const results = document.getElementById('catalog-results');
    const status = document.getElementById('catalog-load-status');
    const progress = document.getElementById('catalog-load-progress');
    const retry = document.getElementById('catalog-retry');
    let controller;
    let hasResults = false;

    function update(data) {
        if (data.started) return;
        if (data.waiting) {
            status.textContent = 'Checking sources. Results will appear shortly…';
            return;
        }
        if (data.error) throw new Error(data.error);
        if (data.html !== null && data.html !== undefined) {
            const focused = results.contains(document.activeElement) ? document.activeElement.closest('a')?.getAttribute('href') : null;
            results.innerHTML = data.html;
            hasResults = true;
            results.setAttribute('aria-busy', 'false');
            document.dispatchEvent(new Event('mangaka:content-updated'));
            if (focused) [...results.querySelectorAll('a')].find(a => a.getAttribute('href') === focused)?.focus({ preventScroll: true });
        }
        progress.value = data.completed;
        progress.max = data.total_sources;
        const unavailable = data.unavailable.length ? ` Could not reach: ${data.unavailable.join(', ')}.` : '';
        status.textContent = data.done
            ? `Checked ${data.completed} sources.${unavailable}`
            : `Checked ${data.completed} of ${data.total_sources} sources. You can start browsing while we check the rest.${unavailable}`;
        retry.hidden = !data.done || !data.unavailable.length;
    }

    async function load() {
        controller?.abort();
        controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 45000);
        retry.hidden = true;
        results.setAttribute('aria-busy', 'true');
        status.textContent = hasResults ? 'Checking sources again. Your results will stay available…' : 'Finding your next read. Results will appear as sources respond…';
        progress.value = 0;
        try {
            const response = await fetch(panel.dataset.catalogStream, { signal: controller.signal });
            if (!response.ok) throw new Error('Could not load the catalog. Please try again.');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let finished = false;
            while (true) {
                const { value, done } = await reader.read();
                buffer += decoder.decode(value, { stream: !done });
                const lines = buffer.split('\n');
                buffer = lines.pop();
                for (const line of lines) {
                    if (!line.trim()) continue;
                    const data = JSON.parse(line);
                    update(data);
                    finished ||= Boolean(data.done);
                }
                if (done) break;
            }
            if (!finished) throw new Error('Some sources did not finish loading. Please try again.');
        } catch (error) {
            controller.abort();
            status.textContent = error.name === 'AbortError' ? 'Some sources took too long. Please try again.' : error.message;
            if (!hasResults) results.replaceChildren();
            retry.hidden = false;
        } finally {
            clearTimeout(timeout);
            results.setAttribute('aria-busy', 'false');
        }
    }
    retry.addEventListener('click', load);
    window.addEventListener('pagehide', () => controller?.abort());
    load();
});
