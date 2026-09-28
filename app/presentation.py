"""Display labels, independent of persisted identities and provider content."""

READING_STATUSES = {
    'reading': 'Reading',
    'plan_to_read': 'Plan to read',
    'completed': 'Completed',
    'paused': 'Paused',
    'dropped': 'Dropped',
}

# Old installations can retain these application-generated placeholders in data.
# Translate them for display only; do not rewrite titles or chapter identities.
LEGACY_PLACEHOLDERS = {
    'Sem número': 'Unnumbered', 'sem número': 'Unnumbered',
    'Sem título': 'Untitled', 'Sem descrição': 'No description available',
    'Não informado': 'Unknown', 'Fontes indisponíveis': 'Sources unavailable',
}


def display_text(value):
    return LEGACY_PLACEHOLDERS.get(value, value) if isinstance(value, str) else value


def init_presentation(app):
    app.jinja_env.filters['display_text'] = display_text
    app.jinja_env.globals['reading_status_labels'] = READING_STATUSES
