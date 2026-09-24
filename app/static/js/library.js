document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.library-remove').forEach(button => {
        button.addEventListener('click', async () => {
            const item = button.closest('[data-manga-id]');
            if (!item || button.disabled) return;
            button.disabled = true;
            try {
                const response = await fetch(`/manga/${encodeURIComponent(item.dataset.mangaId)}/favorite`);
                if (!response.ok) throw new Error('favorite request failed');
                item.remove();
            } catch {
                button.disabled = false;
                button.textContent = 'Tentar novamente';
            }
        });
    });
});
