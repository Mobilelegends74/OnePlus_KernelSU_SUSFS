# KernelSU SELinux timing backport

Source: https://github.com/tiann/KernelSU/pull/3938 by 0ctobot.
Pinned revision: ec7eb93621c40c0cc2c304cca9c0ca43b7d4c23a.

Backported to pershoot/KernelSU-Next dev-susfs. The original patch logic is
unchanged: validate against the backup policy before consulting the live policy,
use stack buffers for short contexts, retain live SID synchronization and RCU,
and retry live-policy ESTALE after reparsing. Permission checks are retained.
This does not special-case a detector or disable SELinux enforcement.

Device testing on OnePlus 13R / Linux 6.1.118 / KSUN 33405 produced completed
512-pair Duck Build 1072 parent samples with negative A-B timing instead of the
previous positive signature. This does not guarantee timing equality, absence of
all detection channels, or correctness of future upstream combinations.

The separate intermittent throne-hunt finding is not addressed by this patch.
The CI helper applies the patch once, recognizes an exact existing application,
and fails rather than silently omitting it on incompatible source revisions.
KernelSU/SUSFS update resolution is not pinned by this backport.
