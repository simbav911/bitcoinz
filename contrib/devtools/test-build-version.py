#!/usr/bin/env python3
"""Exercise generated Git metadata through the actual C++ version formatter."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--boost-include', type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='bitcoinz-version-') as temporary:
        root = Path(temporary)
        repo = root / 'repo'
        repo.mkdir()

        def git(*arguments):
            return subprocess.check_output(['git', '-C', str(repo), *arguments], text=True).strip()

        git('init', '-q')
        git('config', 'user.name', 'Version Test')
        git('config', 'user.email', 'test@example.invalid')
        (repo / 'tracked').write_text('original\n')
        git('add', 'tracked')
        git('commit', '-qm', 'Test fixture')
        commit = git('rev-parse', '--short=12', 'HEAD')
        driver = root / 'driver.cpp'
        driver.write_text('#include "clientversion.h"\n#include <iostream>\n'
                          'int main() { std::cout << FormatFullVersion(); }\n')
        base_command = [args.cxx, '-std=c++17', '-DHAVE_BUILD_INFO', '-I' + str(root),
                        '-I' + str(source / 'src')]
        if args.boost_include:
            base_command += ['-I' + str(args.boost_include.resolve())]

        def check(name, expected, no_git=False):
            env = dict(os.environ, BITCOIN_GENBUILD_NO_GIT='1' if no_git else '0')
            subprocess.run(['sh', str(source / 'share/genbuild.sh'), str(root / 'build.h'),
                            str(repo)], env=env, check=True)
            executable = root / 'version'
            subprocess.run(base_command + [str(driver), str(source / 'src/clientversion.cpp'),
                                          '-o', str(executable)], check=True)
            actual = subprocess.check_output([str(executable)], text=True)
            if actual != expected:
                raise AssertionError(name + ': ' + repr(actual) + ' != ' + repr(expected))
            print(name + ': ' + actual, flush=True)

        # Derive the numeric prefix from the no-Git build rather than hardcoding a release.
        (root / 'build.h').write_text('// No build information available\n')
        subprocess.run(base_command + [str(driver), str(source / 'src/clientversion.cpp'),
                                      '-o', str(root / 'version')], check=True)
        fallback = subprocess.check_output([str(root / 'version')], text=True)
        if not fallback.endswith('-unk'):
            raise AssertionError('Expected explicit unknown provenance for a build without Git')
        prefix = fallback[:-4]
        check('untagged commit', prefix + '-g' + commit)
        git('tag', '-a', 'v9.8.7-test', '-m', 'Test tag')
        check('clean tag', 'v9.8.7-test')
        (repo / 'tracked').write_text('changed\n')
        check('dirty tagged checkout', prefix + '-g' + commit + '-dirty')
        check('Git explicitly disabled', fallback, no_git=True)


if __name__ == '__main__':
    main()
