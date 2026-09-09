#!/usr/bin/env python3
"""CI host tests of the actual OP13R DRM clone-policy functions.

No policy is reimplemented in Python: extract the two patched C functions,
provide mock DRM objects/iterators, then compile and execute on the CI host.
Use --check-source-only locally when kernel/host compilation is not wanted.
These tests do not validate DRM locking, vendor binaries, or panel hardware.
"""

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#define DRM_MODE_CONNECTOR_DSI 16
#define DRM_MODE_CONNECTOR_VIRTUAL 15
#define DRM_MODE_CONNECTOR_HDMIA 11
#define MAX_OBJECTS 4
struct drm_driver { const char *name; };
struct drm_encoder { unsigned int index, possible_clones; struct { int id; } base; };
struct drm_device { struct drm_driver *driver; struct drm_encoder *encoders[MAX_OBJECTS]; };
struct drm_crtc { struct drm_device *dev; struct { int id; } base; };
struct drm_crtc_state { unsigned int encoder_mask; };
struct drm_connector { int connector_type; };
struct drm_connector_state { struct drm_crtc *crtc; };
struct drm_atomic_state {
    struct drm_crtc_state crtc_state;
    struct drm_connector connectors[MAX_OBJECTS];
    struct drm_connector_state conn_states[MAX_OBJECTS];
    int num_connectors;
};
static struct drm_crtc_state *drm_atomic_get_new_crtc_state(
        struct drm_atomic_state *state, struct drm_crtc *crtc)
{
    (void)crtc;
    return &state->crtc_state;
}
static unsigned int drm_encoder_mask(struct drm_encoder *encoder)
{
    return 1U << encoder->index;
}
#define hweight32(value) __builtin_popcount((unsigned int)(value))
#define drm_for_each_encoder_mask(encoder, dev, mask) \
    for (unsigned int bit = 0; bit < MAX_OBJECTS; bit++) \
        if (((mask) & (1U << bit)) && ((encoder) = (dev)->encoders[bit]))
#define for_each_new_connector_in_state(state, connector, conn_state, i) \
    for ((i) = 0; (i) < (state)->num_connectors && \
         (((connector) = &(state)->connectors[i]), \
          ((conn_state) = &(state)->conn_states[i]), 1); (i)++)
#define DRM_DEBUG(...) ((void)0)
#define pr_info_once(...) ((void)0)
#define pr_warn_ratelimited(...) ((void)0)
'''

TESTS = r'''
static struct drm_driver driver;
static struct drm_device dev;
static struct drm_encoder encoders[MAX_OBJECTS];
static struct drm_crtc crtc, other_crtc;
static struct drm_atomic_state state;
static int tests;

static void reset(void)
{
    memset(&state, 0, sizeof(state));
    driver.name = "msm_drm";
    dev.driver = &driver;
    crtc.dev = &dev;
    other_crtc.dev = &dev;
    for (unsigned int i = 0; i < MAX_OBJECTS; i++) {
        encoders[i].index = i;
        encoders[i].possible_clones = 1U << i;
        dev.encoders[i] = &encoders[i];
        state.conn_states[i].crtc = &crtc;
    }
    state.num_connectors = 2;
    state.crtc_state.encoder_mask = 3;
    state.connectors[0].connector_type = DRM_MODE_CONNECTOR_DSI;
    state.connectors[1].connector_type = DRM_MODE_CONNECTOR_VIRTUAL;
}

static void check(const char *name, bool legacy, int expected)
{
    assert(drm_atomic_legacy_msm_cwb(&state, &crtc) == legacy);
    assert(drm_atomic_check_valid_clones(&state, &crtc) == expected);
    printf("PASS: %s\n", name);
    tests++;
}

int main(void)
{
    reset(); check("OEM DSI + CWB with default self masks", true, 0);
    reset(); driver.name = "msm";
    check("upstream msm driver not exempt", false, -EINVAL);
    reset(); driver.name = "i915";
    check("other drivers not exempt", false, -EINVAL);
    reset(); state.connectors[1].connector_type = DRM_MODE_CONNECTOR_HDMIA;
    check("DSI + HDMI not exempt", false, -EINVAL);
    reset(); state.connectors[1].connector_type = DRM_MODE_CONNECTOR_DSI;
    check("two physical DSI outputs not exempt", false, -EINVAL);
    reset(); state.connectors[0].connector_type = DRM_MODE_CONNECTOR_VIRTUAL;
    check("two virtual outputs not exempt", false, -EINVAL);
    reset(); state.num_connectors = 3;
    state.connectors[2].connector_type = DRM_MODE_CONNECTOR_VIRTUAL;
    check("extra connector on same CRTC not exempt", false, -EINVAL);
    reset(); state.num_connectors = 3;
    state.connectors[2].connector_type = DRM_MODE_CONNECTOR_HDMIA;
    state.conn_states[2].crtc = &other_crtc;
    check("unrelated CRTC does not affect valid OEM pair", true, 0);
    reset(); state.conn_states[1].crtc = &other_crtc;
    check("virtual connector must belong to current CRTC", false, -EINVAL);
    reset(); state.crtc_state.encoder_mask = 7;
    check("three encoders not exempt", false, -EINVAL);
    reset(); encoders[0].possible_clones = 7;
    check("explicit wider mask not exempt", false, -EINVAL);
    reset(); encoders[0].possible_clones = 2;
    check("explicit non-self mask not exempt", false, -EINVAL);
    reset(); encoders[0].possible_clones = 3; encoders[1].possible_clones = 3;
    check("explicit valid clones pass upstream check", false, 0);
    reset(); encoders[0].possible_clones = 0;
    check("mixed zero and self masks not exempt", false, -EINVAL);
    reset(); encoders[0].possible_clones = 0; encoders[1].possible_clones = 0;
    check("upstream zero-mask semantics retained", false, 0);
    reset(); state.crtc_state.encoder_mask = 1; state.num_connectors = 1;
    check("ordinary single display still passes", false, 0);
    reset(); state.crtc_state.encoder_mask = 0; state.num_connectors = 0;
    check("disabled CRTC still passes", false, 0);
    reset(); state.crtc_state.encoder_mask = 6;
    check("valid pair independent of encoder indices", true, 0);
    printf("%d DRM clone-policy cases passed (mock objects, not a device test)\n", tests);
    return 0;
}
'''


def harness(root):
    source = (root / "drivers/gpu/drm/drm_atomic_helper.c").read_text()
    functions = []
    for result_type, name in (("bool", "drm_atomic_legacy_msm_cwb"),
                              ("int", "drm_atomic_check_valid_clones")):
        matches = re.findall(r"^static " + result_type + r" " + name +
                             r"\([^;{}]*\)\n\{\n.*?^\}", source, re.M | re.S)
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one definition of {name}")
        functions.append(matches[0])
    return PREAMBLE + "\n" + "\n".join(functions) + "\n" + TESTS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--check-source-only", action="store_true")
    args = parser.parse_args()
    source = harness(args.root)
    if args.check_source_only:
        print("DRM test source extraction: PASS (no compilation or execution)")
        return
    with tempfile.TemporaryDirectory(prefix="op13r-drm-test-") as directory:
        binary = Path(directory) / "test-drm-cwb"
        compiler = shlex.split(os.environ.get("HOSTCC", "cc"))
        subprocess.run(compiler + ["-std=c11", "-Wall", "-Wextra", "-Werror",
                                  "-x", "c", "-", "-o", str(binary)],
                       input=source, text=True, check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
