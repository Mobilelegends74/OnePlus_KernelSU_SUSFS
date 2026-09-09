#!/usr/bin/env python3
"""Check known OP13R LTS merge invariants without compiling the kernel.

Run against the common source tree after 0000a and 0000c-0000j. These checks
guard prior merge regressions; they do not replace CI or on-device testing.
"""

import re
import sys
from pathlib import Path


def validate(root):
    errors = []

    def read(path):
        return (root / path).read_text()

    def require(condition, message):
        if not condition:
            errors.append(message)

    def function(text, name):
        match = re.search(r"\b" + name + r"\([^;{}]*\)\n\{\n.*?^\}", text, re.M | re.S)
        require(match is not None, f"missing function: {name}")
        return match[0] if match else ""

    fork = read("kernel/fork.c")
    mm_types = read("include/linux/mm_types.h")
    require("struct chp_vma_name_address chp;" in mm_types, "missing MM/CHP prefix")
    require("BUILD_BUG_ON(offsetof(struct mm_struct_abi_extend, chp) != 0);" in fork,
            "missing CHP ABI prefix assertion")
    require("kzalloc(sizeof(*mm->abi_extend), GFP_KERNEL)" in function(fork, "allocate_mm"),
            "MM extension must be zero-initialized")
    require(fork.count("kfree(mm->abi_extend);") == 1, "MM extension must have one free site")
    require("kfree(mm->abi_extend);" in function(fork, "free_mm"), "extension leak on free_mm")
    for name in ("mm_alloc", "dup_mm"):
        body = function(fork, name)
        require("abi_extend = mm->abi_extend;" in body and "mm->abi_extend = abi_extend;" in body,
                f"{name} must preserve its independently allocated extension")
    require("put_dmabuf_info(tsk->dmabuf_info);" in function(fork, "__put_task_struct"),
            "task DMA-BUF reference leak")

    blk = function(read("block/blk-mq.c"), "blk_mq_init_hctx")
    for state in ("CPUHP_AP_BLK_MQ_ONLINE", "CPUHP_BLK_MQ_DEAD"):
        require(f"cpuhp_state_add_instance_nocalls({state}," in blk, f"missing {state} registration")

    for path, name in (
        ("drivers/usb/host/xhci.c", "xhci_handshake_check_state"),
        ("drivers/pci/pcie/portdrv_pci.c", "pcie_portdrv_shutdown"),
        ("drivers/usb/gadget/function/uvc_configfs.c", "uvcg_framebased_make"),
        ("drivers/usb/gadget/function/uvc_configfs.c", "__uvcg_copy_framebased_desc"),
    ):
        definitions = re.findall(r"\b" + name + r"\([^;{}]*\)\n\{", read(path))
        require(len(definitions) == 1, f"{path}: expected one definition of {name}")

    events = read("include/trace/events/f2fs.h")
    for event in ("f2fs_lock_elapsed_time", "f2fs_priority_uplift", "f2fs_priority_restore"):
        require(re.search(r"\b" + event + r"\s*,", events), f"missing F2FS event: {event}")

    compress = read("fs/f2fs/compress.c")
    alloc = function(compress, "f2fs_alloc_dic")
    for field in ("sbi", "compress_algorithm", "fixed_input"):
        require(f"dic->{field} =" in alloc, f"uninitialized decompress state: {field}")
    require("dic->inode" not in function(compress, "f2fs_free_dic"),
            "late decompress cleanup must not dereference inode")
    end_io = function(compress, "f2fs_compress_write_end_io")
    require(end_io.rstrip().endswith("dec_page_count(sbi, type);\n}"),
            "compressed write completion must decrement sbi counter last")
    raw = function(compress, "f2fs_write_raw_pages")
    require("f2fs_lock_op(sbi, &lc);" in raw and "f2fs_unlock_op(sbi, &lc);" in raw,
            "raw cluster replacement needs lock context")
    require(not re.search(r"page_array_(?:alloc|free)\(cc->inode,", compress),
            "page array helpers now require sbi, not inode")

    file_ops = read("fs/f2fs/file.c")
    donate = function(read("fs/f2fs/inode.c"), "f2fs_remove_donate_inode")
    require("list_del_init(&F2FS_I(inode)->gdonate_list);" in donate and
            "sbi->donate_files--;" in donate, "missing donation-cache inode cleanup implementation")
    require("f2fs_putname(buf);" in function(file_ops, "f2fs_trace_rw_file_path"),
            "trace path allocation/free mismatch")
    for name in ("f2fs_setattr", "f2fs_fallocate"):
        require("inode_dio_wait(inode);" in function(file_ops, name), f"{name}: missing DIO drain")
    for name in ("__f2fs_file_open", "__f2fs_release_file"):
        require("open_count" not in function(file_ops, name), f"{name}: OEM recursion must not count VFS opens")
    require("atomic_inc(&F2FS_I(inode)->open_count)" in function(file_ops, "f2fs_file_open"),
            "VFS open count missing")
    require("atomic_dec_and_test(&F2FS_I(inode)->open_count)" in function(file_ops, "f2fs_release_file"),
            "VFS release count missing")
    reserve = function(file_ops, "reserve_compress_blocks")
    require("for (i = 0; i < cluster_size; i++)" in reserve,
            "reserve scan must not advance dn before accounting succeeds")
    require("reserved && to_reserved == 1" in reserve, "missing already-reserved cluster check")

    exports = re.findall(r"EXPORT_TRACEPOINT_SYMBOL_GPL\((\w+)\)", read("drivers/android/vendor_hooks.c"))
    for name in ("android_vh_mm_init", "android_vh_mm_free", "android_rvh_create_worker",
                 "android_vh_drain_all_pages_bypass", "android_vh_signal_coredump_check"):
        require(exports.count(name) == 1, f"missing or duplicate vendor export: {name}")

    drm = read("drivers/gpu/drm/drm_atomic_helper.c")
    cwb = function(drm, "drm_atomic_legacy_msm_cwb")
    for guard in ('strcmp(crtc->dev->driver->name, "msm_drm")',
                  'hweight32(crtc_state->encoder_mask) != 2',
                  'encoder->possible_clones != drm_encoder_mask(encoder)',
                  'conn_state->crtc != crtc',
                  'DRM_MODE_CONNECTOR_DSI', 'DRM_MODE_CONNECTOR_VIRTUAL',
                  'return dsi == 1 && cwb == 1;'):
        require(guard in cwb, f"missing legacy CWB restriction: {guard}")
    clone_check = function(drm, "drm_atomic_check_valid_clones")
    require('if (drm_atomic_legacy_msm_cwb(state, crtc))' in clone_check,
            "missing targeted legacy CWB compatibility path")
    require('return -EINVAL;' in clone_check and
            'crtc_state->encoder_mask & drm_enc->possible_clones' in clone_check,
            "upstream clone validation must remain in place")
    require('OP13R DRM: legacy DSI/CWB clone compatibility enabled' in clone_check,
            "missing one-time device diagnostic for CWB compatibility")

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("OP13R LTS merge invariants: PASS (static checks, no compilation)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: validate_lts_merge.py COMMON_KERNEL_FOLDER")
    sys.exit(validate(Path(sys.argv[1])))
