---
owner: '@inder'
---
# Trusted signing keys

This file lists the GPG public keys whose signatures `tools/sync_harness.py`
will accept on harness tags. To trust a new key, import it with `gpg
--import`, optionally raise its trust level (`gpg --edit-key <id>` →
`trust`), then re-run `make harness-sync`.

## Active

### `ai-harness signer` <ai-harness@local>

- **Fingerprint:** `B73C 1FBA 35B8 E799 0EC5  53B1 73A7 AF8F 04F4 0EC9`
- **Long ID:** `73A7AF8F04F40EC9`
- **Algorithm:** Ed25519 (eddsa)
- **First used:** v1.0.2

```
-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEae924hYJKwYBBAHaRw8BAQdArvEE7oo3QdvSdCQZcuTW+mRrbWOal42Io3gG
mJD71Aa0JGFpLWhhcm5lc3Mgc2lnbmVyIDxhaS1oYXJuZXNzQGxvY2FsPoi1BBMW
CgBdFiEEtzwfujW455kOxVOxc6evjwT0DskFAmnvduIbFIAAAAAABAAObWFudTIs
Mi41KzEuMTIsMCwzAhsDBQkDwmcABQsJCAcCAiICBhUKCQgLAgQWAgMBAh4HAheA
AAoJEHOnr48E9A7J57oA/RXu7xL6D5wgpcNnn9o/v2DC5OMVLyR//cAhgILDb7I/
AP4znrQ+YkWugbr36uRMX7y8bx/zmZLPZGEDe1VDBI7YBA==
=OTnY
-----END PGP PUBLIC KEY BLOCK-----
```

To import:

```bash
# Save the block above to /tmp/key.asc, then:
gpg --import /tmp/key.asc
```

To verify a tag manually:

```bash
git -C <local-clone-of-ai-harness> verify-tag v1.0.2
```

## Pinning the trust key (B15 — v1.2.0)

`git verify-tag` accepts ANY key in the consumer's local keyring, so a
maintainer who has imported many keys downgrades the trust model to
"any of those keys + write access to upstream = ship overlay code."

Since v1.2.0, `tools/sync_harness.py` accepts a `--trust-key
<FINGERPRINT>` flag (or `HARNESS_TRUST_KEY` env var) that requires the
tag's signature to come from the named fingerprint:

```bash
# One-shot pin (recommended for CI):
python3 tools/sync_harness.py --trust-key 73A7AF8F04F40EC9

# Repo-wide pin via env (e.g. set in your make harness-sync recipe):
HARNESS_TRUST_KEY=73A7AF8F04F40EC9 python3 tools/sync_harness.py
```

Use the **long ID** (`73A7AF8F04F40EC9`) or full fingerprint
(`B73C1FBA35B8E7990EC553B173A7AF8F04F40EC9`); the comparison is
case-insensitive and matches whatever GPG emits in its `VALIDSIG` line.

## Revoked

(none yet)
