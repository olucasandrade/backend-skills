"""
Shared codebase file-enumeration logic for implementation/ skills
(stdlib-only Python 3).

Extracted once a second consumer (implementation/performance-review) needed
the exact same logic already built for implementation/security-review:
walk a codebase root, respect a simple fnmatch-based subset of .gitignore,
and filter out files that are never worth an LLM's attention (binaries,
vendored/generated directories, lockfiles, VCS metadata).

This module does NOT do any content-level analysis (no secrets scanning,
no pattern detection) — that stays in each skill's own script, since that
logic is specific to what each skill is looking for, not shared.
"""
import fnmatch
import os

DEFAULT_IGNORE_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out",
    "__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    "target", ".next", ".nuxt", "coverage", ".tox", ".idea", ".vscode",
}

LOCKFILE_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Gemfile.lock",
    "poetry.lock", "Cargo.lock", "composer.lock", "Pipfile.lock",
    "go.sum", "mix.lock",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz", ".tar",
    ".woff", ".woff2", ".ttf", ".eot", ".otf", ".mp4", ".mp3", ".wav",
    ".so", ".dylib", ".dll", ".exe", ".class", ".jar", ".pyc", ".o",
    ".bin", ".db", ".sqlite", ".sqlite3",
}


def load_gitignore_patterns(root):
    patterns = []
    gi_path = os.path.join(root, ".gitignore")
    if os.path.isfile(gi_path):
        with open(gi_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                patterns.append(line.rstrip("/"))
    return patterns


def matches_gitignore(rel_path, patterns):
    parts = rel_path.split(os.sep)
    for pattern in patterns:
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(os.path.basename(rel_path), pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in parts):
            return True
    return False


def is_binary_path(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in BINARY_EXTENSIONS


def enumerate_files(root, extra_ignore):
    """Walk root, returning (files, skipped) where files is a sorted list
    of reviewable relative paths and skipped is a dict of
    {"vendor": [], "binary": [], "lockfile": [], "gitignored": []}
    (vendor is currently always empty here — directory-level exclusion
    happens via DEFAULT_IGNORE_DIRS pruning, not a reported skip list —
    kept as a key for output-shape stability across callers)."""
    gitignore_patterns = load_gitignore_patterns(root) + list(extra_ignore)
    files = []
    skipped = {"vendor": [], "binary": [], "lockfile": [], "gitignored": []}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in DEFAULT_IGNORE_DIRS and not d.startswith(".git")]
        rel_dir = os.path.relpath(dirpath, root)

        for fname in filenames:
            rel_path = fname if rel_dir == "." else os.path.join(rel_dir, fname)
            rel_path = rel_path.replace(os.sep, "/")

            if fname in LOCKFILE_NAMES:
                skipped["lockfile"].append(rel_path)
                continue
            if is_binary_path(fname):
                skipped["binary"].append(rel_path)
                continue
            if matches_gitignore(rel_path, gitignore_patterns):
                skipped["gitignored"].append(rel_path)
                continue

            abs_path = os.path.join(root, rel_path)
            try:
                with open(abs_path, "rb") as f:
                    chunk = f.read(4096)
                if b"\x00" in chunk:
                    skipped["binary"].append(rel_path)
                    continue
            except OSError:
                continue

            files.append(rel_path)

    return sorted(files), {k: sorted(v) for k, v in skipped.items()}
