document.querySelectorAll('[data-source-url]').forEach(panel => {
    const status = panel.querySelector('.source-result');
    const links = panel.querySelector('.source-links');
    const retry = panel.querySelector('.source-retry');
    async function load() {
        retry.hidden = true;
        status.textContent = 'Consultando fontes disponíveis…';
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
                ? `Não foi possível consultar: ${data.unavailable.join(', ')}.`
                : data.sources.length ? 'Títulos correspondentes encontrados:'
                : 'Nenhuma correspondência encontrada nas fontes consultadas.';
            retry.hidden = !data.unavailable.length;
        } catch {
            status.textContent = 'Não foi possível consultar outras fontes agora.';
            retry.hidden = false;
        }
    }
    retry.addEventListener('click', load);
    load();
});
