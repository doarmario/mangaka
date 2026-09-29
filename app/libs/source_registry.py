"""One source registry per request; file packages are discovered without restart."""
from flask import current_app, g
from source_registry import registry


def definitions():
    if not hasattr(g, '_source_definitions'):
        g._source_definitions, g._source_package_errors = registry(current_app.config)
    return g._source_definitions


def package_errors():
    definitions()
    return g._source_package_errors


def source_definition(identifier):
    return definitions().get(identifier)


def source_name(identifier):
    definition = source_definition(identifier)
    return definition.name if definition else identifier


def source_api_url(identifier):
    definition = source_definition(identifier)
    return definition.endpoint(current_app.config) if definition else ''


def supports_tags(identifier):
    definition = source_definition(identifier)
    return bool(definition and definition.tags)


def visible_sources():
    return {s.id: s.name for s in definitions().values() if s.enabled and s.visible
            and (s.adapter == 'mangadex' or s.endpoint(current_app.config))}


def configuration_signature():
    return [(repr(d), d.endpoint(current_app.config)) for d in definitions().values()]
