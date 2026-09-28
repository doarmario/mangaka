document.querySelectorAll('[data-source-url]').forEach(panel => {
    const status = panel.querySelector('.source-result');
    const links = panel.querySelector('.source-links');
    const retry = panel.querySelector('.source-retry');
    async function load() {
        retry.hidden = true;
        status.textContent = 'Checking available sources…';
        try {
            const response = await fetch(panel.dataset.sourceUrl);
            if (!response.ok) throw new Error('sources');
            const data = await response.json();
            links.replaceChildren();
            for (const source of data.sources) {
                const link = document.createElement('a');
                link.className = 'button secondary';
                link.href = source.url;
                link.textContent = source.source_name;
                links.appendChild(link);
            }
            status.textContent = data.unavailable.length
                ? `Could not reach: ${data.unavailable.join(', ')}.`
                : data.sources.length ? 'Matching titles found:'
                : 'No matches found in the sources checked.';
            retry.hidden = !data.unavailable.length;
        } catch {
            status.textContent = 'Could not check other sources right now.';
            retry.hidden = false;
        }
    }
    retry.addEventListener('click', load);
    load();
});

const readingStatus = document.getElementById('reading-status');
readingStatus?.addEventListener('change', async () => {
    if (!readingStatus.value) return;
    const feedback = document.getElementById('action-status');
    readingStatus.disabled = true;
    try {
        const response = await fetch(readingStatus.dataset.url, {
            method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': readingStatus.dataset.csrf },
            body: JSON.stringify({ status: readingStatus.value })
        });
        if (!response.ok) throw new Error('status');
        feedback.textContent = 'Reading status saved to your library.';
    } catch { feedback.textContent = 'Could not save your reading status. Please try again.'; }
    finally { readingStatus.disabled = false; }
});
