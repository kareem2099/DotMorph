# Security policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 2.x     | ✅ |
| 0.1.x   | ❌ |

## Reporting a vulnerability

**Please don't report security problems in public issues.**

- **Preferred:** [report privately on GitHub](https://github.com/kareem2099/DotMorph/security/advisories/new)
  (*Security* → *Report a vulnerability*).
- **Or email** [kareem209907@gmail.com](mailto:kareem209907@gmail.com) with the subject
  `[SECURITY] DotMorph`.

Please include:
- what an attacker can do, and what they need: a crafted file, local access, …
- steps or a sample file to reproduce it
- your DotMorph version and `dotmorph doctor` output

You'll get a reply within a few days. Once a fix is out, the advisory is published, with
credit to you if you want it.

## What is in scope

DotMorph runs conversion tools (ffmpeg, ImageMagick, Ghostscript, LibreOffice, pandoc, …) on
files you give it, so these matter most:
- a file name or file content that makes DotMorph run an unintended command, or write
  outside the output folder
- the daemon's socket (`$XDG_RUNTIME_DIR/dotmorph.sock`) accepting requests from other users
- desktop integration (menus, hotkey, autostart, systemd units) running something other
  than DotMorph
- release files that don't match their `SHA256SUMS` or GPG signature

Vulnerabilities inside the conversion tools themselves belong to those projects. Please report
them upstream, and tell us if DotMorph should block or work around something until it's fixed.

## Verifying releases

Every release ships `SHA256SUMS` and a detached GPG signature (`.asc`) for each file, made
with the key `0F0467813146DE68272EDC82145D345956DE18D2` (FreeRave &lt;kareem209907@gmail.com&gt;). The README
explains how to check them under *Verify your download*.
