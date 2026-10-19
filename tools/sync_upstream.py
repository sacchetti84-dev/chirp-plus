"""Bring the official CHIRP changes into this fork.

Usage:
  .venv\\Scripts\\python tools\\sync_upstream.py            # report only
  .venv\\Scripts\\python tools\\sync_upstream.py --merge    # merge + tests

It fetches the official repository, lists the new commits and the drivers
they touch, and warns about files this fork changes too (possible merge
conflicts). With --merge it merges them into the current branch (only on a
clean working tree) and runs the unit tests. It never pushes anything.
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPSTREAM_URL = 'https://github.com/kk7ds/chirp.git'
# Upstream commit this fork started from (the build next-20261016)
FORK_BASE = '832d349e'


def git(*args, check=True):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True,
                            text=True, encoding='utf-8')
    if check and result.returncode:
        sys.exit('git %s failed:\n%s' % (' '.join(args), result.stderr))
    return result.stdout.strip()


def upstream_remote():
    for line in git('remote', '-v').splitlines():
        name, url = line.split()[:2]
        if url.rstrip('/').removesuffix('.git') == \
                UPSTREAM_URL.removesuffix('.git'):
            return name
    git('remote', 'add', 'upstream', UPSTREAM_URL)
    return 'upstream'


def lines(text):
    return [line for line in text.splitlines() if line]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--merge', action='store_true',
                        help='merge the new commits and run the tests')
    parser.add_argument('--branch', default='master')
    parser.add_argument('--no-tests', action='store_true')
    args = parser.parse_args()

    remote = upstream_remote()
    target = '%s/%s' % (remote, args.branch)
    print('Fetching %s ...' % target)
    git('fetch', remote, args.branch)

    new = lines(git('log', '--oneline', 'HEAD..%s' % target))
    if not new:
        print('[ OK ] Already up to date with %s' % target)
        return 0
    print('[INFO] %i new official commits:' % len(new))
    for line in new[:30]:
        print('       ' + line)
    if len(new) > 30:
        print('       ... and %i more' % (len(new) - 30))

    incoming = set(lines(git('diff', '--name-only', 'HEAD...%s' % target)))
    ours = set(lines(git('diff', '--name-only', '%s..HEAD' % FORK_BASE)))
    drivers = sorted(f for f in incoming if f.startswith('chirp/drivers/'))
    if drivers:
        print('[INFO] Drivers changed: %s' % ', '.join(
            os.path.basename(f) for f in drivers))
    both = sorted(incoming & ours)
    if both:
        print('[WARN] Also changed by this fork (check after merging):')
        for f in both:
            print('       ' + f)

    if not args.merge:
        print('Run again with --merge to bring them in.')
        return 0

    if lines(git('status', '--porcelain', '--untracked-files=no')):
        sys.exit('[ERR ] Commit or stash your changes first.')
    result = subprocess.run(['git', 'merge', '--no-edit', target], cwd=ROOT)
    if result.returncode:
        print('[ERR ] Merge conflicts: fix the files listed by "git status" '
              'and commit, or undo with "git merge --abort".')
        return 1
    print('[ OK ] Merged %i commits' % len(new))
    if args.no_tests:
        return 0
    tests = subprocess.run([sys.executable, '-m', 'pytest', '-q',
                            '-p', 'no:cacheprovider', 'tests/unit'],
                           cwd=ROOT)
    print('[ OK ] Unit tests pass' if tests.returncode == 0 else
          '[ERR ] Unit tests fail: check before building')
    return tests.returncode


if __name__ == '__main__':
    sys.exit(main())
