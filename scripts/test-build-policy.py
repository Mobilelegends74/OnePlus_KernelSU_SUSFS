#!/usr/bin/env python3
"""Offline release resolution and cache retention regressions."""
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import textwrap
import zipfile
from pathlib import Path
from unittest.mock import Mock

root = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('resolver', root / 'scripts/resolve-nomount-stable.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sha = 'a' * 40
for annotated in (False, True):
    refs = sha + '\trefs/tags/v9.1.0\n'
    if annotated:
        refs += 'b' * 40 + '\trefs/tags/v9.1.0^{}\n'
    run = Mock(side_effect=[json.dumps({'tag_name': 'v9.1.0', 'draft': False,
                                      'prerelease': False}), refs])
    result = module.resolve(run)
    assert result['nomount_tag'] == 'v9.1.0'
    assert result['nomount_sha'] == ('b' * 40 if annotated else sha)
for release in ({'tag_name': 'v1.0.0', 'draft': True, 'prerelease': False},
                {'tag_name': 'v1.0.0', 'draft': False, 'prerelease': True},
                {'tag_name': 'dev', 'draft': False, 'prerelease': False}):
    try:
        module.resolve(Mock(return_value=json.dumps(release)))
    except ValueError:
        pass
    else:
        raise AssertionError('Unsafe release accepted')
try:
    module.resolve(Mock(side_effect=[json.dumps({'tag_name': 'v1.0.0', 'draft': False,
                                                'prerelease': False}), '']))
except ValueError:
    pass
else:
    raise AssertionError('Missing tag accepted')
action = (root / '.github/actions/build-kernel/action.yml').read_text()
assert 'find "$CCACHE_DIR" -type f -mtime' not in action
assert 'touch -t $(date -d "1 day ago"' not in action
assert 'NoMount dev HEAD' not in action
assert '--branch "$NM_TAG"' in action
assert 'build-components.json' in action
workflow = (root / '.github/workflows/build-kernel-release.yml').read_text()
block = workflow.split('      - name: 📝 Generate Device List and Final Release Notes\n', 1)[1]
block = block.split('      - name: 🚀 Create GitHub Release', 1)[0]
shell = textwrap.dedent(block.split('        run: |\n', 1)[1])
def expression(match):
    name = match[0]
    if 'ksu_options_normalized)[0].type' in name:
        return 'KSUN'
    if 'ksu_options_normalized)[0].hash' in name:
        return 'dev-susfs'
    if 'ksu_resolved_hash' in name:
        return 'b' * 40
    values = {'github.repository': 'Mobilelegends74/OnePlus_KernelSU_SUSFS',
              'github.server_url': 'https://github.com', 'github.run_id': '123',
              'github.workflow': 'Build', 'inputs.clean_build': 'false',
              'inputs.optimize_level': 'O2'}
    return values[name[3:-2].strip()]
shell = re.sub(r'\$\{\{.*?\}\}', expression, shell)
with tempfile.TemporaryDirectory(prefix='kernel-release-notes-test-') as tmp:
    artifacts = Path(tmp) / 'downloaded-artifacts'
    artifacts.mkdir()
    (artifacts / 'matrix.json').write_text(json.dumps([
        {'model': 'OP13r', 'os_version': 'A15', 'susfs': True}]))
    with zipfile.ZipFile(artifacts / 'AK3_OP13r_A15_android14-6.1.118_KSUN_33455_SuSFS_2.0_UIDFAKE.zip', 'w') as z:
        z.writestr('build-components.json', json.dumps({
            'nomount_tag': 'v9.1.0', 'nomount_sha': 'a' * 40,
            'vpnhide_sha': 'c' * 40}))
    env = dict(os.environ, REPO_OWNER='Mobilelegends74', REPO_NAME='OnePlus_KernelSU_SUSFS',
               RELEASE_NAME='Test UIDFAKE', NEW_TAG='test', SUSFS_BASE_VERSION='2.0',
               GITHUB_REF_NAME='UIDFAKE-op13r-6.1.118-build80', GITHUB_SHA='d' * 40)
    subprocess.run(['bash', '-e', '-o', 'pipefail'], input=shell, text=True,
                   cwd=tmp, env=env, check=True, stdout=subprocess.DEVNULL)
    notes = (Path(tmp) / 'release_notes.md').read_text()
    assert 'HMA UIDFAKE built-in' in notes
    assert 'nomount/releases/tag/v9.1.0' in notes
    assert 'vpnhide/commit/' + 'c' * 40 in notes
    assert 'v2.1.1' not in notes
print('OK: latest stable tag, annotated tags, safe failure and cache retention')
print('OK: actual release notes render UIDFAKE and ZIP component links')
