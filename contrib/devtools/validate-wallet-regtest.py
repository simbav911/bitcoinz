#!/usr/bin/env python3
"""Exercise a new wallet using only isolated, valueless regtest coins."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True, help='Must not already exist')
    parser.add_argument('--rpc-port', type=int, default=29215)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    data = root / 'node'
    data.mkdir(mode=0o700)
    core = root / 'bitcoinzd'
    shutil.copy2(args.binary.resolve(), core)
    config = data / 'bitcoinz.conf'
    config.write_text('regtest=1\nserver=1\nlisten=0\nconnect=0\ndnsseed=0\n'
        'discover=0\nupnp=0\nmaxconnections=0\nrpcbind=127.0.0.1\nrpcallowip=127.0.0.1\n'
        'rpcport=' + str(args.rpc_port) + '\ntxindex=1\npar=1\n'
        'nuparams=5ba81b19:1\nnuparams=76b809bb:1\n')
    result = {'outcome': 'running', 'network': 'regtest', 'mainnet_transactions_sent': 0,
              'started_at': time.time(), 'daemon_sha256': hashlib.sha256(core.read_bytes()).hexdigest(),
              'phases': []}
    proc = log = phase = None

    def rpc(method, params=None, timeout=60):
        token = base64.b64encode((data / 'regtest/.cookie').read_bytes().strip()).decode()
        req = urllib.request.Request('http://127.0.0.1:' + str(args.rpc_port),
            json.dumps({'id': 'regtest-wallet', 'method': method, 'params': params or []}).encode(),
            {'Authorization': 'Basic ' + token, 'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                reply = json.load(response)
        except urllib.error.HTTPError as error:
            reply = json.load(error)
        if reply.get('error'):
            raise RuntimeError(reply['error'])
        return reply['result']

    def start(name):
        nonlocal proc, log, phase
        with socket.socket() as check:
            check.bind(('127.0.0.1', args.rpc_port))
        phase = {'name': name}
        result['phases'].append(phase)
        log = (root / (name + '.log')).open('w')
        proc = subprocess.Popen([str(core), '-datadir=' + str(data), '-printtoconsole=1'],
                                stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError('Core exited before readiness')
            try:
                info = rpc('getblockchaininfo')
            except (RuntimeError, OSError):
                time.sleep(1)
                continue
            if info['chain'] != 'regtest' or rpc('getconnectioncount') != 0:
                raise RuntimeError('Regtest isolation check failed')
            rpc('getwalletinfo')  # Fail if this is a wallet-disabled build.
            return info
        raise RuntimeError('Regtest startup deadline')

    def stop():
        nonlocal proc
        if proc is None:
            return
        if proc.poll() is None:
            try:
                rpc('stop')
            except Exception:
                proc.send_signal(signal.SIGINT)
            proc.wait(timeout=600)
        log.close()
        phase['exit_code'] = proc.returncode
        phase['clean_shutdown'] = 'Shutdown: done' in (root / (phase['name'] + '.log')).read_text()
        proc = None
        if phase['exit_code'] != 0 or not phase['clean_shutdown']:
            raise RuntimeError('Unclean regtest shutdown')

    def operation(opid):
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            operations = rpc('z_getoperationstatus', [[opid]])
            if len(operations) != 1:
                raise RuntimeError('Operation disappeared')
            item = operations[0]
            if item['status'] == 'success':
                return item['result']['txid']
            if item['status'] in ('failed', 'cancelled'):
                raise RuntimeError(item.get('error', item['status']))
            time.sleep(1)
        raise RuntimeError('Shielded operation deadline')

    def interrupted(*_):
        raise KeyboardInterrupt('Stop requested')

    signal.signal(signal.SIGTERM, interrupted)
    try:
        start('wallet-send')
        rpc('generate', [101], timeout=300)
        source = rpc('z_getnewaddress', ['sapling'])
        recipient = rpc('z_getnewaddress', ['sapling'])
        shield = rpc('z_shieldcoinbase', ['*', source, 0.0001, 1])
        result['shield_txid'] = operation(shield['opid'])
        rpc('generate', [1])
        if rpc('z_getbalance', [source]) <= 1:
            raise RuntimeError('Shielded coinbase did not arrive')
        memo = b'Core candidate wallet regression'.hex()
        result['send_txid'] = operation(rpc('z_sendmany', [source,
            [{'address': recipient, 'amount': 1, 'memo': memo}], 1, 0.0001]))
        rpc('generate', [1])
        if rpc('z_getbalance', [recipient]) != 1:
            raise RuntimeError('Sapling recipient balance mismatch')
        received = rpc('z_listreceivedbyaddress', [recipient])
        if not any(item['txid'] == result['send_txid'] and item['memo'].startswith(memo) for item in received):
            raise RuntimeError('Sapling memo was not recovered')
        if rpc('verifychain', [4, 0], timeout=300) is not True:
            raise RuntimeError('Regtest chain verification failed')
        before = rpc('getblockchaininfo')
        stop()
        after = start('wallet-restart')
        if after['bestblockhash'] != before['bestblockhash'] or rpc('z_getbalance', [recipient]) != 1:
            raise RuntimeError('Wallet/chain state changed on restart')
        if rpc('getconnectioncount') != 0:
            raise RuntimeError('Unexpected peer')
        result.update(outcome='passed', sapling_received_amount=1,
                      memo_verified=True, balance_retained_after_restart=True,
                      final_height=after['blocks'], peers=0)
    except BaseException as error:
        result.update(outcome='failed_or_incomplete', error=repr(error))
    finally:
        try:
            stop()
        except BaseException as error:
            result.update(outcome='failed_or_incomplete', shutdown_error=repr(error))
        result['finished_at'] = time.time()
        (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['outcome'] == 'passed' else 1)


if __name__ == '__main__':
    main()
