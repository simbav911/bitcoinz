#!/usr/bin/env python3
"""Bounded mainnet acceptance in a new datadir. Never sends or mines funds."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request

INCIDENT_HEIGHT = 1789967
INCIDENT_HASH = '0000002e04e291438a422e2d5e9d6d67ac87059afefeb03136ff9f21711bb359'


def save(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


class Run:
    def __init__(self, args):
        self.args = args
        self.root = args.root.resolve()
        # Exclusive creation prevents accidental use of an existing installation.
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.data = self.root / 'node'
        self.data.mkdir(mode=0o700)
        self.core = self.root / 'bitcoinzd'
        shutil.copy2(args.binary.resolve(), self.core)
        self.proc = None
        self.log = None
        self.phase = None
        self.stopping = False
        self.result = {
            'started_at': time.time(), 'outcome': 'running',
            'source_commit': args.source_commit,
            'daemon_sha256': hashlib.sha256(self.core.read_bytes()).hexdigest(),
            'initial_datadir_empty': True, 'copied_chain_data': False,
            'historical_option': args.accept_historical,
            'wallet_server_index': args.wallet_server_index,
            'fresh_sync_from_genesis_verified': False, 'phases': [],
        }

    def rpc(self, method, params=None, timeout=20):
        auth = base64.b64encode((self.data / '.cookie').read_bytes().strip()).decode()
        request = urllib.request.Request(
            'http://127.0.0.1:' + str(self.args.rpc_port),
            json.dumps({'id': 'acceptance', 'method': method, 'params': params or []}).encode(),
            {'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as error:
            reply = json.load(error)
        if reply.get('error'):
            raise RuntimeError(reply['error'])
        return reply['result']

    def status(self, stage, **fields):
        status = {'stage': stage, 'observed_at': time.time(), **fields}
        save(self.root / 'status.json', status)
        with (self.root / 'samples.jsonl').open('a') as output:
            output.write(json.dumps(status) + '\n')

    def check_limits(self):
        if self.stopping or (self.root / 'STOP').exists():
            raise RuntimeError('Stop requested; acceptance remains incomplete')
        if time.time() - self.result['started_at'] > self.args.hours * 3600:
            raise RuntimeError('Acceptance deadline reached')
        if shutil.disk_usage(self.root).free < self.args.min_free_gib * 1024**3:
            raise RuntimeError('Disk reserve reached')
        if self.proc is not None and self.proc.poll() is not None:
            raise RuntimeError('Core exited unexpectedly: ' + str(self.proc.returncode))

    def start(self, name, online):
        with socket.socket() as check:
            check.bind(('127.0.0.1', self.args.rpc_port))
        config = self.root / (name + '.conf')
        config.write_text(
            'server=1\nlisten=0\ndiscover=0\nupnp=0\ndisablewallet=1\n'
            'rpcbind=127.0.0.1\nrpcallowip=127.0.0.1\n'
            'rpcport=' + str(self.args.rpc_port) + '\n'
            'rpccookiefile=' + str(self.data / '.cookie') + '\n'
            'txindex=1\npar=1\ndbcache=600\nchecklevel=4\ncheckblocks=288\n'
            'experimentalaccept1789967=' + str(int(self.args.accept_historical)) + '\n' +
            ('experimentalfeatures=1\nlightwalletd=1\n' if self.args.wallet_server_index else '') +
            ('maxconnections=8\n' + ''.join('addnode=' + peer + '\n' for peer in self.args.addnode)
             if online else 'connect=0\ndnsseed=0\nmaxconnections=0\n'))
        self.phase = {'name': name, 'online': online, 'started_at': time.time()}
        self.result['phases'].append(self.phase)
        self.log = (self.root / (name + '.log')).open('w')
        self.proc = subprocess.Popen([
            str(self.core), '-datadir=' + str(self.data), '-conf=' + str(config),
            '-printtoconsole=1'], stdout=self.log, stderr=subprocess.STDOUT)
        save(self.root / 'process.json', {'runner_pid': os.getpid(), 'core_pid': self.proc.pid,
                                        'binary': str(self.core), 'data': str(self.data)})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            self.check_limits()
            try:
                info = self.rpc('getblockchaininfo')
            except (OSError, RuntimeError) as error:
                self.status(name + '_startup', rpc_error=str(error))
                time.sleep(2)
                continue
            if info['chain'] != 'main':
                raise RuntimeError('Unexpected network')
            self.phase['initial_info'] = info
            return info
        raise RuntimeError('Core startup deadline reached')

    def stop(self):
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                self.rpc('stop')
            except Exception:
                self.proc.send_signal(signal.SIGINT)
            # Never force-kill a database flush.
            self.proc.wait(timeout=600)
        self.log.close()
        self.phase['exit_code'] = self.proc.returncode
        self.phase['clean_shutdown'] = 'Shutdown: done' in (
            self.root / (self.phase['name'] + '.log')).read_text(errors='replace')
        self.phase['finished_at'] = time.time()
        self.proc = None
        save(self.root / 'result.json', self.result)
        if self.phase['exit_code'] != 0 or not self.phase['clean_shutdown']:
            raise RuntimeError('Unclean Core shutdown')

    def execute(self):
        try:
            self.start('fresh-sync', online=True)
            last_height = -1
            last_progress = time.monotonic()
            first_ready_height = None
            while True:
                self.check_limits()
                try:
                    info = self.rpc('getblockchaininfo')
                    peers = self.rpc('getpeerinfo')
                    block = self.rpc('getblock', [info['bestblockhash']])
                except (OSError, RuntimeError) as error:
                    self.status('rpc_unavailable', rpc_error=str(error))
                    if time.monotonic() - last_progress > 3600:
                        raise RuntimeError('No observable progress for one hour')
                    time.sleep(10)
                    continue
                age = time.time() - block['time']
                self.status('syncing', blocks=info['blocks'], headers=info['headers'],
                            peers=len(peers), verification_progress=info['verificationprogress'],
                            tip_age_seconds=age, free_bytes=shutil.disk_usage(self.root).free)
                if info['blocks'] != last_height:
                    last_height, last_progress = info['blocks'], time.monotonic()
                elif time.monotonic() - last_progress > 3600:
                    raise RuntimeError('Block height stalled for one hour')
                ready = (info['blocks'] > INCIDENT_HEIGHT and info['blocks'] == info['headers']
                         and len(peers) >= 2 and 0 <= age < 3600)
                if ready:
                    if first_ready_height is None:
                        first_ready_height = info['blocks']
                    elif info['blocks'] > first_ready_height:
                        break
                time.sleep(20)
            self.result['synced_info'] = info
            self.result['peers_at_tip'] = len(peers)
            if self.rpc('getblockhash', [INCIDENT_HEIGHT]) != INCIDENT_HASH:
                raise RuntimeError('Unexpected historical block hash')
            self.status('recent_verification', blocks=info['blocks'])
            if self.rpc('verifychain', [4, 288], timeout=600) is not True:
                raise RuntimeError('Recent verification failed')
            self.phase['verifychain4_recent'] = True
            height, block_hash = info['blocks'], info['bestblockhash']
            self.stop()
            restarted = self.start('offline-restart', online=False)
            if self.rpc('getconnectioncount') != 0:
                raise RuntimeError('Offline restart has peers')
            if restarted['blocks'] < height or self.rpc('getblockhash', [height]) != block_hash:
                raise RuntimeError('Restart lost verified chain progress')
            if self.rpc('verifychain', [4, 288], timeout=600) is not True:
                raise RuntimeError('Post-restart verification failed')
            self.phase['verifychain4_recent'] = True
            self.stop()
            self.result['fresh_sync_from_genesis_verified'] = True
            self.result['outcome'] = 'passed'
        except BaseException as error:
            self.result['outcome'] = 'failed_or_incomplete'
            self.result['error'] = repr(error)
        finally:
            try:
                self.stop()
            except BaseException as error:
                self.result['shutdown_error'] = repr(error)
                self.result['outcome'] = 'failed_or_incomplete'
                self.result['fresh_sync_from_genesis_verified'] = False
            self.result['finished_at'] = time.time()
            save(self.root / 'result.json', self.result)
            self.status(self.result['outcome'])
        return 0 if self.result['outcome'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True, help='Must not exist')
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--rpc-port', type=int, default=29205)
    parser.add_argument('--hours', type=float, default=24)
    parser.add_argument('--min-free-gib', type=float, default=20)
    parser.add_argument('--addnode', action='append', default=[])
    parser.add_argument('--accept-historical', action='store_true',
                        help='Explicitly opt in to the exact historical mainnet exception')
    parser.add_argument('--wallet-server-index', action='store_true',
                        help='Build the optional lightwalletd address index from genesis')
    args = parser.parse_args()
    if not args.binary.is_file() or not os.access(args.binary, os.X_OK):
        parser.error('binary must be an executable file')
    if not 1024 <= args.rpc_port <= 65535 or args.hours <= 0 or args.min_free_gib <= 0:
        parser.error('invalid port, deadline or disk reserve')
    if any('\n' in peer or '\r' in peer for peer in args.addnode):
        parser.error('addnode must be a single-line address')
    run = Run(args)
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: setattr(run, 'stopping', True))
    raise SystemExit(run.execute())


if __name__ == '__main__':
    main()
