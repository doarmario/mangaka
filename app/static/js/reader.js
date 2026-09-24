document.addEventListener('DOMContentLoaded', () => {
    const mode = document.getElementById('scrollToggle');
    const container = document.getElementById('leitor');
    const previous = document.getElementById('changeprev');
    const next = document.getElementById('changenext');
    const progress = document.getElementById('reader-progress');
    let index = 0;
    let marked = false;
    let marking = false;
    let observer;
    try { mode.checked = localStorage.getItem('mode') === 'scroll'; } catch { /* Storage is optional. */ }

    async function markRead() {
        if (!readerAuthenticated || marked || marking) return;
        marking = true;
        try {
            const response = await fetch(`/cap/${cap}/readed`);
            if (response.ok) marked = (await response.json()).status === 'success';
        } catch { /* Reading remains available if saving fails. */ }
        finally { marking = false; }
    }
    function image(number, scroll) {
        const img = new Image();
        img.alt = `Página ${number + 1}`;
        img.loading = scroll && number > 1 ? 'lazy' : 'eager';
        img.addEventListener('load', () => {
            if (!scroll && number === index) {
                progress.textContent = `Página ${number + 1} de ${pages.length} · Use as setas do teclado para navegar`;
                if (number === pages.length - 1) markRead();
            }
            if (scroll && number === pages.length - 1 && img.isConnected) {
                const end = document.getElementById('reader-end');
                if (end) observer?.observe(end);
            }
        });
        img.addEventListener('error', () => {
            progress.textContent = `Não foi possível carregar a página ${number + 1}. Recarregue para tentar novamente.`;
        });
        img.src = pages[number];
        return img;
    }
    function render() {
        observer?.disconnect();
        container.replaceChildren();
        previous.hidden = mode.checked || index === 0 || !pages.length;
        next.hidden = mode.checked || index === pages.length - 1 || !pages.length;
        if (!pages.length) { progress.textContent = 'Este capítulo não tem páginas disponíveis.'; return; }
        if (mode.checked) {
            progress.textContent = `${pages.length} páginas · Rolagem contínua`;
            if ('IntersectionObserver' in window) {
                observer = new IntersectionObserver(entries => {
                    if (entries.some(entry => entry.isIntersecting)) markRead();
                }, { threshold: 0.5 });
            }
            pages.forEach((_, number) => container.appendChild(image(number, true)));
            const end = document.createElement('div');
            end.id = 'reader-end';
            end.style.height = '1px';
            end.setAttribute('aria-hidden', 'true');
            container.appendChild(end);
        } else {
            progress.textContent = `Carregando página ${index + 1} de ${pages.length}…`;
            container.appendChild(image(index, false));
            if (pages[index + 1]) { const preload = new Image(); preload.src = pages[index + 1]; }
        }
    }
    function change(delta) {
        if (mode.checked || !pages.length) return;
        const target = Math.max(0, Math.min(pages.length - 1, index + delta));
        if (target !== index) { index = target; render(); }
    }
    previous.addEventListener('click', () => change(-1));
    next.addEventListener('click', () => change(1));
    document.addEventListener('keydown', event => {
        if (event.target.closest('input, textarea, select, button, [contenteditable]')) return;
        if (!mode.checked && ['ArrowLeft', 'ArrowRight'].includes(event.key)) {
            event.preventDefault();
            change(event.key === 'ArrowLeft' ? -1 : 1);
        }
    });
    mode.addEventListener('change', () => {
        try { localStorage.setItem('mode', mode.checked ? 'scroll' : 'páginas'); } catch { /* Optional. */ }
        render();
    });
    render();
});
