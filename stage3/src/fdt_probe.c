/* Strict read-only FDT parser for nabu PSCI probe. */
#include "fdt_probe.h"
#define FDT_MAGIC 0xd00dfeedU
#define FDT_BEGIN_NODE 1U
#define FDT_END_NODE 2U
#define FDT_PROP 3U
#define FDT_NOP 4U
#define FDT_END 9U
#define MAX_FDT_SIZE (4U * 1024U * 1024U)

static uint32_t be32(const uint8_t *p) {
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static uint64_t be64(const uint8_t *p) {
    return ((uint64_t)be32(p) << 32) | be32(p + 4);
}

static int equals(const char *p, uint32_t len, const char *q) {
    uint32_t i = 0;
    while (q[i]) {
        if (i >= len || p[i] != q[i]) return 0;
        ++i;
    }
    return i < len && p[i] == '\0';
}

static int contains(const char *s, uint32_t len, const char *target) {
    uint32_t target_len = 0;
    while (target[target_len]) ++target_len;
    if (target_len == 0 || target_len > len) return 0;
    for (uint32_t i = 0; i <= len - target_len; ++i) {
        uint32_t k = 0;
        while (k < target_len && s[i + k] == target[k]) ++k;
        if (k == target_len) return 1;
    }
    return 0;
}

static uint32_t align4(uint32_t n) { return (n + 3U) & ~3U; }

/* Read only the FDT's tightly bounded header, nodes and property values. */
struct fdt_result nabu_inspect_fdt(const void *dtb) {
    struct fdt_result r = {0};
    if (!dtb || ((uintptr_t)dtb & 7U)) return r;
    const uint8_t *f = (const uint8_t *)dtb;
    if (be32(f) != FDT_MAGIC) return r;
    uint32_t total = be32(f + 4), off_struct = be32(f + 8);
    uint32_t off_strings = be32(f + 12);
    uint32_t sz_strings = be32(f + 32), sz_struct = be32(f + 36);
    if (total < 40U || total > MAX_FDT_SIZE ||
        off_struct < 40U || off_strings < 40U ||
        off_struct > total || off_strings > total ||
        sz_struct > total - off_struct || sz_strings > total - off_strings) return r;

    uint32_t end_struct = off_struct + sz_struct;
    const char *names = (const char *)(f + off_strings);
    uint32_t at = off_struct;
    int depth = 0, psci_depth = -1, chosen_depth = -1;
    int complete = 0;
    /* The parser avoids unbounded recursion or C library functions. */
    for (uint32_t step = 0; step < 120000 && at <= end_struct && end_struct - at >= 4U; ++step) {
        uint32_t token = be32(f + at);
        at += 4;
        if (token == FDT_BEGIN_NODE) {
            uint32_t start = at;
            while (at < end_struct && f[at] != 0) ++at;
            if (at >= end_struct) return r;
            uint32_t len = at - start;
            ++depth;
            if (depth > 64) return r;
            if (depth == 2 && equals((const char *)(f + start), len + 1, "psci"))
                psci_depth = depth;
            if (depth == 2 && equals((const char *)(f + start), len + 1, "chosen"))
                chosen_depth = depth;
            at = align4(at + 1U);
            if (at > end_struct) return r;
        } else if (token == FDT_END_NODE) {
            if (depth <= 0) return r;
            if (depth == psci_depth) psci_depth = -1;
            if (depth == chosen_depth) chosen_depth = -1;
            --depth;
        } else if (token == FDT_PROP) {
            if (at > end_struct || end_struct - at < 8U) return r;
            uint32_t len = be32(f + at), no = be32(f + at + 4);
            at += 8;
            if (len > end_struct - at || no >= sz_strings) return r;
            uint32_t name_len = 0;
            while (name_len < sz_strings - no && names[no + name_len] != '\0')
                ++name_len;
            if (name_len == sz_strings - no) return r;
            const char *key = names + no;
            const char *val = (const char *)(f + at);
            if (depth == 1 && (equals(key, name_len + 1, "compatible") ||
                               equals(key, name_len + 1, "model"))) {
                if (contains(val, len, "nabu") || contains(val, len, "NABU") ||
                    contains(val, len, "Pad 5")) r.nabu = 1;
            }
            if (depth == chosen_depth && (len == 4U || len == 8U)) {
                uint64_t address = len == 4U ? be32((const uint8_t *)val) :
                                               be64((const uint8_t *)val);
                if (equals(key, name_len + 1, "linux,initrd-start")) {
                    r.initrd_start = address;
                    r.has_initrd_start = 1;
                } else if (equals(key, name_len + 1, "linux,initrd-end")) {
                    r.initrd_end = address;
                    r.has_initrd_end = 1;
                }
            }
            if (depth == psci_depth) {
                if (equals(key, name_len + 1, "compatible") &&
                    (contains(val, len, "arm,psci-0.2") ||
                     contains(val, len, "arm,psci-1.0")))
                    r.psci_02_or_newer = 1;
                if (equals(key, name_len + 1, "method")) {
                    if (equals(val, len, "smc")) r.method = 1;
                    else if (equals(val, len, "hvc")) r.method = 2;
                }
            }
            at = align4(at + len);
            if (at > end_struct) return r;
        } else if (token == FDT_NOP) {
            /* Skip */
        } else if (token == FDT_END) {
            complete = (depth == 0);
            break;
        } else {
            return r;
        }
    }
    r.valid = (uint8_t)complete;
    return r;
}
