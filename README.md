# Mangaka — Self-Hosted Manga Reader & Multi-Source Library

<p align="center"><img src="app/static/img/logo.png" alt="Mangaka logo" width="120"></p>

**Your manga library. Your server. Your reading progress.**

Mangaka is an open-source, **self-hosted manga reader and personal library**
that runs with Docker. Organize manga, manhwa, and manhua from multiple sources
and read from your computer, phone, or tablet. Your library and reading progress
belong to your installation, with continuity across providers when equivalent
chapters are available.

[![License: MIT](https://img.shields.io/badge/license-MIT-7c3aed)](LICENSE)
[![Tests](https://github.com/doarmario/mangaka/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/doarmario/mangaka/actions/workflows/tests.yml)
[![Docker installation](https://img.shields.io/badge/install-Docker-2496ed?logo=docker&logoColor=white)](#install-mangaka-with-docker)
[![GitHub stars](https://img.shields.io/github/stars/doarmario/mangaka?style=flat)](https://github.com/doarmario/mangaka/stargazers)

[Install Mangaka](#install-mangaka-with-docker) ·
[Features](#what-you-can-do-with-mangaka) ·
[Supported sources](#supported-manga-sources) ·
[Documentation](#documentation) ·
[Contribute](#contributing)

## What you can do with Mangaka

- **Search multiple manga sources together.** Browse a shared catalog and find
  matching works without choosing a provider for every search.
  Results appear progressively, so you can browse while slower sources respond.
- **Keep your place when a source changes.** Resume the same logical chapter from
  another available provider when an equivalent chapter is known.
- **Build your own reading library.** Save favorites and organize works as
  reading, plan to read, completed, paused, or dropped.
- **Read comfortably on desktop and mobile.** Use single-page or continuous-scroll
  mode, keyboard navigation, touch gestures, fullscreen, width, and brightness controls.
- **Discover and follow works.** Search tags and genres in supported catalogs
  and receive notifications for new chapters in your favorites.
- **Preserve multilingual titles.** Store original titles, translated names,
  aliases, and provider-supplied romanizations with their language and source.
- **Install and update with Docker.** One installer command prepares the services
  and enables automatic updates.

Mangaka is built for readers who want to run their own software at home. The
reader interface has no advertising or subscription billing built in. You control
the installation, accounts, configuration, and locally stored reading metadata.

## Install Mangaka with Docker

### Requirements

- Git to clone the repository.
- Docker with the Docker Compose plugin, running and accessible from your terminal.
- An internet connection for installation and access to external manga sources.
- At least 2 GB of available memory for the services.

On Windows, use Docker Desktop in **Linux containers** mode and run the commands
in PowerShell. The installer itself runs inside Docker. Windows is not currently
part of routine project testing.

### Quick start

Clone the repository and enter its directory:

```bash
git clone https://github.com/doarmario/mangaka.git
cd mangaka
```

Then run the installer:

```bash
docker compose -f compose.install.yaml run --build --rm installer
```

The installer generates configuration and passwords, retrieves the additional
source API, builds the services, prepares the database, applies migrations, and
enables automatic updates. You do not need to install Python or Node.js, edit an
`.env` file, or clone a source API separately for this installation path.

The first build can take several minutes. When it finishes, open
**[http://localhost:5000](http://localhost:5000)** and create your local account.
Keep Docker running while you read or receive updates.

For installation details, backups, and troubleshooting, see the
[self-hosting guide](docs/self-hosting.md).

### Read on your phone or tablet

To access the same library from devices on your home network, set this value in
the generated `.env` file:

```dotenv
MANGAKA_BIND_ADDRESS=0.0.0.0
```

Recreate the web service to apply the setting:

```bash
docker compose up -d web
```

Open `http://YOUR_COMPUTER_LAN_IP:5000` on a device connected to the same network.
Sign in with the same local account to use your saved library and reading progress.
The default installation binds to localhost; this setting enables network access.

## Supported manga sources

These are technical integrations with third-party websites, not partnerships
or endorsements. Integration support does not establish that a provider is
authorized to distribute its catalog. Mangaka's software license does not grant
rights to manga content; use sources and content you are authorized to access.

| Source | Integration | Reading languages |
| --- | --- | --- |
| MangaDex | MangaDex API adapter | Brazilian Portuguese, Portuguese, English |
| Asura Scans | Local Manga Novel API adapter | English |
| Qi Scans | Included Python source service | English |
| Demonic Scans | Included Python source service | English |
| Thunder Scans | Included Python source service | English |

MangaFire is available as an [optional source package](integrations/mangafire/README.md)
with English and Brazilian Portuguese chapters.

Additional compatible APIs can be installed as [source packages](docs/source-packages.md):
place a package in `sources/` and let Mangaka discover it. Packages with Docker
services are started by the installer or automatic updater, without editing the
application or the main Compose file. Open **Sources** to inspect installed packages.

The installer builds and starts the bundled source services automatically.
Catalog entries, chapter availability, genres, and pagination depend on each
provider. Source outages, request limits, or website changes can temporarily
prevent access. A healthy local source service does not guarantee that its
upstream website is available.

Chapter language preferences and title metadata are separate: Mangaka preserves
all title languages supplied by a provider, including Japanese, Korean, Chinese,
and romanized forms. It does not automatically translate titles or manga pages.

The application interface is currently in English. An interface language selector
is not available yet; Portuguese and English chapter support is unchanged.

## Reading progress that survives source changes

The same work can have different titles and provider IDs. Mangaka assigns it a
**local canonical identity** and connects the source records to that identity.
Favorites, reading status, history, and progress use the local work and logical
chapter, while providers supply the actual pages.

For example:

1. You read chapter 50 on source A and stop at page 32 of 42.
2. Source A becomes unavailable.
3. You choose **Continue reading**.
4. If source B has a mapped equivalent of chapter 50, Mangaka opens it there.
5. With 57 pages on source B, your position is approximated as page 43 of 57.

The chapter is the reliable reference; page position between editions is an
approximation. When no equivalent is available, Mangaka keeps your progress and
reports the problem instead of silently opening a different chapter.

Ambiguous matches stay separate. Matching is not a complete crawl of every
provider, and older records may need chapter metadata before they can be matched.

Read the [canonical identity and progress documentation](docs/canonical-reading.md)
for matching rules, chapter numbering, migration behavior, and limitations.

## Automatic updates and everyday maintenance

The standard installer enables the Docker-based updater. It checks for new
commits every five minutes by default and handles builds, database migration,
and service startup. No host cron job or systemd timer is needed.

Local changes or a failed deployment can interrupt updates. Check service status
and updater logs with:

```bash
# Check application services and the updater
docker compose -f compose.yaml -f compose.updater.yaml ps

# Inspect the most recent update activity
docker compose -f compose.yaml -f compose.updater.yaml logs --tail=100 auto-updater
```

Keep your `.env` file and back up your database before manual maintenance.
**Do not use `docker compose down -v` if you want to preserve your data.**

See the [automatic update guide](docs/auto-update.md) for configuration and
recovery, and the [self-hosting guide](docs/self-hosting.md) for manual updates,
backups, and deployment behind HTTPS. The installer and updater require Docker
socket access to manage services; use a trusted copy of the project.

## How Mangaka works

Flask serves the reader, MySQL stores accounts and reading metadata, and Redis
reduces repeated provider requests. Source adapters retrieve catalog information
and chapter-page URLs; a background worker checks favorites for updates.
Docker Compose manages the services.

Mangaka stores reading metadata and source mappings. It does **not** provide a
permanent manga-image archive or an offline chapter downloader.

## Documentation

The README is in English. Some linked guides and integration notes are currently
available only in Portuguese.

| Guide | What it covers |
| --- | --- |
| [Self-hosting Mangaka](docs/self-hosting.md) | Installation, local-network access, backup, restoration, and HTTPS deployment |
| [Automatic updates](docs/auto-update.md) | Updater configuration, Git behavior, permissions, and recovery |
| [Source packages](docs/source-packages.md) | Plug-and-play installation, manifests, API contract, and service lifecycle |
| [Progressive catalog loading](docs/catalog-loading.md) | Incremental results, shared cache, concurrency limits, and proxy streaming |
| [Canonical works and reading progress](docs/canonical-reading.md) | Identity, multilingual titles, matching, chapter mappings, and migrations |
| [Manga Novel API integration](integrations/manga-novel/README.md) | Local API setup and Asura adapter details |
| [Qi Scans integration](integrations/qiscans/README.md) | Source configuration and behavior |
| [Demonic Scans integration](integrations/demonicscans/README.md) | Scraper setup and limitations |
| [Thunder Scans integration](integrations/thunderscans/README.md) | Source service and chapter support |

## Frequently asked questions

### Is Mangaka free and open source?

Yes. The application is released under the MIT license. You can run your own
instance and modify the software. That license applies to the application code,
not to the manga content available through external sources.

### Can I use Mangaka without programming knowledge?

Yes. Once Git and Docker are installed, clone the repository and run the installer
command above. The installer prepares the supporting services for you.

### Can I read manga offline?

Mangaka currently needs access to external sources to retrieve pages. It saves
library and reading metadata locally, but does not download complete chapters
for permanent offline reading.

### Will switching sources keep my reading progress?

Yes, when both source records map to the same canonical work and logical chapter.
The page position is approximated if the editions have different page counts.
Unavailable or ambiguous chapter mappings do not erase your history.

### Can I host Mangaka outside my home network?

The software can run on your own server. The default setup is local; consult the
[self-hosting guide](docs/self-hosting.md) before configuring public access and HTTPS.

## Development and tests

For application development, use Python 3.13 and an isolated environment:

```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

On Windows, activate the environment with `venv\Scripts\Activate.ps1` instead.
The shell-based installer/updater tests require Bash, Git, and `jq`; run those in
a Linux environment. JavaScript reader tests run with:

```bash
node --test tests/*.test.cjs
```

The application tests use SQLite and an in-memory cache, mock upstream HTTP
responses, and block unexpected network requests. Optional MySQL tests exercise
migration and concurrency against a disposable database; see the
[database test instructions](docs/canonical-reading.md).
The source-service contract tests also run during their Docker builds.

The MangaDex dependency is pinned in `requirements.txt`. Test its adapter contract
before changing that revision. CI configuration lives in
[`.github/workflows/tests.yml`](.github/workflows/tests.yml).

## Contributing

Bug reports, documentation improvements, UI fixes, and source-adapter maintenance
are welcome. For a source issue, include the provider name, reproduction steps,
and relevant logs with credentials and personal information removed.

- [Report a bug or request a feature](https://github.com/doarmario/mangaka/issues).
- [Review open pull requests](https://github.com/doarmario/mangaka/pulls).
- Add regression tests when changing matching, reading progress, migrations, or
  provider contracts.

If Mangaka is useful to you, [star the repository](https://github.com/doarmario/mangaka)
to help other self-hosting readers discover it.

## License and content

Mangaka's application code is available under the [MIT license](LICENSE).
Bundled integrations retain their respective license and attribution files.
This repository contains software, not a manga collection, and is not affiliated
with the external content providers. Content remains subject to its owners'
rights and the sources' terms. Use the software to access content you are
authorized to read and support creators and official releases.
