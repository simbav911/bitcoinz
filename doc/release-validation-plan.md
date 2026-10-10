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

## Running the bounded fresh-sync acceptance

Install the normal verification parameters first. The binary and its source
commit must be known, and the output directory must not already exist.

```sh
python3 contrib/devtools/validate-fresh-sync.py \
  --binary /absolute/path/to/bitcoinzd \
  --source-commit FULL_COMMIT_SHA \
  --root /absolute/path/to/new-acceptance-directory \
  --accept-historical --addnode seed.minebtcz.com:1989
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
