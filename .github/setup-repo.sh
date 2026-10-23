#!/usr/bin/env bash
# One-time GitHub setup for the DotMorph repository, with the gh CLI.
# Run it once, after the first push:
#
#     .github/setup-repo.sh            # apply the settings
#     DRY_RUN=1 .github/setup-repo.sh  # only print what it would do
#     .github/setup-repo.sh --secrets  # also store the release secrets (asks you for each)
#
# Safe to run again: every step sets a value, it doesn't add duplicates.
# The social-preview image has no API: upload docs/screenshots/banner.png by hand under
# Settings -> General -> Social preview.
set -euo pipefail

REPO="${REPO:-kareem2099/DotMorph}"
DRY_RUN="${DRY_RUN:-}"
WITH_SECRETS=""
[[ "${1:-}" == "--secrets" ]] && WITH_SECRETS=1

run() {
  if [[ -n "$DRY_RUN" ]]; then
    printf '  would run:'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

# `gh api` with a JSON body read from stdin
api() {
  local method=$1 path=$2 body=${3:-}
  if [[ -n "$DRY_RUN" ]]; then
    echo "  would run: gh api -X $method repos/$REPO/$path ${body:+<<< $body}"
  elif [[ -n "$body" ]]; then
    gh api -X "$method" "repos/$REPO/$path" --input - <<< "$body" > /dev/null
  else
    gh api -X "$method" "repos/$REPO/$path" > /dev/null
  fi
}

step() { printf '\n\033[1;32m==>\033[0m %s\n' "$*"; }

if [[ -z "$DRY_RUN" ]]; then
  gh auth status > /dev/null
  gh repo view "$REPO" --json name > /dev/null || {
    echo "$REPO does not exist yet. Push it first, for example:"
    echo "  gh repo create $REPO --public --source . --push"
    exit 1
  }
fi

step "Description, website and features"
run gh repo edit "$REPO" \
  --description "Radial-menu file converter for Linux: 440+ conversions for images, PDF, SVG, video, audio, Office and Markdown. Edge dock, global hotkey, file-manager menus. Part of DotSuite." \
  --homepage "https://dotsuite.dev/en/product/dotmorph" \
  --enable-issues --enable-discussions \
  --enable-wiki=false --enable-projects=false \
  --enable-squash-merge --enable-merge-commit=false --enable-rebase-merge \
  --delete-branch-on-merge --allow-update-branch

step "Topics (what GitHub search and Explore use)"
run gh repo edit "$REPO" \
  --add-topic linux,file-converter,converter,radial-menu,pdf,image-converter \
  --add-topic video-converter,audio-converter,ffmpeg,imagemagick,libreoffice,pandoc \
  --add-topic pyside6,qml,qt6,gnome,wayland,nautilus,appimage,dotsuite

step "Labels used by the issue forms and Dependabot"
label() {  # name colour description
  if [[ -n "$DRY_RUN" ]]; then
    echo "  would create label: $1"
  else
    gh label create "$1" --repo "$REPO" --color "$2" --description "$3" --force > /dev/null
  fi
}
label bug           d73a4a "Something doesn't convert, open or look right"
label enhancement   10b981 "A new format, tool or idea"
label packaging     5319e7 "AppImage, .deb, AUR, PyPI, release workflow"
label translation   fbca04 "Arabic or another language, right-to-left"
label wayland       1d76db "Wayland / XWayland behaviour"
label ci            ededed "GitHub Actions (Dependabot)"
label deps          ededed "Python dependencies (Dependabot)"
label "good first issue" 7057ff "A good place to start contributing"

step "Security: private vulnerability reports (SECURITY.md points here), Dependabot alerts and fixes"
api PUT private-vulnerability-reporting
api PUT vulnerability-alerts
api PUT automated-security-fixes

step "Environment 'pypi' for trusted publishing, only deployable from v* tags"
api PUT environments/pypi '{"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}'
if [[ -n "$DRY_RUN" ]] || ! gh api "repos/$REPO/environments/pypi/deployment-branch-policies" \
    --jq '.branch_policies[].name' 2>/dev/null | grep -qx 'v\*'; then
  api POST environments/pypi/deployment-branch-policies '{"name": "v*", "type": "tag"}'
fi

step "Protect main: CI must pass, no force-pushes or deletion (you, as admin, can still push)"
api PUT branches/main/protection '{
  "required_status_checks": {"strict": false,
    "contexts": ["test (3.10)", "test (3.12)", "test (3.13)"]},
  "enforce_admins": false,
  "required_pull_request_reviews": null,
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}'

if [[ -n "$WITH_SECRETS" && -n "$DRY_RUN" ]]; then
  step "Release secrets"
  echo "  (skipped in a dry run: it would ask for the GPG fingerprint, passphrase and AUR key)"
elif [[ -n "$WITH_SECRETS" ]]; then
  step "Release secrets (typed by you, sent straight to GitHub; nothing is stored here)"
  read -r -p "GPG key fingerprint for signing releases (empty to skip): " key
  if [[ -n "$key" ]]; then
    gpg --armor --export-secret-keys "$key" | run gh secret set GPG_PRIVATE_KEY --repo "$REPO"
    run gh secret set GPG_KEY_ID --repo "$REPO" --body "$key"
    echo "GPG passphrase (empty if the key has none). gh asks for it without echoing:"
    run gh secret set GPG_PASSPHRASE --repo "$REPO"
  fi
  read -r -p "Path to the AUR SSH private key (empty to skip): " aur
  if [[ -n "$aur" ]]; then
    run gh secret set AUR_SSH_PRIVATE_KEY --repo "$REPO" < "${aur/#\~/$HOME}"
  fi
fi

step "Done"
secrets_hint=""
[[ -z "$WITH_SECRETS" ]] && secrets_hint="  - Release secrets: run  .github/setup-repo.sh --secrets  (GPG signing, AUR)"
cat <<EOF
Still by hand (no API):
  - Social preview: Settings -> General -> Social preview -> upload docs/screenshots/banner.png
  - PyPI trusted publisher: pypi.org -> Publishing -> add pending publisher
    (dotmorph / kareem2099 / DotMorph / release.yml / environment pypi). See docs/RELEASING.md.
$secrets_hint
EOF
