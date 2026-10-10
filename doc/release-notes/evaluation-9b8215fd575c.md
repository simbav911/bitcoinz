# Linux evaluation candidate 9b8215fd575c

This is an evaluation build for validating synchronization and recovery. Local
genesis acceptance passed; the native hosted acceptance and stable release
preparation remain incomplete. No stable version or default historical
consensus-policy change is announced here.

## What changed

- A preliminary block check no longer marks Sprout proofs as strictly verified
  in the block-validation cache.
- An explicit, default-off option permits only the identified historical
  mainnet block/transaction described in
  [historical compatibility](../historical-mainnet-compatibility.md).
  Cache repair alone rejects that block and cannot synchronize past it.
- The version output identifies the actual Git source revision.
- `getblocksubsidy` includes its documented funding-stream `address` and
  `valueZat` fields. Reward amounts and activation heights are unchanged.

## Exact package and platform

Source: `9b8215fd575c18f456c8c40e5eff19973429e62b`.
Version: `v2.2.0-g9b8215fd575c`.
Package: `bitcoinz-9b8215fd575c-linux-x86_64-evaluation.tar.gz`.
Archive SHA-256:
`359f3d437990a37326f6938fde79c8e37944b8446c26723b66fe6a7b2abe206a`.
Daemon SHA-256:
`7e5f4f440dd6e8906139c63f9e679b937db06f78c3ee16e5eed9536691ace436`.

The package contains the wallet-enabled daemon, RPC client, transaction utility,
build manifest, per-file checksums, sample configuration and recovery guide.
It was built and tested on Ubuntu 24.04 x86_64. There is no GUI in this package.
ELF inspection finds glibc 2.38 and libstdc++ `GLIBCXX_3.4.32` requirements; the
daemon also requires `CXXABI_1.3.13`. The host must provide compatible C++/libgcc
runtime libraries. Do not assume it runs on older Linux
distributions merely because they use x86_64. Other platforms and distribution
signatures have not been validated for this candidate.

The native CI artifact is available from
[the successful build](https://github.com/simbav911/bitcoinz/actions/runs/38049142520)
for its configured 14-day retention period. It is not a permanent release URL.
Verify the outer archive hash, extract it, then run `sha256sum -c SHA256SUMS`
inside the extracted directory before using its binaries.

## Validation and limitations

Native Linux CI passed the build-identification checks, 45 targeted assertions,
334 Boost cases, 55 selected GoogleTests and an isolated Sapling send/receive,
memo and wallet-restart test. Exact-archive follow-up checks passed saved-chain
opening, recent level-4 verification and independent wallet-server block/tree
queries. Saved-data recovery and deep historical verification are documented
in the [validation plan](../release-validation-plan.md).

The first native genesis attempt reached 718,619 blocks before its 2.25-hour
deadline. It retained two peers, recorded no RPC-unavailable samples, and shut
down cleanly. It did not complete full synchronization.

The exact archive subsequently passed a new-datadir genesis acceptance on Ubuntu
amd64 under ARM emulation, reaching height 1,854,011 in about 7 h 40 min. With the
historical option and wallet-server indexing enabled, it followed another block,
checked the incident hash, passed recent level-4 verification, and retained the
same chain after an offline restart. Both shutdowns were clean. An actual wallet
client then scanned 1,000 recent blocks through a wallet server using a new empty
wallet, saved/reopened it at the same height and repeated synchronization. This
does not establish funded wallet receive/send or desktop-client acceptance.

The second native hosted run (38060634630) reached the current peer tip at
1,854,030 blocks with two peers and no RPC-unavailable samples. Its 5.5-hour limit
expired while waiting for an additional block, before final verification and
restart. Core shut down cleanly, but the acceptance remains incomplete. The next
run allows 5.75 hours within the six-hour hosted job, using the same frozen
artifact. No Core runtime or historical-policy change accompanies this retry.

For evaluation, use a separate datadir and explicitly select the historical
option. Preserve an existing installation before attempting recovery. Turning
the option off does not roll back an already accepted historical block. Read
the compatibility guide before changing policy or recovering a failed index.

The candidate inherits automatic deprecation at block 1,993,192. A regular
release must review its version, support matrix, deprecation policy, signing
and all outstanding validation before publication.
