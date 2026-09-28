document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('browser-alerts');
    if (!button || !('Notification' in window)) {
        if (button) button.hidden = true;
        return;
    }
    const key = 'mangaka-notification-count';
    let previous = Number(localStorage.getItem(key) || 0);
    async function check() {
        try {
            const response = await fetch('/api/notificacoes/count', { headers: { Accept: 'application/json' } });
            if (!response.ok) return;
            const { count } = await response.json();
            if (Notification.permission === 'granted' && count > previous) {
                new Notification('Mangaka', { body: `${count - previous} new chapter(s) in your favorites.` });
            }
            previous = count;
            localStorage.setItem(key, String(count));
        } catch { /* Alerts are optional. */ }
    }
    if (Notification.permission === 'granted') button.textContent = 'Alerts enabled';
    button.addEventListener('click', async () => {
        const permission = await Notification.requestPermission();
        if (permission === 'granted') {
            button.textContent = 'Alerts enabled';
            check();
        }
    });
    check();
    window.setInterval(check, 60_000);
});
