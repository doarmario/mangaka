document.addEventListener('DOMContentLoaded', () => {
    const images = document.querySelectorAll('img[data-src]');
    const load = img => {
        img.src = img.dataset.src;
        img.removeAttribute('data-src');
    };
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => {
            entries.forEach(entry => {
                if (entry.isIntersecting) { load(entry.target); observer.unobserve(entry.target); }
            });
        }, { rootMargin: '150px' });
        images.forEach(img => observer.observe(img));
    } else { images.forEach(load); }
    document.querySelectorAll('img').forEach(img => img.addEventListener('error', () => {
        if (!img.src.endsWith('/static/img/cover-placeholder.svg')) img.src = '/static/img/cover-placeholder.svg';
    }, { once: true }));

    const toggle = document.getElementById('drop-btn');
    const mobileNav = document.getElementById('mobile-nav');
    toggle?.addEventListener('click', () => {
        mobileNav.hidden = !mobileNav.hidden;
        toggle.setAttribute('aria-expanded', String(!mobileNav.hidden));
    });
    document.addEventListener('keydown', event => {
        if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey &&
            !event.target.closest('input, textarea, select, [contenteditable]')) {
            event.preventDefault();
            document.querySelector('.nav-search input')?.focus();
        }
        if (event.key === 'Escape' && mobileNav && !mobileNav.hidden) {
            mobileNav.hidden = true;
            toggle.setAttribute('aria-expanded', 'false');
            toggle.focus();
        }
    });
    const favorite = document.getElementById('favorite-btn');
    favorite?.addEventListener('click', async () => {
        favorite.disabled = true;
        const status = document.getElementById('action-status');
        try {
            const response = await fetch(`/manga/${favorite.dataset.mangaId}/favorite`);
            if (!response.ok) throw new Error('request');
            const data = await response.json();
            if (data.status !== 'success') throw new Error('request');
            const added = data.message === 'added';
            favorite.setAttribute('aria-pressed', String(added));
            favorite.querySelector('span').textContent = added ? 'Nos favoritos' : 'Favoritar';
            status.textContent = added ? 'Adicionado aos seus favoritos.' : 'Removido dos favoritos.';
        } catch { status.textContent = 'Não foi possível salvar. Tente novamente.'; }
        finally { favorite.disabled = false; }
    });
    const sort = document.getElementById('chapter-filter');
    const chapters = document.querySelector('.chapter-list ul');
    let descending = true;
    sort?.addEventListener('click', () => {
        descending = !descending;
        const items = [...chapters.querySelectorAll('li[data-number]')];
        items.sort((a, b) => {
            const x = Number.parseFloat(a.dataset.number);
            const y = Number.parseFloat(b.dataset.number);
            if (!Number.isFinite(x)) return Number.isFinite(y) ? 1 : 0;
            if (!Number.isFinite(y)) return -1;
            return descending ? y - x : x - y;
        });
        items.forEach(item => chapters.appendChild(item));
        sort.querySelector('span').textContent = descending ? 'Mais recentes' : 'Primeiros capítulos';
    });
    const language = document.getElementById('chapter-language');
    const startReading = document.getElementById('start-reading');
    const defaultStart = startReading?.href;
    language?.addEventListener('change', () => {
        const items = [...chapters.querySelectorAll('li[data-language]')];
        items.forEach(item => { item.hidden = language.value !== 'all' && item.dataset.language !== language.value; });
        const visible = items.filter(item => !item.hidden);
        document.getElementById('chapter-language-status').textContent = `${visible.length} capítulos`;
        if (startReading) {
            if (language.value === 'all') startReading.href = defaultStart;
            else {
                const ordered = visible.slice().sort((a, b) => {
                    const x = Number.parseFloat(a.dataset.number);
                    const y = Number.parseFloat(b.dataset.number);
                    return (Number.isFinite(x) ? x : Infinity) - (Number.isFinite(y) ? y : Infinity);
                });
                if (ordered.length) startReading.href = ordered[0].querySelector('a').href;
            }
        }
    });
    const top = document.getElementById('btnTop');
    if (top) {
        const update = () => { top.hidden = window.scrollY < 500; };
        window.addEventListener('scroll', update, { passive: true });
        update();
        top.addEventListener('click', () => window.scrollTo({ top: 0,
            behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }));
    }
});
