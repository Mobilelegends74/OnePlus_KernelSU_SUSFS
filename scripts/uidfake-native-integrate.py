#!/usr/bin/env python3
"""Apply native hooks with checked semantic anchors; also emit a standalone patch.

No version-number dispatch: a changed kernel API is rejected with the exact
missing anchor rather than silently omitting a hook. Run twice to verify idempotence.
"""
import argparse
import difflib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def integrate(kernel, patch_path):
    changes = {}

    def edit(name, fn):
        path = kernel / name
        before = path.read_text()
        after = fn(before)
        if before != after:
            changes[name] = (before, after)

    def once(text, anchor, replacement):
        if replacement in text:
            return text
        if text.count(anchor) != 1:
            raise RuntimeError(f"expected one source anchor: {anchor!r}")
        return text.replace(anchor, replacement, 1)

    def header(text):
        inc = '#include <linux/hma_uidfake.h>\n'
        if inc not in text:
            text = inc + text
        return text

    def priority(text):
        text = header(text)
        # All priority users converge here, including the compat ABI.
        anchor = '\tcase PRIO_USER:\n'
        check = '\t\tif (hma_uidfake_hidden(who))\n\t\t\tbreak;\n'
        if text.count(anchor) != 2:
            raise RuntimeError('expected PRIO_USER in getpriority and setpriority')
        if text.count(check) == 2:
            return text
        return text.replace(anchor, anchor + check)

    def ioprio(text):
        text = header(text)
        anchor = '\t\tcase IOPRIO_WHO_USER:\n'
        check = '\t\t\tif (hma_uidfake_hidden(who))\n\t\t\t\tbreak;\n'
        if text.count(anchor) != 2:
            raise RuntimeError('expected IOPRIO_WHO_USER in get and set')
        if text.count(check) == 2:
            return text
        return text.replace(anchor, anchor + check)

    def credentials(text):
        text = header(text)
        # After validations and before publication; runs on successful commits
        # and does not replace or bypass any LSM check.
        anchor = '\trcu_assign_pointer(task->real_cred, new);'
        return once(text, anchor, '\thma_uidfake_creds(old, new);\n' + anchor)

    def file_open(text):
        text = header(text)
        anchor = '\terror = security_file_open(f);\n\tif (error)\n\t\tgoto cleanup_all;'
        return once(text, anchor, anchor + '\n\thma_uidfake_open(f);')

    edit('kernel/sys.c', priority)
    edit('block/ioprio.c', ioprio)
    edit('kernel/cred.c', credentials)
    edit('fs/open.c', file_open)
    def task_field(text):
        if 'u32 hma_uidfake_app;' in text:
            return text
        start = text.index('struct task_struct {')
        end = text.index('\n};', start)
        # Preserve offsets of existing task members on the Android ARM64 target.
        return text[:end] + '\n#ifdef CONFIG_HMA_UIDFAKE_BUILTIN\n' \
            '\t/* Fork-inherited app identity, independent of scheduler flags. */\n' \
            '\tu32 hma_uidfake_app;\n#endif' + text[end:]
    edit('include/linux/sched.h', task_field)
    edit('drivers/misc/Kconfig', lambda t: t if 'hma_uidfake/Kconfig' in t else
         t + '\nsource "drivers/misc/hma_uidfake/Kconfig"\n')
    edit('drivers/misc/Makefile', lambda t: t if 'hma_uidfake/' in t else
         t + '\nobj-$(CONFIG_HMA_UIDFAKE_BUILTIN) += hma_uidfake/\n')

    files = {'include/linux/hma_uidfake.h': ROOT / 'uidfake/hma_uidfake.h'}
    for source in (ROOT / 'uidfake/kernel').rglob('*'):
        if source.is_file():
            files['drivers/misc/hma_uidfake/' + str(source.relative_to(ROOT / 'uidfake/kernel'))] = source
    for name, source in files.items():
        dest = kernel / name
        before = dest.read_text() if dest.exists() else ''
        after = source.read_text()
        if before != after:
            changes[name] = (before, after)

    patch = []
    for name, (before, after) in changes.items():
        patch.extend(difflib.unified_diff(
            before.splitlines(True), after.splitlines(True),
            fromfile='a/' + name if before else '/dev/null', tofile='b/' + name))
    # Preflight every edit before writing any kernel source.
    for name, (_, after) in changes.items():
        dest = kernel / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(after)
    if patch_path and patch:
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(''.join(patch))
    print(f'UIDFAKE: {len(changes)} files updated; native source hooks installed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('kernel', type=Path)
    parser.add_argument('--patch', type=Path)
    args = parser.parse_args()
    integrate(args.kernel, args.patch)
