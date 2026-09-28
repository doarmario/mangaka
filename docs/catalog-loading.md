# Progressive catalog loading

The combined catalog and search return the page shell before contacting providers.
`GET /api/catalog/stream` sends newline-delimited JSON as sources respond. Readers
can browse early results while the remaining sources load. Each snapshot groups
cards by canonical work identity; source failures do not remove useful results.

Provider I/O is limited to three concurrent tasks per application process, with
at most six accepted tasks including queued work. Collection has a 35-second
deadline. Outstanding network calls retain their own HTTP timeouts; they are not
forcibly killed. Requests beyond the task limit are treated as unavailable for
that refresh. Reference registration and canonical identity writes run sequentially
in the coordinating request, outside the provider I/O workers.

Complete results are shared in Redis for 120 seconds; partial results for 30
seconds. Concurrent readers of the same page follow the existing refresh rather
than start another provider batch. Cache keys include the query, page, configured
sources and API endpoints, content languages and page size. No reading progress,
favorites, account details or personalized HTML enters this cache. Existing
per-provider caches and cooldowns remain active. Retrying during the partial-result
cache window can return the same snapshot until it expires.

The stream disables compression and sends `X-Accel-Buffering: no`. Reverse proxies
must preserve streaming and disable response buffering for this endpoint; otherwise
the browser may receive all results at the end. The client retains loaded results
if a stream fails and offers a retry. Without JavaScript, **Load catalog without
JavaScript** opens the conventional combined listing and preserves that mode when
paging.

The details page also checks alternative providers concurrently. **Continue reading**
tries known chapter mappings first and searches other sources only if those fail.
Failed known sources are not retried during the same continue-reading request.

Tests use a blocked slow source to verify that a fast source appears first, and
cover shared refreshes, cache isolation, deduplication, partial failures, interrupted
streams and Unicode split across network chunks. These are controlled regression
checks, not latency guarantees for external websites.
