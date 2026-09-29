"""Request signing for MangaFire's public reader API (see UPSTREAM.md)."""
import base64
import json
from importlib.resources import files
from urllib.parse import urlencode, unquote_plus

STAGES = tuple((base64.b64decode(table), base64.b64decode(key), initial)
               for table, key, initial in json.loads(
                   files(__package__).joinpath('signature_stages.json').read_text()))


def signed_path(path, params=()):
    query = urlencode(sorted(params))
    # The current API signs decoded query text; the wire URL stays escaped.
    payload = (path + ('?' + unquote_plus(query) if query else '')).encode('utf-8')
    for table, key, previous in STAGES:
        output = bytearray()
        for index, value in enumerate(payload):
            previous = table[value ^ key[index % len(key)] ^ previous]
            output.append(previous)
        payload = bytes(output)
    token = base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')
    return '/api' + path + '?' + (query + '&' if query else '') + 'vrf=' + token
