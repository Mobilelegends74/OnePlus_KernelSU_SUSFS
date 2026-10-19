// SPDX-License-Identifier: GPL-2.0
/* Native integration of HMA UIDFAKE's policy protocol and process identity.
 * No syscall-table writes, instruction decoding, f_op substitution or TIF bits.
 */
#include <linux/cred.h>
#include <linux/dcache.h>
#include <linux/fs.h>
#include <linux/hma_uidfake.h>
#include <linux/init.h>
#include <linux/kdev_t.h>
#include <linux/mutex.h>
#include <linux/namei.h>
#include <linux/rcupdate.h>
#include <linux/sched/signal.h>
#include <linux/slab.h>
#include <linux/sort.h>
#include <linux/vmalloc.h>
#include "uidfake.h"

#define APP_MIN 10000u
#define APP_SPAN 10000u
#define USER_RANGE 100000u
#define ISOLATED_MIN 90000u
#define PENDING (1u << 31)
struct uf_pair { u32 caller, target; };
struct uf_policy { u32 n; struct uf_pair pairs[]; };
/* Metadata references inodes by dev/ino, never replaces their operations. */
struct uf_apk { u32 dev, uid; u64 ino; };
struct uf_apks { u32 n; struct uf_apk entries[]; };
static struct uf_policy __rcu *policy;
static struct uf_apks __rcu *apks;
static DEFINE_MUTEX(update_lock);
static u32 apk_offered, apk_failed, apk_failed_total, apk_updates;

static u32 app_id(u32 uid)
{
	uid %= USER_RANGE;
	return uid >= APP_MIN && uid < APP_MIN + APP_SPAN ?
		uid - APP_MIN + 1 : 0;
}

static int pair_cmp(const void *a, const void *b)
{
	const struct uf_pair *x = a, *y = b;
	if (x->caller != y->caller)
		return x->caller < y->caller ? -1 : 1;
	return x->target < y->target ? -1 : x->target != y->target;
}

static bool pair_has(const struct uf_policy *p, u32 caller, u32 target)
{
	struct uf_pair key = { caller, target };
	u32 lo = 0, hi = p->n;
	while (lo < hi) {
		u32 mid = lo + (hi - lo) / 2;
		int cmp = pair_cmp(&p->pairs[mid], &key);
		if (cmp < 0)
			lo = mid + 1;
		else if (cmp > 0)
			hi = mid;
		else
			return true;
	}
	return false;
}

int policy_apply(const u32 *pairs, u32 n)
{
	struct uf_policy *next, *old;
	u32 i, live = 0;
	if (n > POLICY_MAX_PAIRS)
		return -E2BIG;
	next = kvzalloc(sizeof(*next) + n * sizeof(struct uf_pair), GFP_KERNEL);
	if (!next)
		return -ENOMEM;
	for (i = 0; i < n; i++) {
		u32 caller = pairs[2 * i], target = pairs[2 * i + 1];
		if (target % USER_RANGE < APP_MIN)
			continue; /* root/system targets always retain native visibility */
		if (caller && !app_id(caller))
			continue;
		next->pairs[live].caller = caller ? caller % USER_RANGE : 0;
		next->pairs[live++].target = target;
	}
	next->n = live;
	sort(next->pairs, live, sizeof(struct uf_pair), pair_cmp, NULL);
	mutex_lock(&update_lock);
	old = rcu_dereference_protected(policy, lockdep_is_held(&update_lock));
	rcu_assign_pointer(policy, next);
	synchronize_rcu();
	kvfree(old);
	mutex_unlock(&update_lock);
	pr_info("hma_uidfake: published %u caller/target pairs\n", live);
	return 0;
}

/* task_struct is copied by fork; app_zygote descendants keep the original app.
 * A system zygote child entering an isolated UID waits for its app code inode.
 * Once named, later setuid calls cannot select another app's hiding policy.
 */
void hma_uidfake_creds(const struct cred *old, const struct cred *new)
{
	u32 before = __kuid_val(old->fsuid), after = __kuid_val(new->fsuid);
	u32 tag, id;
	if (before == after)
		return;
	tag = READ_ONCE(current->hma_uidfake_app);
	if (tag && tag != PENDING)
		return;
	if (before % USER_RANGE >= APP_MIN && tag != PENDING)
		return;
	id = app_id(after);
	if (id)
		cmpxchg(&current->hma_uidfake_app, tag, id);
	else if (after % USER_RANGE >= ISOLATED_MIN)
		cmpxchg(&current->hma_uidfake_app, tag, PENDING);
}

bool hma_uidfake_hidden(unsigned int target)
{
	const struct uf_policy *p;
	u32 tag = READ_ONCE(current->hma_uidfake_app);
	u32 caller;
	bool hidden = false;
	if (tag == PENDING) {
		/* Close the APK attribution window on the first UID query. */
		cmpxchg(&current->hma_uidfake_app, PENDING, 0);
		return false;
	}
	if (!tag)
		tag = app_id(__kuid_val(current_fsuid()));
	if (!tag)
		return false;
	caller = APP_MIN + tag - 1;
	if (target % USER_RANGE == caller)
		return false;
	rcu_read_lock();
	p = rcu_dereference(policy);
	if (p)
		hidden = pair_has(p, caller, target) || pair_has(p, 0, target);
	rcu_read_unlock();
	return hidden;
}

static u32 encode_dev(dev_t dev)
{
	return new_encode_dev(dev);
}

/* Keep all threads of an isolated process consistent; updates never sleep. */
static void name_task(u32 id)
{
	struct task_struct *leader = current->group_leader, *t;
	rcu_read_lock();
	cmpxchg(&leader->hma_uidfake_app, PENDING, id);
	for_each_thread(leader, t)
		cmpxchg(&t->hma_uidfake_app, PENDING, id);
	rcu_read_unlock();
}

void hma_uidfake_open(struct file *file)
{
	const struct uf_apks *table;
	struct dentry *d;
	u32 i, depth, id = 0;
	if (READ_ONCE(current->hma_uidfake_app) != PENDING)
		return;
	/* dget_parent/dput rather than racing a rename through d_parent. */
	d = dget(file->f_path.dentry);
	for (depth = 0; depth < 5 && d; depth++) {
		struct inode *inode = d_inode(d);
		struct dentry *parent;
		if (inode) {
			rcu_read_lock();
			table = rcu_dereference(apks);
			if (table)
				for (i = 0; i < table->n; i++)
					if (table->entries[i].ino == inode->i_ino &&
					    table->entries[i].dev == encode_dev(inode->i_sb->s_dev)) {
						id = app_id(table->entries[i].uid);
						break;
					}
			rcu_read_unlock();
		}
		if (id || IS_ROOT(d)) {
			dput(d);
			break;
		}
		parent = dget_parent(d);
		dput(d);
		d = parent;
	}
	if (depth == 5 && d)
		dput(d);
	if (id)
		name_task(id);
}

int uidfake_apk_apply(const u32 *blob, u32 len)
{
	struct uf_apks *next, *old;
	const u8 *bytes = (const u8 *)blob;
	u32 n, i, failed = 0;
	int ret = 0;
	if (len < 4)
		return -EINVAL;
	n = blob[0];
	if (n > UF_APK_MAX || 4ull + 16ull * n > len)
		return -EINVAL;
	/* Validate the complete upload before touching the current table. */
	for (i = 0; i < n; i++) {
		const u32 *e = &blob[1 + 4 * i];
		if (e[0] > 1)
			return -EINVAL;
		if (!e[0] && (!app_id(e[1]) || !e[3] ||
		    e[2] < 4ull + 16ull * n || e[2] > len ||
		    e[3] > len - e[2] || bytes[e[2] + e[3] - 1] ||
		    strnlen((const char *)bytes + e[2], e[3]) != e[3] - 1))
			return -EINVAL;
	}
	next = kvzalloc(sizeof(*next) + UF_APK_MAX * sizeof(struct uf_apk), GFP_KERNEL);
	if (!next)
		return -ENOMEM;
	mutex_lock(&update_lock);
	old = rcu_dereference_protected(apks, lockdep_is_held(&update_lock));
	if (old) {
		next->n = old->n;
		memcpy(next->entries, old->entries, old->n * sizeof(struct uf_apk));
	}
	for (i = 0; i < n; i++) {
		const u32 *e = &blob[1 + 4 * i];
		struct uf_apk item;
		u32 j;
		if (!e[0]) {
			struct path path;
			struct inode *inode;
			ret = kern_path((const char *)bytes + e[2], LOOKUP_FOLLOW, &path);
			if (ret) { failed++; continue; }
			inode = d_inode(path.dentry);
			item.dev = encode_dev(inode->i_sb->s_dev);
			item.ino = inode->i_ino;
			item.uid = e[1];
			path_put(&path);
		} else {
			item.dev = e[1];
			item.ino = (u64)e[2] | ((u64)e[3] << 32);
			item.uid = 0;
		}
		for (j = 0; j < next->n; j++)
			if (next->entries[j].dev == item.dev && next->entries[j].ino == item.ino)
				break;
		if (e[0]) {
			if (j < next->n)
				next->entries[j] = next->entries[--next->n];
		} else if (j < next->n) {
			next->entries[j] = item;
		} else if (next->n < UF_APK_MAX) {
			next->entries[next->n++] = item;
		} else {
			failed++;
		}
	}
	/* Failed batches preserve old table and return error so the daemon retries. */
	if (!failed) {
		rcu_assign_pointer(apks, next);
		synchronize_rcu();
		kvfree(old);
	} else {
		kvfree(next);
	}
	apk_offered = n;
	apk_failed = failed;
	apk_failed_total += failed;
	apk_updates++;
	mutex_unlock(&update_lock);
	return failed ? -EAGAIN : 0;
}

void uidfake_status_get(struct kaux_status *out)
{
	const struct uf_policy *p;
	const struct uf_apks *a;
	memset(out, 0, sizeof(*out));
	out->magic = KAUX_STATUS_MAGIC;
	out->size = sizeof(*out);
	out->version = KAUX_FAMILY_VERSION;
	out->native = out->native_expected = 4;
	if (IS_ENABLED(CONFIG_COMPAT))
		out->compat = out->compat_expected = 4;
	out->flags = KAUX_F_NATIVE | KAUX_F_SETUID;
	if (IS_ENABLED(CONFIG_COMPAT))
		out->flags |= KAUX_F_COMPAT;
	out->lsm_state = KAUX_LSM_TAKEN;
	strscpy(out->lsm_target, "native commit_creds", sizeof(out->lsm_target));
	mutex_lock(&update_lock);
	out->apk_offered = apk_offered;
	out->apk_failed = apk_failed;
	out->apk_failed_total = apk_failed_total;
	out->apk_updates = apk_updates;
	if (!apk_failed)
		out->flags |= KAUX_F_APKS;
	rcu_read_lock();
	p = rcu_dereference(policy);
	a = rcu_dereference(apks);
	out->policy_pairs = p ? p->n : 0;
	out->apk_inodes = a ? a->n : 0;
	rcu_read_unlock();
	mutex_unlock(&update_lock);
}

static int __init hma_uidfake_init(void)
{
	int ret = netlink_init();
	if (ret)
		pr_err("hma_uidfake: generic netlink registration failed: %d\n", ret);
	else
		pr_info("hma_uidfake: native built-in policy ready (protocol %u)\n", KAUX_FAMILY_VERSION);
	return ret;
}
late_initcall(hma_uidfake_init);
