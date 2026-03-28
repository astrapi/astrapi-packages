#!/usr/bin/env bash
# release.sh – Tag setzen, pushen, Paket bauen und in GitLab-Registry hochladen.
#
# Verwendung:
#   ./release.sh 26.3.2
#
# Credentials in .release.env (wird nicht committed):
#   GITLAB_PROJECT_ID=12345678
#   GITLAB_TOKEN_NAME=pypi-publish
#   GITLAB_TOKEN_SECRET=gldt-xxxxxxxxxxxx
set -euo pipefail

# ── Credentials laden ──────────────────────────────────────────────────────────
RELEASE_ENV="$(dirname "$0")/.release.env"
if [[ -f "$RELEASE_ENV" ]]; then
    # shellcheck source=/dev/null
    source "$RELEASE_ENV"
fi

GITLAB_PROJECT_ID="${GITLAB_PROJECT_ID:?Bitte GITLAB_PROJECT_ID in .release.env setzen}"
GITLAB_TOKEN_NAME="${GITLAB_TOKEN_NAME:?Bitte GITLAB_TOKEN_NAME in .release.env setzen}"
GITLAB_TOKEN_SECRET="${GITLAB_TOKEN_SECRET:?Bitte GITLAB_TOKEN_SECRET in .release.env setzen}"

# ── Version aus Argument ───────────────────────────────────────────────────────
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    echo "Verwendung: $0 <version>  (z.B. $0 26.3.2)" >&2
    exit 1
fi
TAG="v${VERSION}"

# ── Prüfungen ─────────────────────────────────────────────────────────────────
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Fehler: uncommitted changes vorhanden. Bitte erst committen." >&2
    exit 1
fi

if git tag | grep -qx "$TAG"; then
    echo "Fehler: Tag $TAG existiert bereits." >&2
    exit 1
fi

EXISTING_TAG="$(git tag --points-at HEAD | head -1)"
if [[ -n "$EXISTING_TAG" ]]; then
    echo "Fehler: HEAD hat bereits Tag '$EXISTING_TAG'. Bitte erst committen." >&2
    exit 1
fi

# ── Tag setzen und pushen ──────────────────────────────────────────────────────
echo "→ Setze Tag $TAG …"
git tag "$TAG"
git push
git push --tags
echo "  ✓ Gepusht"

# ── Paket bauen ───────────────────────────────────────────────────────────────
echo "→ Baue Paket …"
rm -rf dist/
python -m build --wheel --sdist
echo "  ✓ dist/ erstellt"

# ── In GitLab-Registry hochladen ──────────────────────────────────────────────
REGISTRY_URL="https://gitlab.com/api/v4/projects/${GITLAB_PROJECT_ID}/packages/pypi"
echo "→ Lade hoch nach ${REGISTRY_URL} …"
twine upload \
    --repository-url "$REGISTRY_URL" \
    --username "__token__" \
    --password "$GITLAB_TOKEN_SECRET" \
    dist/*
echo "  ✓ Fertig – packagectl==${VERSION} ist in der Registry"
