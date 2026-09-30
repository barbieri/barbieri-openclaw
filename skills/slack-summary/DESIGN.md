# Slack summary design

## Problem

The extractor must turn version-tolerant slacrawl rows into coherent, model-ready conversations.
It must preserve exact Slack message identity for links while displaying local minute timestamps,
exclude bots by default, and clean only message text before applying a whole-thread limit.

## Shape

`cli.py` owns arguments and JSONL output behind the single `main` entry point. `transcript.py` owns
conversation policy, cleanup-aware limiting, and model-facing records. `slacrawl.py` owns schema
inspection, workspace-aware author resolution, bot evidence, read-only queries, and missing-root
hydration. `cleanup.py` owns the narrow disclosure rule for
email, phone, valid CPF, and secret spans. `references.py` owns Slack links and local-time rendering.

Raw Slack timestamp strings remain the source of truth for thread identity, ordering, and links.
Rounded display timestamps never feed those decisions. Cleanup happens before selection so omitted
messages do not consume the limit. `--limit` counts emitted threads, not messages. Conversations are
indivisible, so a thread with any number of replies consumes exactly one entry.

The pipeline uses generators across database loading, preparation, and record creation. The source
adapter orders thread keys by newest activity and hydrates only the current thread. Preparation
redacts before counting, skips empty threads, and stops pulling upstream after the requested number
of emitted threads. A replies list exists only while materializing one JSON object.

The public code has no database row, detector plugin, or redaction-span types. Those details stay
inside their owning modules.

## Synthesis decision

The selected design keeps one application flow while separating knowledge boundaries: slacrawl
schema adaptation, transcript policy, text cleanup, and Slack references. Source and prepared
message types are distinct so raw text cannot survive into model-facing records. A public sequence
of load/filter/redact/render stages was rejected because it would make callers preserve ordering and
privacy invariants themselves. Applying limits before cleanup was also rejected because fully
redacted messages could displace useful conversations.

## Tradeoffs accepted

- Output is newest-thread-first so limiting can stop without buffering all selected threads.
- Bot filtering removes only proven bots; unknown authorship remains to avoid discarding people.
- Thread coverage is reported as potentially incomplete because the database does not prove which
  Slack credentials populated every historical reply.
- A fully cleaned root becomes `null` while its thread link and useful replies remain.

## Private validation

Real Slack data may be used only for ephemeral, authorized local validation. Repository fixtures
must use invented authors, IDs, timestamps, and prose. A real-data finding is reduced to its
structural condition before it becomes a test.
