# Historical mainnet compatibility

The validation cache repair prevents a preliminary check with Sprout proof
verification disabled from satisfying a later strict check through `fChecked`.
The public historical block reported in issue #118 is rejected by strict proof
verification. Cache repair alone does not enable synchronization through it.

## Explicit historical policy

This candidate offers `experimentalaccept1789967=1` in `bitcoinz.conf` (or
`-experimentalaccept1789967=1` on the command line), disabled by default.
Use a separate datadir for evaluation and preserve the pre-test database.
The option is rejected at startup on testnet and regtest.

The exception requires mainnet, the option, and these exact identifiers:

- Block: `0000002e04e291438a422e2d5e9d6d67ac87059afefeb03136ff9f21711bb359`
  (height 1,789,967).
- Transaction: `02ee84491eee2fc6a7e1558bec4adb34f50e6fd8325378bedd3fa341db5e692d`.

Only Sprout proof verification for that transaction in that block is omitted.
PoW and Merkle/body binding are mandatory even for partial-check callers.
The existing other checks, contextual validation and pool accounting remain.
Standalone transaction validation is unchanged; the option is not a mempool
exception. An exception result never populates the strict validation cache.

This accepts existing history despite an invalid proof. It does not establish
that the historical withdrawal was authorized or recover funds. Disabling the
option does not remove an already-connected block or its descendants. A recent
startup check may not cover this old block; it cannot establish that the whole
database validates without the exception. Preserve the pre-test datadir rather
than treating an option toggle as a rollback procedure.

The default remains strict. Enabling the exception by default for a public
release would be an explicit historical consensus-policy change requiring
updated tests and release documentation.

## Recovering a previously stopped database

Stop Core cleanly and preserve a complete backup before trying recovery in a
separate datadir. Choose the historical policy explicitly before starting that
copy. Merely enabling the option does not clear every persisted failure state.

If the incident block still has an index entry, `reconsiderblock` can request
another validation attempt under the selected policy. If it returns RPC -5
(`Block not found`), repeating that command cannot help: startup may have removed
the insufficiently validated branch from the index. This was observed after an
isolated invalidation and restart at height 1,789,966. It does not by itself mean
that the saved block files have been lost.

An online node can obtain missing blocks again from peers. For offline recovery,
Core also supports importing an archive of existing block bytes with `-loadblock`:

```sh
bitcoinzd -datadir=/path/to/separate-copy \
  -experimentalaccept1789967=1 -connect=0 -dnsseed=0 -listen=0 \
  -loadblock=/path/to/parent-ordered-blocks.dat
```

The archive must retain normal block-file framing, contain unmodified block
payloads and put parents before their children. Raw `blk*.dat` file order is not
guaranteed to meet this requirement; ordinary `-loadblock` imports can skip an
unknown-parent block. A full reindex of saved block files is a separate, slower
recovery option when an ordered archive is unavailable. Do not automatically
delete chainstate or block files after a validation error.

During an import, the header height may advance before the active block height.
Wait for activation to finish, verify the expected block hashes and recent chain,
then test a clean restart. An isolated Linux test recovered all 63,798 blocks from
the incident through height 1,853,764 using unchanged saved bytes, with zero peers,
and retained the original tip hash. This is saved-data recovery evidence, not a
completed fresh sync from genesis or permission to change the default policy.

## Regression checks

The checked-in public fixture `src/test/data/bitcoinz-1789967.dat` contains eight
bytes of block-file framing followed by the 2,312-byte historical payload.
Payload SHA-256:
`ef224f10e4976746f7ce2a7fcf1ebc90b8cefcac6dec9d870d16bd74132cc741`.
Tests use it locally and do not broadcast any transaction or block.

After building with tests and installing the standard verification parameters:

```sh
cd src/test
./test_bitcoinz --run_test=CheckBlock\* --log_level=test_suite --report_level=detailed
./test_bitcoinz --log_level=error --report_level=short
cd ..
./bitcoinz-gtest --gtest_filter='CheckBlock.*:ChecktransactionTests.*:ContextualCheckBlockTest.*'
```

The tests cover strict/preliminary/disk consistency, no-JoinSplit caching,
partial checks, opt-in scope, option disabling after acceptance, wrong header,
wrong network, changed body and standalone transaction rejection. The separate
GoogleTest expectation corrections concern pre-existing reject-reason/order
expectations and an integer DoS argument; they do not alter runtime validation.

## Test plan for the next regular release

Record the exact source commit, binary checksum, platform, configuration and
results for each release candidate. Prior prototype results do not substitute
for validation of the final packaged binaries.

- Run the regression commands above and confirm startup rejects the option on
  testnet/regtest, while ordinary regtest operation remains available without it.
- In an isolated copy stopped at height 1,789,966, confirm the default rejects
  the public fixture. With opt-in, confirm that exact block connects and that
  a clean restart retains its hash. Exercise a previously failed block index as
  well as a fresh database; do not assume a flag clears persisted failure state.
- Complete a fresh-datadir mainnet sync from genesis with the selected release
  policy. Check a recent tip against peers, receipt of new blocks, peer recovery,
  orderly shutdown and restart. Also test upgrading an existing installation.
- Perform offline `verifychain 4 <depth>` across the incident and subsequent
  blocks, with adequate database cache. Verify the actual disconnected/reconnected
  count in the log: available cache may limit reconnection coverage. The opt-in
  candidate should pass; a separate strict control should reject block 1,789,967.
  The control is an expected failure, not a passing strict-validation result.
- Level-1 `verifychain` omits Sprout proofs in this version. It must not be
  reported as a full historical proof revalidation.
- Validate native builds for supported platforms, wallet/GUI operation, and
  the actual lightwalletd/client integration where distributed together.
- Include the selected historical policy, upgrade/recovery instructions,
  versioned artifacts, checksums and applicable signatures in the release.

An earlier 2.2.0-based Linux amd64 prototype (under ARM emulation, wallet/GUI
disabled) passed 45 targeted assertions, 305 Boost cases and 55 selected
GoogleTests. From a saved chain at 1,789,966 it reached the live tip, received
block 1,853,748 and restarted cleanly. Offline level-4 replay reconnected 64,071
blocks / 97,630 transactions with opt-in; the strict control rejected the
incident. A fresh sync from genesis and final multi-platform packages remain
release checks. The PR notes record validation of the branch based on master.
