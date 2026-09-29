document.addEventListener('DOMContentLoaded', () => {
    const panel = document.querySelector('[data-catalog-stream]');
    if (!panel) return;
    const results = document.getElementById('catalog-results');
    const status = document.getElementById('catalog-load-status');
    const progress = document.getElementById('catalog-load-progress');
    const retry = document.getElementById('catalog-retry');
    let controller;
    let hasResults = false;

    const sourceIds = card => {
        try { return JSON.parse(card.dataset.catalogSources || '[]'); }
        catch (_) { return []; }
    };

    function updateCard(existing, incoming) {
        const ids = [...new Set([...sourceIds(existing), ...sourceIds(incoming)])];
        existing.dataset.catalogId = incoming.dataset.catalogId;
        existing.dataset.catalogSources = JSON.stringify(ids);
        if (incoming.getAttribute('href')) existing.setAttribute('href', incoming.getAttribute('href'));
        const incomingTitle = incoming.querySelector('h3');
        const title = existing.querySelector('h3');
        if (incomingTitle && title) title.textContent = incomingTitle.textContent;
        const incomingCaption = incoming.querySelector('.card-caption');
        const caption = existing.querySelector('.card-caption');
        if (incomingCaption && caption) {
            caption.textContent = incomingCaption.textContent;
            caption.setAttribute('title', incomingCaption.textContent);
        }
    }

    function mergeHtml(html) {
        // The fallback keeps the stream usable in small embedded clients and
        // test harnesses without a DOM parser.
        if (!document.createElement || !results.querySelector) {
            results.innerHTML = html;
            document.dispatchEvent(new Event('mangaka:content-updated'));
            return;
        }
        const template = document.createElement('template');
        template.innerHTML = html;
        const incomingGrid = template.content.querySelector('.card-grid');
        const incomingCards = incomingGrid ? [...incomingGrid.querySelectorAll('.manga-card[data-catalog-id]')] : [];
        const currentGrid = results.querySelector('.card-grid');
        const currentCards = currentGrid ? [...currentGrid.querySelectorAll('.manga-card[data-catalog-id]')] : [];
        if (!currentGrid || currentGrid.classList.contains('catalog-skeletons') || (!hasResults && !currentCards.length)) {
            results.replaceChildren(...template.content.childNodes);
            hasResults = true;
            document.dispatchEvent(new Event('mangaka:content-updated'));
            return;
        }
        if (!incomingGrid) return;
        let inserted = false;
        for (const incoming of incomingCards) {
            const incomingSources = sourceIds(incoming);
            let existing = currentCards.find(card => card.dataset.catalogId === incoming.dataset.catalogId);
            if (!existing) existing = currentCards.find(card => sourceIds(card).some(id => incomingSources.includes(id)));
            if (existing) {
                updateCard(existing, incoming);
                // If canonical resolution merges two cards, retain the first
                // card so its position and loaded cover remain stable.
                for (const duplicate of [...currentGrid.querySelectorAll('.manga-card[data-catalog-id]')]) {
                    if (duplicate !== existing && sourceIds(duplicate).some(id => incomingSources.includes(id))) duplicate.remove();
                }
            } else {
                currentGrid.append(incoming);
                currentCards.push(incoming);
                inserted = true;
            }
        }
        const incomingPaginator = template.content.querySelector('.paginator');
        const currentPaginator = results.querySelector('.paginator');
        if (incomingPaginator) {
            if (currentPaginator) currentPaginator.replaceWith(incomingPaginator);
            else results.append(incomingPaginator);
        } else if (currentPaginator) currentPaginator.remove();
        hasResults = true;
        if (inserted) document.dispatchEvent(new Event('mangaka:content-updated'));
    }

    function update(data) {
        if (data.started) return;
        if (data.waiting) {
            status.textContent = 'Checking sources. Results will appear shortly…';
            return;
        }
        if (data.error) throw new Error(data.error);
        if (data.html !== null && data.html !== undefined) {
            mergeHtml(data.html);
            hasResults = true;
            results.setAttribute('aria-busy', 'false');
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
