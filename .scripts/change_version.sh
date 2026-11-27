#!/usr/bin/env bash

#-----------------------------------------------------------------------------------------
# Bump project version in all relevant files, commit & tag the release, and push to remote
#-----------------------------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

# ----------------------------------------------------
# Print usage and exit if no version argument provided
# ----------------------------------------------------
if [ $# -lt 1 ]; then
  echo "Usage: $0 <new_version>"
  echo "Example: $0 1.2.3"
  exit 1
fi

NEW_VERSION="$1"

# ----------------------------------------------------------------
# Validate version format (must be x.y.z where x,y,z are integers)
# ----------------------------------------------------------------
if [[ ! "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Error: Version must follow x.y.z format (e.g., 1.2.3)"
  exit 1
fi

echo "[-] Starting version bump to $NEW_VERSION"
echo

# -------------------------------------------------------
# Validate CHANGELOG.md exists and contains version entry
# -------------------------------------------------------
if [ ! -f CHANGELOG.md ]; then
  echo "Error: CHANGELOG.md file not found."
  exit 1
fi

if ! grep -q "## \[v${NEW_VERSION}\]" CHANGELOG.md; then
  echo "Error: CHANGELOG.md does not contain '## [v${NEW_VERSION}]'."
  exit 1
fi

echo "[-] CHANGELOG.md validated for version $NEW_VERSION"
echo

# -------------------------------
# Update version in "api/main.py"
# -------------------------------
echo "[-] Updating version in 'api/main.py'..."
awk -v version="$NEW_VERSION" '
  /FastAPI\(/ { inblock=1; print; next }
  inblock && /^[[:space:]]*version *=/ {
    # No spaces around "=": keep the keyword argument ruff-formatted (CI checks it).
    sub(/version *= *"[^"]*"/, "version=\"" version "\"")
    inblock=0
  }
  { print }
' api/main.py > tmp && mv tmp api/main.py
echo "   → api/main.py updated."

# ----------------------------------
# Update version in "pyproject.toml"
# ----------------------------------
echo "[-] Updating version in 'pyproject.toml'..."
awk -v version="$NEW_VERSION" '
  /^\[project\]/ { inblock=1; print; next }
  inblock && /^version =/ {
    sub(/version = "[^"]*"/, "version = \"" version "\"")
    inblock=0
  }
  { print }
' pyproject.toml > tmp && mv tmp pyproject.toml
echo "   → pyproject.toml updated."

# -----------------------------------
# Update version in "docker-bake.hcl"
# -----------------------------------
echo "[-] Updating version in 'docker-bake.hcl'..."
awk -v version="$NEW_VERSION" '
  /variable "VERSION_TAG"/ {inblock=1}
  inblock && /default =/ {
    sub(/default = "[^"]*"/, "default = \"" version "\"")
    inblock=0
  }
  {print}
' docker-bake.hcl > tmp && mv tmp docker-bake.hcl
echo "   → docker-bake.hcl updated."

# -----------------------------
# Update version in "README.md"
# -----------------------------
echo "[-] Updating version in 'README.md'..."
awk -v version="$NEW_VERSION" '
  # The Docker image tag in the "docker run" example, e.g. "protoncalendar-ro-api:1.2.3".
  { gsub(/protoncalendar-ro-api:[0-9]+\.[0-9]+\.[0-9]+/, "protoncalendar-ro-api:" version) }
  { print }
' README.md > tmp && mv tmp README.md
echo "   → README.md updated."

# --------------
# Commit changes
# --------------
echo "[-] Staging and committing version bump..."
git add -A
git commit -m "feat(version): $NEW_VERSION."
echo "   → Commit created."

# -----------
# Push commit
# -----------
echo "[-] Pushing commit to origin/develop..."
git push origin develop
echo "   → Push complete."

# -----------------------
# Create and push GIT tag
# -----------------------
echo "[-] Creating annotated tag '$NEW_VERSION'"
git tag -a "$NEW_VERSION" -m "Release $NEW_VERSION"
echo "[-] Pushing tag to origin..."
git push origin "$NEW_VERSION"
echo "   → Tag pushed."

echo
echo "[-] Version bump to $NEW_VERSION completed successfully!"