#!/usr/bin/env bash
# Installer for api-skills — no git clone required.
#
# Usage (once published to GitHub, replace <owner> below or set
# API_SKILLS_REPO):
#   curl -fsSL https://raw.githubusercontent.com/<owner>/api-skills/main/install.sh | bash -s -- log-triage
#   curl -fsSL .../install.sh | bash -s -- log-triage rfc-review
#   curl -fsSL .../install.sh | bash -s -- --category implementation
#   curl -fsSL .../install.sh | bash -s -- --all
#
# For local testing against a checked-out copy of this repo (no network):
#   bash install.sh --local-path . log-triage
#
# Requires: bash, curl, tar, python3 (python3 is already a hard
# dependency of every skill's own scripts, so this adds nothing new).
set -euo pipefail

REPO_OWNER="${API_SKILLS_REPO:-olucasandrade/backend-skills}"
REF="${API_SKILLS_REF:-main}"
SKILLS_DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"

LOCAL_PATH=""
MODE="names"   # names | category | all
CATEGORY=""
NAMES=()

usage() {
  cat <<'EOF'
Usage:
  install.sh <skill-name> [<skill-name> ...]
  install.sh --category <requirements|design|implementation|operations>
  install.sh --all
  install.sh --local-path <dir> <skill-name> [...]   # test against a local checkout, no network

Env vars:
  API_SKILLS_REPO   owner/repo to install from (default: placeholder, set before publishing)
  API_SKILLS_REF     branch/tag to install from (default: main)
  CLAUDE_SKILLS_DIR  install destination (default: ~/.claude/skills)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --local-path)
      LOCAL_PATH="$2"; shift 2 ;;
    --category)
      MODE="category"; CATEGORY="$2"; shift 2 ;;
    --all)
      MODE="all"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      NAMES+=("$1"); shift ;;
  esac
done

if [ "$MODE" = "names" ] && [ "${#NAMES[@]}" -eq 0 ]; then
  echo "No skill(s) specified." >&2
  usage
  exit 1
fi

WORKDIR=""
cleanup() {
  if [ -n "$WORKDIR" ] && [ -d "$WORKDIR" ]; then
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

if [ -n "$LOCAL_PATH" ]; then
  SRC_ROOT="$(cd "$LOCAL_PATH" && pwd)"
else
  echo "Downloading api-skills (${REPO_OWNER}@${REF})..." >&2
  WORKDIR="$(mktemp -d)"
  TARBALL_URL="https://codeload.github.com/${REPO_OWNER}/tar.gz/refs/heads/${REF}"
  curl -fsSL "$TARBALL_URL" -o "$WORKDIR/repo.tar.gz"
  tar -xzf "$WORKDIR/repo.tar.gz" -C "$WORKDIR"
  # GitHub tarballs extract into a single top-level dir named
  # "<repo>-<ref-with-slashes-replaced>" — find it rather than hardcode it.
  SRC_ROOT="$(find "$WORKDIR" -mindepth 1 -maxdepth 1 -type d | head -n1)"
fi

MANIFEST="$SRC_ROOT/MANIFEST.json"
if [ ! -f "$MANIFEST" ]; then
  echo "MANIFEST.json not found at $MANIFEST — corrupt download or wrong --local-path?" >&2
  exit 1
fi

all_skill_names() {
  python3 -c "
import json
with open('$MANIFEST') as f:
    data = json.load(f)
for name in data['skills']:
    print(name)
"
}

resolve_names_for_category() {
  python3 -c "
import json, sys
with open('$MANIFEST') as f:
    data = json.load(f)
cat = sys.argv[1]
names = [n for n, s in data['skills'].items() if s['category'] == cat]
if not names:
    sys.exit('No skills found in category: ' + cat)
print('\n'.join(names))
" "$1"
}

skill_paths() {
  # prints: <skill_path>\n<shared_path>\n<shared_path>\n... (one shared path
  # per line, may be empty) for a given skill name.
  python3 -c "
import json, sys
with open('$MANIFEST') as f:
    data = json.load(f)
name = sys.argv[1]
if name not in data['skills']:
    sys.exit('Unknown skill: ' + name)
entry = data['skills'][name]
print(entry['path'])
for s in entry.get('shared', []):
    print(s)
" "$1"
}

case "$MODE" in
  all)
    NAMES=()
    while IFS= read -r n; do NAMES+=("$n"); done < <(all_skill_names)
    ;;
  category)
    NAMES=()
    while IFS= read -r n; do NAMES+=("$n"); done < <(resolve_names_for_category "$CATEGORY")
    ;;
esac

mkdir -p "$SKILLS_DEST"

INSTALLED=()
FAILED=()
for name in "${NAMES[@]+"${NAMES[@]}"}"; do
  set +e
  paths_output="$(skill_paths "$name" 2>&1)"
  paths_status=$?
  set -e

  if [ "$paths_status" -ne 0 ]; then
    echo "$paths_output" >&2
    echo "Available skills: $(all_skill_names | tr '\n' ' ')" >&2
    FAILED+=("$name")
    continue
  fi

  paths=()
  while IFS= read -r line; do paths+=("$line"); done <<< "$paths_output"

  skill_path="${paths[0]}"
  shared_paths=("${paths[@]:1}")

  src="$SRC_ROOT/$skill_path"
  if [ ! -d "$src" ]; then
    echo "Skipping $name: expected directory not found ($skill_path)" >&2
    continue
  fi

  dest="$SKILLS_DEST/$(basename "$skill_path")"
  rm -rf "$dest"
  cp -r "$src" "$dest"

  for shared_path in "${shared_paths[@]+"${shared_paths[@]}"}"; do
    [ -z "$shared_path" ] && continue
    shared_src="$SRC_ROOT/$shared_path"
    if [ ! -d "$shared_src" ]; then
      echo "Warning: shared dependency not found for $name: $shared_path" >&2
      continue
    fi
    mkdir -p "$SKILLS_DEST/_shared"
    if [ "$(basename "$shared_path")" = "_shared" ]; then
      # A category-level shared dir (design/_shared, implementation/_shared):
      # every skill's own sys.path resolves it to a plain "_shared" sibling
      # of the skill folder, so once installed flat into $SKILLS_DEST these
      # need to MERGE their contents into one shared "_shared" directory,
      # not nest under their own basename (which would just be "_shared"
      # again, doubling the path). Filenames don't collide across
      # categories (naming.py/rest_path.py vs. file_enum.py vs.
      # log-triage-core/), so a content merge is safe.
      cp -r "$shared_src"/. "$SKILLS_DEST/_shared/"
    else
      # A named sub-dependency (operations/_shared/log-triage-core): lands
      # as its own subdirectory under the shared dir, matching the
      # "_shared/log-triage-core/" relative path every consumer expects.
      shared_dest="$SKILLS_DEST/_shared/$(basename "$shared_path")"
      rm -rf "$shared_dest"
      cp -r "$shared_src" "$shared_dest"
    fi
  done

  INSTALLED+=("$name")
  echo "Installed: $name -> $dest" >&2
done

if [ "${#INSTALLED[@]}" -eq 0 ]; then
  echo "Nothing installed." >&2
  exit 1
fi

echo "" >&2
echo "Done. Installed ${#INSTALLED[@]} skill(s) into $SKILLS_DEST" >&2
echo "Note: skills with a shared dependency expect it at ${SKILLS_DEST}/_shared/<name> —" >&2
echo "if a skill's SKILL.md references a different relative path (e.g. ../_shared),"  >&2
echo "verify the copied layout matches what its scripts import." >&2

if [ "${#FAILED[@]}" -gt 0 ]; then
  echo "" >&2
  echo "Failed to install: ${FAILED[*]}" >&2
  exit 1
fi
