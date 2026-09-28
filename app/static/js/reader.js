document.addEventListener('DOMContentLoaded', () => {
    const mode = document.getElementById('scrollToggle');
    const container = document.getElementById('leitor');
    const previous = document.getElementById('changeprev');
    const next = document.getElementById('changenext');
    const progress = document.getElementById('reader-progress');
    const fullscreen = document.getElementById('fullscreenToggle');
    const width = document.getElementById('readerWidth');
    const brightness = document.getElementById('readerBrightness');
    let index = Math.max(0, Math.min(pages.length - 1, resumePage - 1));
    let saveTimer;
    let saveInFlight = false;
    let pendingSave = false;
    let marked = false;
    let marking = false;
    let observer;
    let touchStartX = 0;
    try { mode.checked = localStorage.getItem('mode') === 'scroll'; } catch { /* Storage is optional. */ }
    try {
        width.value = localStorage.getItem('reader-width') || '100';
        brightness.value = localStorage.getItem('reader-brightness') || '100';
    } catch { /* Optional. */ }
    function applyDisplay() {
        document.documentElement.style.setProperty('--reader-width', `${width.value}%`);
        document.documentElement.style.setProperty('--reader-brightness', `${brightness.value}%`);
    }
    applyDisplay();
    width.addEventListener('input', () => { applyDisplay(); localStorage.setItem('reader-width', width.value); });
    brightness.addEventListener('input', () => { applyDisplay(); localStorage.setItem('reader-brightness', brightness.value); });
    fullscreen.addEventListener('click', async () => {
        try {
            if (document.fullscreenElement) await document.exitFullscreen();
            else await document.querySelector('.reader').requestFullscreen();
            fullscreen.textContent = document.fullscreenElement ? 'Exit fullscreen' : 'Fullscreen';
        } catch { progress.textContent = 'Fullscreen is not available in this browser.'; }
    });
    try {
        const saved = JSON.parse(localStorage.getItem(`mangaka-reader:${cap}`) || 'null');
        if (!readerAuthenticated && saved && Number.isInteger(saved.page) && saved.page >= 0 && saved.page < pages.length) index = saved.page;
    } catch { /* Progress storage is optional. */ }

    async function sendProgress() {
        if (!readerAuthenticated || !pages.length) return;
        if (saveInFlight) { pendingSave = true; return; }
        saveInFlight = true;
        pendingSave = false;
        try {
            const response = await fetch(`/cap/${encodeURIComponent(cap)}/progress`, {
                method: 'POST', keepalive: true,
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': readerCsrf },
                body: JSON.stringify({ page: index + 1, page_count: pages.length })
            });
            if (!response.ok) progress.textContent = 'You can keep reading, but your progress could not be synced right now.';
        } catch { /* Local progress is retained if offline. */ }
        finally {
            saveInFlight = false;
            if (pendingSave) sendProgress();
        }
    }
    function saveProgress() {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(sendProgress, 600);
        try { localStorage.setItem(`mangaka-reader:${cap}`, JSON.stringify({ page: index, total: pages.length, savedAt: Date.now() })); } catch { /* Optional. */ }
    }

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
        img.alt = `Page ${number + 1}`;
        img.loading = scroll && number > 1 ? 'lazy' : 'eager';
        img.addEventListener('load', () => {
            if (!scroll && number === index) {
                progress.textContent = `Page ${number + 1} of ${pages.length} · Use the arrow keys to navigate`;
                saveProgress();
                if (number === pages.length - 1) markRead();
            }
            if (scroll && number === pages.length - 1 && img.isConnected) {
                const end = document.getElementById('reader-end');
                if (end) observer?.observe(end);
            }
        });
        img.addEventListener('error', () => {
            progress.textContent = `Could not load page ${number + 1}. Reload to try again.`;
        });
        img.src = pages[number];
        return img;
    }
    function render() {
        observer?.disconnect();
        container.replaceChildren();
        previous.hidden = mode.checked || index === 0 || !pages.length;
        next.hidden = mode.checked || index === pages.length - 1 || !pages.length;
        if (!pages.length) { progress.textContent = 'This chapter has no available pages.'; return; }
        if (mode.checked) {
            progress.textContent = `${pages.length} pages · Continuous scroll`;
            if ('IntersectionObserver' in window) {
                observer = new IntersectionObserver(entries => {
                    if (entries.some(entry => entry.isIntersecting)) { index = pages.length - 1; saveProgress(); markRead(); }
                }, { threshold: 0.5 });
            }
            pages.forEach((_, number) => container.appendChild(image(number, true)));
            if (index > 0) {
                const target = container.children[index];
                const restore = () => target.scrollIntoView({ block: 'start' });
                requestAnimationFrame(restore);
                if (!target.complete) target.addEventListener('load', restore, { once: true });
            }
            try {
                const saved = JSON.parse(localStorage.getItem(`mangaka-reader:${cap}`) || 'null');
                if (!readerAuthenticated && saved?.scroll) setTimeout(() => window.scrollTo({ top: saved.scroll, behavior: 'auto' }), 100);
            } catch { /* Optional. */ }
            const end = document.createElement('div');
            end.id = 'reader-end';
            end.style.height = '1px';
            end.setAttribute('aria-hidden', 'true');
            container.appendChild(end);
        } else {
            progress.textContent = `Loading page ${index + 1} of ${pages.length}…`;
            container.appendChild(image(index, false));
            if (pages[index + 1]) { const preload = new Image(); preload.src = pages[index + 1]; }
        }
    }
    function change(delta) {
        if (mode.checked || !pages.length) return;
        const target = Math.max(0, Math.min(pages.length - 1, index + delta));
        if (target !== index) { index = target; saveProgress(); render(); }
    }
    previous.addEventListener('click', () => change(-1));
    next.addEventListener('click', () => change(1));
    container.addEventListener('touchstart', event => { touchStartX = event.changedTouches[0]?.screenX || 0; }, { passive: true });
    container.addEventListener('touchend', event => {
        if (mode.checked) return;
        const distance = (event.changedTouches[0]?.screenX || 0) - touchStartX;
        if (Math.abs(distance) >= 50) change(distance < 0 ? 1 : -1);
    }, { passive: true });
    document.addEventListener('keydown', event => {
        if (event.target.closest('input, textarea, select, button, [contenteditable]')) return;
        if (!mode.checked && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            event.preventDefault();
            if (event.key === 'Home') { index = 0; saveProgress(); render(); }
            else if (event.key === 'End') { index = pages.length - 1; saveProgress(); render(); }
            else change(event.key === 'ArrowLeft' ? -1 : 1);
        }
    });
    window.addEventListener('scroll', () => {
        if (!mode.checked) return;
        const images = [...container.querySelectorAll('img')];
        const visible = images.findIndex(img => img.getBoundingClientRect().bottom > window.innerHeight * .25);
        if (visible >= 0 && visible !== index) { index = visible; saveProgress(); }
        try { localStorage.setItem(`mangaka-reader:${cap}`, JSON.stringify({ page: index, total: pages.length, scroll: window.scrollY, savedAt: Date.now() })); } catch { /* Optional. */ }
    }, { passive: true });
    mode.addEventListener('change', () => {
        try { localStorage.setItem('mode', mode.checked ? 'scroll' : 'páginas'); } catch { /* Optional. */ }
        render();
    });
    document.addEventListener('visibilitychange', () => { if (document.hidden) { clearTimeout(saveTimer); sendProgress(); } });
    render();
});
