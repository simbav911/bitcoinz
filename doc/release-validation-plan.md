# Candidate validation plan

This branch prepares an evaluation build in the maintainer's fork. It is not a
published stable release. The historical exception remains disabled by default;
the isolated mainnet acceptance run explicitly enables it. Release policy must
be stated in the final release notes and matched by the shipped configuration.

## Established baseline

Source `a7a567c6ab4180793b7e91b3761d94892efe994d`, based on upstream
`f9047533ebabb971b92b5103efd9fdbe9eb5c3fb`, passed:

- 45 targeted assertions, 305 Boost cases and 55 selected GoogleTests.
- Strict historical rejection and opt-in level-4 replay of 64,071 blocks.
- Following the live mainnet tip and a clean offline restart.

Those tests used Linux amd64 under ARM emulation, with the wallet disabled and
a saved database. They do not establish fresh-sync, native-platform or wallet
acceptance. Revalidate any changed runtime code and record exact artifact hashes.

## Execution order and exit criteria

1. Freeze source and build inputs. Ensure `--version` identifies the source
   commit. Record compiler, configuration, platform and binary hashes; package
   only the binaries actually exercised. Deterministic packaging does not imply
   independently reproduced compiler output.
2. Synchronize a new mainnet datadir from genesis without importing blocks,
   chainstate or peer databases. Record timestamped block/header heights, peers,
   progress and errors. Pass only after reaching the recent peer tip, receiving
   another block, checking the incident hash, recent level-4 verification and
   an offline restart retaining the same chain. Default checkpoints remain on.
3. Test upgrade of a stopped existing database, peer loss/reconnection, stopping
   during startup and active synchronization, and recovery of a persisted
   failed-block index. Preserve original databases. Never prescribe automatic
   deletion of chainstate or silently relax validation after an error.
4. Exercise the final daemon through a wallet server and an independent client:
   latest block, block range, tree state, expected chain identity and accurate
   not-ready behavior before synchronization. Keep application-specific
   integration records outside this public Core repository.
5. Produce a Linux evaluation archive, checksums, source/build manifest and
   launch/upgrade instructions. Test the extracted binaries. Keep the historical
   option explicit, including its implications and rollback limitations.
6. Build and exercise wallet-enabled Core and each intended native platform.
   GUI and signed distribution checks apply only where those are shipped.
   Do not substitute emulated Linux results for native Windows/macOS coverage.
7. Before stable publication, select the version, historical policy and support
   matrix; finish all applicable checks; record remaining limitations; prepare
   signatures and final release notes. Publication is a separate action.

## Evaluation evidence added on 2026-10-10

The native Linux x86_64 evaluation artifact is frozen at source
`9b8215fd575c18f456c8c40e5eff19973429e62b`. Documentation may advance separately.
[The native CI run](https://github.com/simbav911/bitcoinz/actions/runs/38049142520)
passed all four build-identification scenarios, 45 targeted assertions, 334 Boost
cases, 55 selected GoogleTests and the isolated Sapling wallet/restart test.
The downloaded archive passed checksum, executable identity and wallet checks.

Saved-chain checks on the same runtime source (local build `d536bc7`) passed
strict historical rejection and opt-in level-4 reconnection of 64,087 blocks /
97,655 transactions. After a deliberately invalidated branch was removed from
the index at startup, offline import of 63,798 unchanged saved blocks recovered
the original tip. See the compatibility document for the absent-index case.

These results do not complete the genesis-sync, full wallet-client, other native
platform or stable-publication gates above. The explicit historical option is
still disabled by default.

## Running the bounded fresh-sync acceptance

Install the normal verification parameters first. The binary and its source
commit must be known, and the output directory must not already exist.

```sh
python3 contrib/devtools/validate-fresh-sync.py \
  --binary /absolute/path/to/bitcoinzd \
  --source-commit FULL_COMMIT_SHA \
  --root /absolute/path/to/new-acceptance-directory \
  --accept-historical --wallet-server-index --addnode seed.minebtcz.com:1989
```

The runner uses loopback cookie-authenticated RPC, disables listening and wallet
operation, reserves 20 GiB of free disk and defaults to a 24-hour deadline.
It pins a copy of the supplied executable inside the new directory. `status.json`
and `samples.jsonl` show progress; `result.json` records the final outcome.
Create `STOP` in that directory to request an orderly stop. A stopped or timed-out
run is incomplete, never a passing full-sync result. Database shutdown is given
ten minutes and is never force-killed by this runner.

Serial script checking (`par=1`) is used because the earlier emulated Linux
environment produced script failures with parallel checking. This is a test
environment workaround, not evidence of the behavior of native hardware.

`--wallet-server-index` also builds the lightwalletd address index from the start.
Omit it when evaluating a standalone Core without that index. Changing this
index setting on an existing database requires reindexing; enabling it at first
startup avoids repeating the work for later wallet-server integration.

## Build identification regression

```sh
python3 contrib/devtools/test-build-version.py \
  --boost-include depends/x86_64-pc-linux-gnu/include
```

This compiles the real version formatter using metadata generated from temporary
clean, tagged and dirty Git fixtures, plus the explicit no-Git fallback.

## Wallet acceptance on regtest

After building with wallet support and installing the verification parameters:

```sh
python3 contrib/devtools/validate-wallet-regtest.py \
  --binary /absolute/path/to/bitcoinzd \
  --root /absolute/path/to/new-wallet-acceptance-directory
```

This creates an isolated wallet, mines valueless regtest coins, shields a coinbase
output, sends between two Sapling addresses with a memo, verifies the received
balance/memo, verifies the chain and checks the balance after restart. RPC is
loopback-only and P2P is disabled. No mainnet transaction is constructed or sent.
