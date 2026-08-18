# NOTICE — cacert.pem

`cacert.pem` in this directory is **Mozilla's CA certificate bundle**, obtained
**unmodified, byte-for-byte** from the `certifi` project.

| | |
|---|---|
| Source | https://github.com/certifi/python-certifi |
| certifi release | 2026.02.25 |
| SHA-256 | `fc9165a12403263e7ebfbdad7be7a3eac0fa5d325d3c70465f28d3690072ca28` |
| Root certificates | 137 |
| License of this file | **Mozilla Public License 2.0** (https://mozilla.org/MPL/2.0/) |

MPL-2.0 is a file-level license: it applies to `cacert.pem` only. Everything
else in this package remains under the package's own license. The file is
shipped unmodified; per MPL-2.0 §3.2(a), its source form is available at the
certifi repository above.

## Why it is here, and when it is used

The review gates verify TLS when calling the TruVerifAI backend. Normally they
use the machine's own trust store. On some machines that store is broken — the
documented case is Homebrew Python on macOS with a missing `cert.pem` symlink
(2026-08-17, `REPORT-MAC-m34-FINAL.md` §3), where Python could not verify ANY
certificate and every gate silently failed open.

**This bundle is a fallback only.** It is consulted solely when certificate
verification against the system store has already failed. A machine with a
working trust store never reads this file, which also bounds the cost of it
aging: a stale copy here can only ever affect machines that would otherwise
have no working TLS at all.

## Refreshing it (maintenance obligation)

Shipping a CA bundle is a trust decision: when Mozilla distrusts a CA, this
copy keeps trusting it until refreshed. Refresh on every release cycle, or at
minimum whenever certifi publishes a new bundle:

1. Take `cacert.pem` from the latest certifi release — unmodified.
2. Update the release/date, SHA-256 and certificate count in this NOTICE.
3. Never edit the .pem by hand: a modified file takes on MPL source-publication
   obligations that an unmodified copy does not have.

`tests/test_fail_open_reason.py` asserts the bundle parses and matches the
hash in this NOTICE, so a corrupted or silently-edited copy fails CI.
