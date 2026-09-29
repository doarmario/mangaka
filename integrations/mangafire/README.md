# MangaFire source package

An independent `manga-api-v1` service for Mangaka's
[source package architecture](../../docs/source-packages.md). It uses MangaFire's
current public JSON API, including its request signature, rather than the obsolete
HTML/AJAX reader. No MangaDex adapter, central source list, database schema or main
Compose modification is needed.

Supported features:

- Paginated catalog, title search, genres, themes and demographics.
- Stable MangaFire title/chapter IDs, multilingual alternate titles and external
  MangaDex, AniList and MyAnimeList IDs for canonical matching.
- English and Brazilian Portuguese chapters, including decimal/special numbering.
- Chapter ownership validation and an image proxy restricted to observed CDN hosts.
- Bounded metadata cache and request cooldowns. Images are proxied on demand;
  they are not saved to disk.

## Install from this repository

The package's image is built locally from the checkout, not downloaded from a
public container registry. The installer and automatic updater discover the
bundled manifest, build the Docker context and start the service automatically.
To build it manually:

```sh
docker build -t mangaka-source-mangafire:0.1.0 integrations/mangafire
```

The updater creates `sources/mangafire/source.json` automatically when it is
missing. Manual installation remains available when needed:

```sh
mkdir -p sources/mangafire
cp integrations/mangafire/source.json sources/mangafire/source.json
```

The running automatic updater discovers, builds and starts `source-mangafire` on
its next successful cycle, even at the same Mangaka commit. To start it immediately:

```sh
docker compose -f compose.install.yaml run --build --rm installer
```

Open **Sources → MangaFire → Browse source**. The source is also included in
**All sources** and canonical alternate-source discovery. The API listens on
port 3010 inside Docker, with no port exposed on the host.

This source is bundled with the repository and is activated automatically on a
fresh installation. For future source revisions, the updater rebuilds the local
context using the version declared in the manifest. A release maintainer may
instead distribute the image through a trusted registry and set `service.image`
to that versioned image or digest.

To disable it, set `enabled` to `false` in the installed manifest or remove its
folder. The updater stops its service; canonical works and user progress remain.

## Development

```sh
cd integrations/mangafire
python -m pip install '.[test]'
python -m pytest -q
```

The Docker build runs these offline tests and verifies imports and HTTP health
as the non-root runtime user. CI also checks a build from a private-mode checkout.
The health endpoint verifies the local service; it does not query MangaFire.

The website's protocol and CDN hosts can change independently. A signature change,
upstream block or new CDN domain outside `mfcdn.nl`, `mfcdn2.xyz` and
`mfcdn3.xyz` is reported as a source error, not an empty
successful catalog. The service neither solves Cloudflare challenges nor executes
remote JavaScript. Only English and Brazilian Portuguese reading languages are
requested; all alternate titles supplied by the API are retained without guessing
their language.

This is an unofficial technical integration, not an affiliation or a grant of
rights to content. Use sources and works you are authorized to access.
