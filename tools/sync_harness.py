#!/usr/bin/env python3
"""Pull a pinned ai-harness version into this repo.

Reads .harness-version (single ref string), shallow-clones
github.com/<owner>/ai-harness at that ref into a tempdir, verifies the
ref is a signed git tag (unless --no-verify-tag), then overlays the
harness substrate (.harness/ + the canonical tools/* files) into the
working tree. Idempotent.

Local edits to non-overlay files (root CLAUDE.md, project Makefile,
tests/harness/, project-specific *_policy.yaml additions) are preserved
because they're not in OVERLAY_PATHS.

Tag verification (H.3.6 hardening): by default the script requires the
ref to be an annotated tag signed with a key in the consumer's GPG
keyring. This blocks the "anyone with write access to the upstream
repo can ship malicious overlay code" attack. Override with
--no-verify-tag for environments without GPG configured (CI bootstraps,
fresh dev machines) — that path emits a loud WARN.

H-26: harness substrate is consumed via pinned tag from the standalone
ai-harness repo. Never hand-edit `.harness/checks` or
`.harness/generators` here — PR against the harness repo, then bump
`.harness-version`. Project-specific policy yamls and per-directory
CLAUDE.md remain in this repo.

H-25:
  Missing input    — exit 2 if .harness-version absent and --ref omitted.
  Malformed input  — exit 2 if git clone fails (bad ref or URL).
  Upstream failed  — exit 2 if git binary missing.
  Signature bad    — exit 3 if --verify-tag (default) and the tag is
                     unsigned, signed by an untrusted key, or refers to
                     a branch (not an annotated tag).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://github.com/inder1991/ai-harness.git"

OVERLAY_PATHS = (
    ".harness",
    "tools/load_harness.py",
    "tools/run_validate.py",
    "tools/run_harness_regen.py",
    "tools/refresh_baselines.py",
    "tools/_session_start_hook.sh",
    "tools/install_pre_commit.sh",
    "tools/_common.py",
    "tools/generate_typecheck_baseline.py",
)

# Subpaths under .harness/ to PRESERVE during overlay (don't blow away):
# project-specific baselines + generated truth files belong to the consumer.
PRESERVE_UNDER_HARNESS = ("baselines", "generated")


def _overlay_dir(src: Path, dst: Path) -> None:
    """Replace dst with a copy of src, preserving project-specific subdirs."""
    preserved: dict[str, Path] = {}
    if dst.exists():
        for sub in PRESERVE_UNDER_HARNESS:
            sub_path = dst / sub
            if sub_path.exists():
                preserved[sub] = Path(tempfile.mkdtemp(prefix=f"sync-preserve-{sub}-")) / sub
                shutil.copytree(sub_path, preserved[sub])
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    for sub, backup in preserved.items():
        target = dst / sub
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(backup, target)
        shutil.rmtree(backup.parent, ignore_errors=True)


def _overlay_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _verify_tag(clone_dir: Path, ref: str) -> tuple[bool, str]:
    """Verify `ref` is an annotated, signed tag with a trusted signature.

    Returns (ok, message). Two checks:
      1. ref points at a tag object (not a branch / lightweight tag /
         arbitrary commit).
      2. `git verify-tag` succeeds — i.e. the tag is GPG-signed and the
         signing key is in the consumer's keyring.

    Both checks happen against the cloned tempdir (which has the tag
    fetched as part of --branch <ref>).
    """
    cat = subprocess.run(
        ["git", "cat-file", "-t", ref],
        cwd=clone_dir, capture_output=True, text=True, timeout=10,
    )
    obj_type = (cat.stdout or "").strip()
    if cat.returncode != 0 or obj_type != "tag":
        return False, (
            f"ref {ref!r} is not an annotated tag (git cat-file -t → {obj_type or '?'!r}). "
            "Sign + push an annotated tag, e.g.: "
            f"`git tag -s {ref} -m '...' && git push origin {ref}`"
        )
    verify = subprocess.run(
        ["git", "verify-tag", ref],
        cwd=clone_dir, capture_output=True, text=True, timeout=15,
    )
    if verify.returncode != 0:
        return False, (
            f"git verify-tag {ref} failed: {(verify.stderr or '').strip() or 'no signature or untrusted key'}. "
            "Either import the upstream signing key into your GPG keyring "
            "(`gpg --recv-keys <KEYID>`) or re-run with --no-verify-tag "
            "(NOT recommended for production)."
        )
    return True, (verify.stderr or verify.stdout or "").strip()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: read pin, clone, overlay."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref",
                        help="Override .harness-version with this ref (e.g. v1.0.1).")
    parser.add_argument("--git-url", default=DEFAULT_URL,
                        help="Remote ai-harness URL.")
    parser.add_argument("--no-verify-tag", action="store_true",
                        help="Skip GPG signature verification of the tag. "
                             "DANGEROUS — only use for bootstraps without GPG configured.")
    args = parser.parse_args(argv)

    if not shutil.which("git"):
        print("[ERROR] git binary not on PATH", file=sys.stderr)
        return 2

    pin_file = REPO_ROOT / ".harness-version"
    if not pin_file.exists() and not args.ref:
        print(f"[ERROR] {pin_file} missing and --ref not supplied", file=sys.stderr)
        return 2
    ref = args.ref or pin_file.read_text(encoding="utf-8").strip()

    tmp = Path(tempfile.mkdtemp(prefix="ai-harness-sync-"))
    try:
        try:
            # B13 (v1.2.0): timeout=120 on clone — hung remote can't
            # stall sync indefinitely.
            subprocess.check_call(
                ["git", "clone", "--depth", "1", "--branch", ref,
                 args.git_url, str(tmp)],
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            print("[ERROR] git clone timed out after 120s", file=sys.stderr)
            return 2
        except subprocess.CalledProcessError as exc:
            print(f"[ERROR] git clone failed: {exc}", file=sys.stderr)
            return 2

        if args.no_verify_tag:
            print(
                f"[WARN] tag verification SKIPPED for ref={ref} (--no-verify-tag). "
                "Anyone who can write to the upstream repo can ship malicious "
                "overlay code. Re-enable verification ASAP.",
                file=sys.stderr,
            )
        else:
            ok, message = _verify_tag(tmp, ref)
            if not ok:
                print(f"[ERROR] tag verification failed: {message}", file=sys.stderr)
                return 3
            print(f"[INFO] tag {ref} signature verified: {message or 'ok'}")

        overlay_count = 0
        for rel in OVERLAY_PATHS:
            src = tmp / rel
            dst = REPO_ROOT / rel
            if not src.exists():
                continue
            if src.is_dir():
                _overlay_dir(src, dst)
            else:
                _overlay_file(src, dst)
            overlay_count += 1
        print(f"[INFO] synced harness ref={ref} into {REPO_ROOT}: {overlay_count} overlay paths")
        print("       baselines/ + generated/ preserved (project-specific).")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
