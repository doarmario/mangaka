# Source packages

Mangaka discovers source packages in `sources/<id>/source.json`. Installing a
compatible source does not require editing application code or `compose.yaml`.
The existing MangaDex, Asura, Qi, Demonic and Thunder integrations remain bundled.

## Install a package

1. Obtain a package from a source maintainer you trust.
2. Extract its folder into `sources/` in your Mangaka checkout.
3. Open **Sources** in Mangaka to see the detected package and validation errors.

A remote API package is discovered on the next request. If the package provides
a Docker image, the automatic updater starts it on its next successful cycle
(normally within five minutes), even if the Mangaka commit has not changed.
You can also run the usual installer immediately:

```sh
docker compose -f compose.install.yaml run --build --rm installer
```

There is no package marketplace or automatic conversion of arbitrary website
URLs. A source author must supply an API implementing the contract below, usually
backed by a scraper. Readers install that author's package; they do not need to
modify Python or Compose files. Packages are local installation settings, ignored
by Git and excluded from application image builds.

The Sources page reports configuration, not upstream website availability. A
configured provider can still be unavailable; use the Status page for API health.

## Manifest

Example `sources/example/source.json` for an existing API:

```json
{
  "schema_version": 1,
  "id": "example",
  "name": "Example Source",
  "api_url": "https://api.example.org",
  "enabled": true,
  "tags": true,
  "search": "catalog",
  "pagination": "basic",
  "chapter_languages": ["en", "pt-br", "pt"],
  "chapter_pagination": false
}
```

For an API packaged as a Docker image, replace `api_url` with:

```json
"service": {
  "image": "ghcr.io/example/source-api:1.0.0",
  "port": 3010
}
```

These names and images are examples, not published packages. The image must
listen on `0.0.0.0` at the declared port and include its own Docker `HEALTHCHECK`.
The generated service is `source-example`; its API URL becomes
`http://source-example:3010`. No host port, host folder or Docker socket is exposed
to the service. Generated services drop Linux capabilities and disallow privilege
escalation. Images must work under these restrictions; packages cannot inject
Compose commands, environment variables, mounts or privileged settings.
Use versioned tags or image digests; changing a mutable tag's contents does not
trigger deployment by itself. Change the manifest image reference to update it.

| Field | Default / meaning |
| --- | --- |
| `schema_version` | Required; integer `1` |
| `id` | Required; directory name, 1–32 lowercase letters, digits, `_` or `-`, starting with a letter |
| `name` | Required; display label, up to 80 characters |
| `api_url` | HTTP(S) base URL; alternatively provide `service` |
| `service` | Exactly `image` and integer `port` (1–65535) |
| `enabled` | `true`; set `false` to disable |
| `tags` | `false`; whether the API provides tag browsing |
| `search` | `endpoint`, `catalog` (catalog accepts `q`), or `complete` (search returns all results, paginated locally) |
| `pagination` | `basic` or `strict` (validated totals and page counts) |
| `chapter_languages` | `["en"]`; supported reading languages: `en`, `pt-br`, `pt` |
| `chapter_pagination` | `false`; enable for chapter APIs paginated in batches of 100 |

IDs must not conflict with bundled sources. Keep an ID stable across package
updates: it is part of persistent provider mappings. Unknown fields, credentials
in URLs and malformed manifests are rejected. Manifests are limited to 64 KiB.
Configuration is declarative JSON, never executable Python.

## API contract (`manga-api-v1`)

All metadata responses are JSON objects with `"source": "<package id>"`. Requests
include a `source` query parameter. Responses with a different source or an
`error` field are rejected instead of silently accepting another provider.
IDs are stable strings; URL path IDs are percent-encoded by Mangaka.

| Request | Response fields |
| --- | --- |
| `GET /api/health` | Successful HTTP status when the API is ready |
| `GET /api/manga/catalog?page=1&limit=20` | `source`, `results`, optional `total`, boolean `has_next`; accepts `q`/`tag` if supported |
| `GET /api/manga/search?q=title&page=1&limit=20` | `source`, `results`; omitted when `search` is `catalog` |
| `GET /api/manga/tags` | `source`, `tags`: `[{"id":"action","name":"Action"}]`; required when `tags` is true |
| `GET /api/manga/<id>` | `source`, work metadata below |
| `GET /api/manga/<id>/chapters?lang=en&page=1&limit=100` | `source`, `chapters`, optional `total` |
| `GET /api/manga/<id>/chapters/<chapter-id>/pages` | `source`, `pages`: image URL strings or objects with `url` |
| `GET /api/proxy/image?url=<encoded-url>` | Image bytes, handling the upstream's required headers |

Each catalog/search result needs `id` and `title`; it may supply `coverUrl`,
`aliases` and `titles`. Details can include `description`, `genres`, `tagLinks`
(`id` and `name`), `authors` (array), `artist`, `year`, `status`, `type`, `country`,
`url` and `external_ids`. Preserve multilingual `titles` using the existing
[canonical metadata contract](canonical-reading.md).

For strict pagination, also return integer `total`, `total_pages`, `page` and
`page_size`, with `total_pages = max(1, ceil(total / page_size))` and
`has_next = (page < total_pages)`. Basic search infers another page from a full
batch; use strict pagination for authoritative search totals.

Each chapter needs `id`, `number` (a string, including decimals or specials), and
optionally `title`, `volume`, `lang`. Without `lang`, the requested language is
used. Chapter pagination must return a truthful `total` or an empty final batch;
repeated pages are rejected. The adapter protects against unbounded pagination.
Image URLs must be reachable by the source service. Source API URLs must be
reachable from Mangaka's container; `localhost` inside it is not the host machine.

## Lifecycle and compatibility

The shared registry (`source_registry.py`) contains bundled definitions and the
manifest validator. The Flask facade snapshots it once per application/request
context. The generic `MangaNovel` adapter handles installed API packages; source
capabilities replace provider-specific route lists. Catalog cache signatures
include source configuration, so endpoint changes do not reuse combined results
from the old endpoint.

The installer/updater generates a restricted Compose overlay in
`.git/mangaka-update/`. It fingerprints the generated services independently of
the Git commit, starts newly configured services, and stops retired package
services after successful deployment. Containers and volumes are not deleted.
An invalid manifest blocks deployment before touching running services; the web
application skips that manifest and displays its validation error on Sources.

Set `enabled` to `false` or remove the package folder to hide it from discovery.
After the next deployment, its previously managed Docker service is stopped.
Remote APIs are never stopped by Mangaka. Canonical works, source references,
favorites, lists and reading progress remain in the database. The existing
continue-reading resolver can choose another configured source. Reinstalling a
package with the same ID reconnects its existing source references.

The default Docker setup mounts `sources/` read-only in application containers,
using the daemon's host path when launched through the containerized installer.
Keep folders traversable and manifests readable by the application's user (for
example, directory mode 755 and file mode 644 on Linux). The installer/updater
continues running Git and creating files as the checkout owner.

Old updater images without Python run the compiler using the already installed
application image, with no network and a read-only checkout mount. New installer
images include Python. For manual Compose operations involving packaged services,
include the generated overlay as well as `compose.yaml`; the installer and
updater already do this. The generated file is local state, not a file to commit.

No schema migration is needed. Existing source IDs, chapter IDs, adapter API
responses and canonical progress mappings are retained.
