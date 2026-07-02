#!/usr/bin/env python3
"""
Shared naming helpers for design/ generative skills (stdlib only).

Extracted once a second real consumer (rfc-to-api) needed the exact same
PascalCase-entity -> plural-snake-case-name logic that rfc-to-schema
already had. Deliberately kept minimal — only genuinely identical,
zero-risk-of-divergence logic belongs here; each skill's IR-specific
conventions (assumed-flagging, validation) stay in their own scripts.
"""

import re


def slugify_table_name(entity_name: str) -> str:
    """PascalCase entity name -> plural snake_case (BlogPost -> blog_posts)."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", entity_name).lower()
    return s if s.endswith("s") else s + "s"


def singularize(plural_snake: str) -> str:
    """Best-effort inverse of the pluralization slugify_table_name applies."""
    return plural_snake[:-1] if plural_snake.endswith("s") else plural_snake
