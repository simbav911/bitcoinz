#!/usr/bin/env python3
"""Package locally built Linux binaries with explicit source/build provenance."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]

    def command(*arguments):
        return subprocess.check_output(arguments, cwd=source, text=True).strip()

    if platform.system() != 'Linux':
        parser.error('This evaluation packager supports Linux only')
    if command('git', 'status', '--porcelain', '--untracked-files=normal'):
        parser.error('Commit or move local changes before packaging')
    commit = command('git', 'rev-parse', 'HEAD')
    epoch = int(command('git', 'show', '-s', '--format=%ct', 'HEAD'))
    tag = subprocess.run(['git', 'describe', '--exact-match', '--tags', 'HEAD'],
                         cwd=source, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    files = {}
    binaries = {}
    for name in ('bitcoinzd', 'bitcoinz-cli', 'bitcoinz-tx'):
        binary = source / 'src' / name
        data = binary.read_bytes()
        if not data.startswith(b'\x7fELF'):
            parser.error(name + ' is not a Linux ELF binary')
        # The raw-transaction utility exposes its version in help only.
        version_argument = '-help' if name == 'bitcoinz-tx' else '--version'
        version = command(str(binary), version_argument).splitlines()[0]
        if '-dirty' in version or (commit[:12] not in version and not (
                tag.returncode == 0 and version.endswith(' ' + tag.stdout.strip()))):
            parser.error(name + ' does not identify this clean source revision: ' + version)
        binaries[name] = {'sha256': sha(data), 'bytes': len(data), 'version': version,
                          'version_argument': version_argument}
        files['bin/' + name] = (data, 0o755)
    configuration = command('sh', str(source / 'config.status'), '--config')
    header = (source / 'src/config/bitcoin-config.h').read_text()
    wallet_enabled = '#define ENABLE_WALLET 1' in header
    manifest = {
        'schema': 1, 'classification': 'evaluation, not a stable release',
        'source_commit': commit, 'source_timestamp': epoch,
        'platform': {'system': platform.system(), 'machine': platform.machine(),
                     'libc': platform.libc_ver()},
        'configure_arguments': configuration, 'wallet_enabled': wallet_enabled,
        'historical_exception_default': False, 'binaries': binaries,
        'validation': 'See acceptance evidence for these exact hashes; packaging is not a test pass.',
        'reproducibility': 'Archive metadata is normalized; independent binary reproduction is unverified.',
    }
    files['BUILD-MANIFEST.json'] = ((json.dumps(manifest, indent=2, sort_keys=True) + '\n').encode(), 0o644)
    for path in ('COPYING', 'doc/historical-mainnet-compatibility.md', 'doc/release-validation-plan.md'):
        files[path] = ((source / path).read_bytes(), 0o644)
    files['bitcoinz.conf.example'] = (b'# Copy to a NEW isolated datadir for evaluation.\n'
        b'server=1\nlisten=0\nrpcbind=127.0.0.1\nrpcallowip=127.0.0.1\ntxindex=1\n'
        b'# Explicit mainnet historical policy; read the included compatibility document.\n'
        b'# experimentalaccept1789967=1\n', 0o644)
    files['README.txt'] = (('BitcoinZ Linux evaluation build\n\n'
        'Source: ' + commit + '\n'
        'Wallet compiled: ' + str(wallet_enabled).lower() + '\n\n'
        'Verify the external SHA256SUMS before extracting, then the internal SHA256SUMS.\n'
        'Install the normal BitcoinZ verification parameters. Use a separate datadir.\n'
        'Copy bitcoinz.conf.example there as bitcoinz.conf and read the historical\n'
        'compatibility document before choosing the explicit option. Without it,\n'
        'strict verification rejects historical mainnet block 1789967.\n\n'
        'Run: bin/bitcoinzd -datadir=/absolute/path/to/separate-directory\n'
        'Stop: bin/bitcoinz-cli -datadir=/absolute/path/to/separate-directory stop\n\n'
        'For upgrades, stop the old process and back up its complete datadir first.\n'
        'Do not open the same datadir with two processes. Disabling the exception\n'
        'does not undo accepted history. Preserve the pre-upgrade backup.\n\n'
        'This archive is unsigned and is not a production-readiness claim.\n'
        'See BUILD-MANIFEST.json for build configuration and runtime platform.\n').encode(), 0o644)
    files['SHA256SUMS'] = (''.join(sha(data) + '  ' + name + '\n'
        for name, (data, _) in sorted(files.items())).encode(), 0o644)
    archive_name = 'bitcoinz-' + commit[:12] + '-linux-' + platform.machine() + '-evaluation.tar.gz'
    args.output.mkdir(parents=True, exist_ok=True)
    destination = args.output / archive_name
    if destination.exists():
        parser.error('Refusing to overwrite ' + str(destination))
    with tempfile.TemporaryFile() as temporary:
        with gzip.GzipFile(fileobj=temporary, mode='wb', filename='', mtime=epoch) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as archive:
                for name, (data, mode) in sorted(files.items()):
                    entry = tarfile.TarInfo(archive_name[:-7] + '/' + name)
                    entry.size, entry.mode, entry.mtime = len(data), mode, epoch
                    entry.uid = entry.gid = 0
                    entry.uname = entry.gname = 'root'
                    archive.addfile(entry, io.BytesIO(data))
        temporary.seek(0)
        data = temporary.read()
    with destination.open('xb') as output:
        output.write(data)
    checksum = sha(data) + '  ' + archive_name + '\n'
    with (args.output / (archive_name + '.sha256')).open('x') as output:
        output.write(checksum)
    print(checksum, end='')


if __name__ == '__main__':
    main()
