#!/usr/bin/env python3
"""Resolve GitHub's latest non-prerelease NoMount tag to one immutable commit."""
import json
import re
import subprocess


def resolve(run=subprocess.check_output):
    release = json.loads(run([
        'gh', 'api', 'repos/maxsteeel/nomount/releases/latest'
    ], text=True))
    tag = release.get('tag_name', '')
    if release.get('draft') is not False or release.get('prerelease') is not False:
        raise ValueError('NoMount latest release is not a published stable release')
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', tag):
        raise ValueError('NoMount stable release tag is not a plain version: ' + tag)
    refs = run(['git', 'ls-remote', '--tags',
                'https://github.com/maxsteeel/nomount.git',
                'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'], text=True)
    refs = dict(line.split()[::-1] for line in refs.splitlines() if line.strip())
    sha = refs.get('refs/tags/' + tag + '^{}', refs.get('refs/tags/' + tag, ''))
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('NoMount release tag could not be resolved to a commit')
    return {'nomount_tag': tag, 'nomount_sha': sha,
            'nomount_release': 'https://github.com/maxsteeel/nomount/releases/tag/' + tag}


if __name__ == '__main__':
    print(json.dumps(resolve()))
