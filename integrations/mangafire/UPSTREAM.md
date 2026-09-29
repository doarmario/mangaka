# Protocol provenance

The API shapes were checked against MangaFire's public browser client and live
JSON responses on 2026-09-29 UTC:

- Website: https://mangafire.to/
- Public routes: `/api/titles`, `/api/titles/<hid>`,
  `/api/titles/<hid>/chapters`, `/api/chapters/<id>` and `/api/filter-options`.
- Public client observed: build `b9f1b44d74fe434ccfa622b2205dd371`.

The request-signature stage tables and the feedback-substitution protocol were
cross-checked with the MangaFire integration in
[Haruneko](https://github.com/manga-download/haruneko/blob/master/web/src/engine/websites/MangaFire.ts),
which is released under the
[Unlicense](https://github.com/manga-download/haruneko/blob/master/UNLICENSE).
The three public protocol tables are stored in `signature_stages.json`; they are
not user credentials. `signature.py` implements the protocol for canonical,
request paths with decoded query text. Wire URLs remain percent-encoded;
array filters use explicit numeric indices and sort orders use named keys. No upstream browser script is downloaded or executed
at service runtime. Tests include fixed signature vectors verified against the
live API, in addition to synthetic API fixtures.

The Mangaka-specific transport, cache, API translation, manifest and tests are
maintained here under this repository's MIT license. No manga images or chapter
content are included in the package or its tests.
