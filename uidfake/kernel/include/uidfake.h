/* SPDX-License-Identifier: GPL-2.0 */
#ifndef HMA_UIDFAKE_INTERNAL_H
#define HMA_UIDFAKE_INTERNAL_H
#include <linux/types.h>
#include "kaux.h"
#define POLICY_MAX_PAIRS 65536u
#define UF_APK_MAX 10000u
int policy_apply(const u32 *pairs, u32 npairs);
int uidfake_apk_apply(const u32 *blob, u32 len);
void uidfake_status_get(struct kaux_status *out);
int netlink_init(void);
#endif
