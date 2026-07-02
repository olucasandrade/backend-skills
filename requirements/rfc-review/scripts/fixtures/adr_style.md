# ADR 0012: Use Postgres for the Event Store

## Status

Accepted

## Context

We need a durable, queryable store for domain events.

## Decision

We will use Postgres with a JSONB payload column and a GIN index.

## Consequences

Query flexibility improves; write throughput is somewhat lower than a
purpose-built event store, which should be fine for current volume.
