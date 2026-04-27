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

## Revoked

(none yet)
