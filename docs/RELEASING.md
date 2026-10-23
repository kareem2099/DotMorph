# Releasing DotMorph

One tag publishes everything:
- a GitHub Release with the AppImage, `.deb`, Arch `.pkg.tar.zst`, wheel, sdist (`.tar.gz`)
  and `PKGBUILD`, plus `SHA256SUMS`, a detached `.asc` GPG signature for every file, and the
  public key
- PyPI
- the AUR

| Release file | What it is |
|--------------|------------|
| `DotMorph-X.Y.Z-x86_64.AppImage` | everything in one file, any distro with glibc 2.28+ |
| `dotmorph_X.Y.Z-1_all.deb` | Debian 13+, Ubuntu 25.04+, Kali |
| `dotmorph-X.Y.Z-1-any.pkg.tar.zst` | Arch package, built with makepkg (`sudo pacman -U` it) |
| `dotmorph-X.Y.Z-py3-none-any.whl`, `dotmorph-X.Y.Z.tar.gz` | the wheel and sdist (also on PyPI) |
| `PKGBUILD` | the AUR recipe |
| `SHA256SUMS` | checksums of all of the above |
| `*.asc` | detached signatures, including `SHA256SUMS.asc` |
| `dotmorph-signing-key.asc` | the public key that verifies them |

PyPI doesn't take `.asc` files any more. There, the publish step uploads attestations (PEP 740)
signed by the workflow's own identity.

## One-time setup

After the first push, `.github/setup-repo.sh` sets up the repository with the `gh` CLI. It
handles:
- the description, website and 20 topics
- Discussions, merge options and labels
- private vulnerability reporting, Dependabot alerts and security fixes
- the `pypi` environment, deployable only from `v*` tags
- protection for `main`

With `--secrets` it also stores the GPG and AUR secrets; you type each one, and it goes straight
to GitHub. Run `DRY_RUN=1 .github/setup-repo.sh` to see every command first. Only the
social-preview image and the PyPI side of trusted publishing have to be done on the websites.

The steps below are what it automates, for reference:

1. **GitHub:** push the repository to `github.com/kareem2099/DotMorph` (public). The
   dotsuite.dev product page reads the README and CHANGELOG from there.
2. **PyPI (trusted publishing, no token in the repo):**
   - On pypi.org → *Your account* → *Publishing* → *Add a new pending publisher*, enter:
     - project `dotmorph`
     - owner `kareem2099`
     - repository `DotMorph`
     - workflow `release.yml`
     - environment `pypi`
   - On GitHub → *Settings* → *Environments*, create an environment named `pypi`.
3. **GPG signing (optional; without it the release has `SHA256SUMS` but no `.asc` files):**
   - Make a signing key (or use one you already have):

     ```bash
     gpg --quick-gen-key "DotMorph releases <kareem209907@gmail.com>" ed25519 sign 2y
     gpg --list-secret-keys --keyid-format long       # note the fingerprint
     ```

   - Add three repository secrets on GitHub (*Settings* → *Secrets and variables* →
     *Actions*):
     - `GPG_PRIVATE_KEY`: the output of `gpg --armor --export-secret-keys FINGERPRINT`
     - `GPG_PASSPHRASE`: its passphrase (leave it out if the key has none)
     - `GPG_KEY_ID`: the fingerprint
   - Publish the public key so people can check it independently, for example with
     `gpg --keyserver keys.openpgp.org --send-keys FINGERPRINT`. Then put the fingerprint in
     the README's "Verify your download" section. Every release also attaches it as
     `dotmorph-signing-key.asc`.
4. **AUR (optional; without it the PKGBUILD is attached to the release instead):**
   - Create an account on aur.archlinux.org and add an SSH public key to it.
   - Create the package once from an Arch machine or container:
     `git clone ssh://aur@aur.archlinux.org/dotmorph.git`, add the generated `PKGBUILD`
     and `.SRCINFO`, commit, push.
   - Put the matching private key in the repository secret `AUR_SSH_PRIVATE_KEY`.

## Every release

1. Bump the version in `pyproject.toml` and `src/dotmorph/__init__.py`.
2. Add a `## [X.Y.Z] - YYYY-MM-DD` section at the top of `CHANGELOG.md` and its link at the
   bottom.
3. Regenerate the packaging assets (desktop files, AppStream release list, man page, icons,
   completions):

   ```bash
   python packaging/build.py assets
   python packaging/build.py check      # versions agree, assets are current
   pytest -q
   ```

4. Optional dry run: GitHub → *Actions* → *Release* → *Run workflow*. It builds every
   package, smoke-tests the AppImage, and uploads everything as artifacts. It publishes
   nothing.
5. Commit, then tag and push:

   ```bash
   git tag vX.Y.Z
   git push origin main vX.Y.Z
   ```

The workflow refuses a tag that doesn't match the version.

## What the workflow does

| Job | Result |
|-----|--------|
| `test` | the CI suite (Python 3.10, 3.12, 3.13) |
| `build` | `python -m build` + `twine check`, then `.deb`, AppImage (smoke-tested: CLI, a conversion, the settings window loading), AUR files with the tag tarball's sha256, release notes from the CHANGELOG |
| `arch` | `makepkg` in an `archlinux:base-devel` container from the same PKGBUILD, `namcap`, then installs the `.pkg.tar.zst` and smoke-tests it |
| `release-files` | collects every file, writes `SHA256SUMS`, signs each file and the sums, checks every checksum and signature (this also runs in the dry run) |
| `github-release` | the release, titled `DotMorph X.Y.Z`, with every file attached |
| `pypi` | upload through trusted publishing, with attestations (after the GitHub Release succeeded) |
| `aur` | push `PKGBUILD` + `.SRCINFO` when `AUR_SSH_PRIVATE_KEY` is set |

## Building locally

```bash
python -m build                             # dist/dotmorph-X.Y.Z(.tar.gz|-py3-none-any.whl)
python packaging/build.py deb               # dist/dotmorph_X.Y.Z-1_all.deb (needs dpkg-deb)
pip install python-appimage
python packaging/build.py appimage          # dist/DotMorph-X.Y.Z-x86_64.AppImage
python packaging/build.py aur --fetch       # dist/aur/ (after the tag exists on GitHub)
python packaging/build.py notes             # release notes for the current version
python packaging/build.py sums DIR --sign   # SHA256SUMS + .asc for every file in DIR
```

The AppImage build downloads a manylinux Python AppImage and `appimagetool` (from the
python-appimage project), then installs the wheel with `PySide6-Essentials` into it.
