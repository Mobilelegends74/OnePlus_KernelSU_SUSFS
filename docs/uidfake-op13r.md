# OP13R UIDFAKE experimental in-kernel integration

**Status: experimental, not yet phone-tested.** Do not replace a working kernel until a verified build exists and recovery is available.

## Baseline and provenance

- Parent release: `op13r-6.1.118-2026-10-16-build80-1`
- Parent commit: `7722c865a096efdfbbd3b221952a6f7e4636d7d8`
- Target: OnePlus 13R, OxygenOS 15, android14-6.1.118 (ARM64)
- HMA UID Fake source: `Mobilelegends74/hma-uidfake`, pinned commit `fa72fe4fa93b26a336bf8c421ba60a108a54c253` (v0.3.6-fork)
- Existing KernelSU Next/SUSFS/NoMount/other base features remain as in the branch's parent workflow.
- Build archive suffix: `_UIDFAKE.zip`.

## What is built into Image

The build copies pinned HMA UID Fake kernel sources into `drivers/misc/hma_uidfake/`, adds Kconfig and Kbuild entries, enables `CONFIG_HMA_UIDFAKE_BUILTIN=y`, and asserts that it survived `olddefconfig`.
The component is linked directly into the kernel **Image**, not shipped as `hma_uidfake.ko`.

The existing UID Fake netlink protocol still requires a userspace producer of caller/target policy. A kernel by itself cannot read encrypted Android application files or robustly parse HMA/HMA-OSS configuration.

## Automatic policy synchronization

The flash ZIP ships the pinned `sync-tool` binary from the published UID Fake v0.3.6 release and a minimal `/data/adb/service.d/97-uidfake-kernel.sh` boot script.
At flash time, AnyKernel3 installs both into `/data/adb` **only if the partition is mounted and writable**. No KernelSU module ZIP is installed; KernelSU's existing service.d runner launches the daemon. The daemon waits until credential-protected HMA data is available, watches configuration and sends policies using generic netlink.

**Important:** if recovery cannot access encrypted `/data`, the flash ZIP only installs the kernel; a warning is printed and automatic HMA synchronization cannot run. Do not report this as a fully functioning integrated installation. Flash from a booted, rooted Android kernel flasher with writable `/data/adb` to meet the zero-manual-step goal.

## Validation gates

1. GitHub Actions `Build and Release OnePlus Kernels` success on `UIDFAKE-op13r-6.1.118-build80`.
2. `CONFIG_HMA_UIDFAKE_BUILTIN=y` in final .config (checked by workflow).
3. Successful built-in link of Image, plus OP13R 6.1.118 checks.
4. AnyKernel ZIP contains `uidfake/sync-tool` and `uidfake/service.sh`, with `_UIDFAKE` suffix.
5. On-device tests after flashing: check `dmesg` for UID Fake initialization, no duplicate loadable module, `/data/adb/uidfake-kernel/sync.log`, HMA config reloads after unlock, correct UID masking, reboot stability and recovery.

A successful CI build **does not** prove that the hooked syscalls, reboot, HMA sync, or security checks behave correctly on a physical phone.

## Warning about legacy modules

Do not run the separate `hma-uidfake.ko` module alongside this built-in implementation: both would try to patch the same kernel interfaces. Disable/remove an existing UID Fake KernelSU module before real device testing. HMA-OSS itself remains a separate Android app/LSPosed or Zygisk implementation as required by its own configuration.
