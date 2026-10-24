# OP13R UIDFAKE — TEST-SELINUX

Experimental comparison with Actions run 39956289689. Not a stable release.

- Base branch: UIDFAKE-op13r-6.1.118-build80 at 83b7d62d2d2d7876161142e6e8dd243af86eb61f.
- KernelSU Next: d21e0a66c887ae4bc75b7c9f83e41761819ec09a (33405).
- SUSFS: c27ebe93c68e953c248b11bb747ef220ea648373 (2.3.0).
- NoMount: v2.2.0, bf1847f98fed382369c43bfd652cd93774b9b8e3.
- vpnhide: d85dc3423d6fb647f33f8c23b8d5f453c4238419.
- UIDFAKE built-in and its AnyKernel policy synchronization files are retained.

The experimental code change is KernelSU PR 3938 by 0ctobot, pinned at
ec7eb93621c40c0cc2c304cca9c0ca43b7d4c23a:
https://github.com/tiann/KernelSU/pull/3938

The patch is backported without changing its logic to the existing KernelSU
Next SELinux implementation. It checks the backup policy before the live policy,
uses stack buffers for short contexts, and retains live SID synchronization,
RCU protection and existing permission checks. It does not special-case Duck.
Long contexts retain heap allocation. Live-policy ESTALE retries reparse input.

The test workflow must use the pinned KernelSU and SUSFS commits above; it fails
if they differ. NoMount and vpnhide are pinned only on this experimental branch.
The normal branch continues resolving updates as before.

Download the AnyKernel ZIP marked UIDFAKE_TEST-SELINUX from Actions Artifacts.
Keep a known-working kernel and recovery method before flashing. Compilation
does not prove bootability or absence of SELinux regressions.

After flashing, check SELinux remains Enforcing, app behavior and UIDFAKE rules.
Compare Duck reports from several reboots/cold starts using the same settings.
Only completed parent samples (512 pairs, zero within-pair CPU migrations) are
classifiable. An inconclusive or unavailable sample is not proof of a fix.
Timing equality and absence of root detection are not guaranteed.
