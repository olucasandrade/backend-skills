# RFC: Add Rate Limiting to the Public API

## Summary

This RFC proposes adding per-API-key rate limiting to the public REST API.

## Motivation

We currently have no rate limiting, and a single misbehaving client can
degrade the service for everyone.

## Goals

- Enforce a configurable per-key request budget.
- Return HTTP 429 with a `Retry-After` header when exceeded.

## Non-Goals

- Global (cross-key) rate limiting is out of scope.

## Design

We will use a token-bucket algorithm backed by Redis, with each API key
mapped to a bucket. The limit should be fast and should scale to our
traffic.

## Alternatives Considered

- Fixed-window counters: simpler but allows bursts at window boundaries.

## Risks

- Redis outage would need a fail-open or fail-closed decision; TBD.

## Rollback

Feature-flagged; can be disabled without a deploy.

See the current architecture diagram: ![arch](./diagrams/current.png)
And the proposed one: ![proposed](./diagrams/proposed.png)
