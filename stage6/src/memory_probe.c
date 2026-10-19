/*
 * Read-only flattened Device Tree analysis for Xiaomi nabu Stage 6.
 *
 * Examine ONLY the FDT blob supplied as input. Never touch addresses in its
 * reg properties; they are integers, NOT pointers to dereference.
 *
 * Fail closed on unsupported cell layouts, malformed node boundaries, missing
 * FDT /memreserve terminator, integer overflow, or excessive tree depth.
 */
#include "memory_probe.h"
#include <stdint.h>
#include <stddef.h>

#define MAGIC 0xD00DFEEDU
#define T_BEGIN 1U
#define T_END_NODE 2U
#define T_PROP 3U
#define T_NOP 4U
#define T_END 9U
#define MAX_FDT (4U * 1024U * 1024U)
#define MAX_STEPS 160000U
#define MAX_DEPTH 96

static uint32_t u32be(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16)
         | ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static uint64_t u64be(const uint8_t *p)
{
    return ((uint64_t)u32be(p) << 32) | u32be(p + 4);
}

static int add_checked(uint64_t a, uint64_t b, uint64_t *out)
{
    if (b > UINT64_MAX - a) return 0;
    *out = a + b;
    return 1;
}

static int intersects(uint64_t a, uint64_t b, uint64_t c, uint64_t d)
{
    return a < d && c < b;
}

static int equals(const char *s, uint32_t n, const char *literal)
{
    uint32_t k = 0;
    while (literal[k]) {
        if (k >= n || s[k] != literal[k]) return 0;
        k++;
    }
    return k == n;
}

static int starts_with(const char *s, uint32_t n, const char *prefix)
{
    uint32_t k = 0;
    while (prefix[k]) {
        if (k >= n || s[k] != prefix[k]) return 0;
        k++;
    }
    return 1;
}

static int equals_name(const char *s, uint32_t n, const char *literal)
{
    return equals(s, n, literal);
}

static int reg_list(const uint8_t *value, uint32_t length,
                    uint64_t candidate_lo, uint64_t candidate_hi,
                    uint32_t *entries, uint32_t *contains, uint32_t *overlaps)
{
    /* nabu /memory and /reserved-memory use 2 address and 2 size cells.
     * A generic 1/1 layout is intentionally not silently assumed.
     */
    if (!length || (length % 16U)) return 0;
    for (uint32_t i = 0; i < length; i += 16U) {
        uint64_t addr = u64be(value + i);
        uint64_t size = u64be(value + i + 8U);
        uint64_t end = 0;
        if (!add_checked(addr, size, &end)) return 0;
        if (!size) continue;
        if (*entries == UINT32_MAX) return 0;
        ++*entries;
        if (addr <= candidate_lo && end >= candidate_hi) *contains = 1;
        if (intersects(addr, end, candidate_lo, candidate_hi)) *overlaps = 1;
    }
    return 1;
}

struct nabu_memory_report nabu_memory_probe(
    const void *dtb, uint64_t dtb_pa,
    uint64_t image_lo, uint64_t image_hi,
    uint64_t candidate_lo, uint64_t candidate_hi,
    uint64_t initrd_lo, uint64_t initrd_hi)
{
    struct nabu_memory_report fail = {0};
    struct nabu_memory_report r = {0};
    if (!dtb || ((uintptr_t)dtb & 7U) ||
        candidate_hi <= candidate_lo || image_hi <= image_lo ||
        initrd_hi <= initrd_lo) return fail;

    const uint8_t *f = (const uint8_t *)dtb;
    if (u32be(f) != MAGIC) return fail;
    uint32_t total = u32be(f + 4);
    uint32_t off_struct = u32be(f + 8);
    uint32_t off_strings = u32be(f + 12);
    uint32_t off_rsvmap = u32be(f + 16);
    uint32_t version = u32be(f + 20);
    uint32_t sz_strings = u32be(f + 32);
    uint32_t sz_struct = u32be(f + 36);
    if (total < 72 || total > MAX_FDT || version < 17 ||
        off_struct < 40 || off_strings < 40 || off_rsvmap < 40 ||
        (off_rsvmap & 7U) || off_rsvmap >= off_struct ||
        off_struct > total || off_strings > total ||
        sz_struct > total - off_struct || sz_strings > total - off_strings)
        return fail;

    uint64_t dtb_end;
    if (!add_checked(dtb_pa, total, &dtb_end)) return fail;

    /* Cross-check physical bounds as NUMBERS only. No address is dereferenced. */
    r.initrd_valid = 1;
    if (intersects(candidate_lo, candidate_hi, image_lo, image_hi) ||
        intersects(candidate_lo, candidate_hi, dtb_pa, dtb_end) ||
        intersects(candidate_lo, candidate_hi, initrd_lo, initrd_hi))
        r.loaded_conflict = 1;

    /* /memreserve entries are pairs (u64 addr, u64 size), terminating 0/0. */
    int reserve_ended = 0;
    uint32_t pos = off_rsvmap;
    for (uint32_t i = 0; i < 4096 && off_struct - pos >= 16U; ++i) {
        uint64_t addr = u64be(f + pos), size = u64be(f + pos + 8);
        pos += 16;
        if (!addr && !size) {
            reserve_ended = 1;
            break;
        }
        uint64_t end;
        if (!add_checked(addr, size, &end)) return fail;
        if (size && intersects(addr, end, candidate_lo, candidate_hi))
            r.fixed_conflict = 1;
        if (r.memreserve_count == UINT32_MAX) return fail;
        r.memreserve_count++;
    }
    if (!reserve_ended) return fail;

    uint32_t at = off_struct, end_struct = off_struct + sz_struct;
    const char *names = (const char *)(f + off_strings);
    int depth = 0;
    uint32_t root_addr_cells = 0, root_size_cells = 0;
    uint32_t reserved_addr_cells = 0, reserved_size_cells = 0;
    int memory_depth = -1, reserved_depth = -1, reserved_child_depth = -1;
    int child_has_reg = 0, child_has_size = 0;
    int complete = 0, saw_root = 0;
    int saw_reserved_root = 0, saw_ram = 0;

    for (uint32_t step = 0;
         step < MAX_STEPS && at <= end_struct && end_struct - at >= 4U;
         ++step) {
        uint32_t token = u32be(f + at);
        at += 4;
        if (token == T_BEGIN) {
            uint32_t start = at;
            while (at < end_struct && f[at] != 0) ++at;
            if (at >= end_struct) return fail;
            uint32_t name_len = at - start;
            const char *name = (const char *)(f + start);
            if (++depth > MAX_DEPTH) return fail;
            if (depth == 1) {
                if (saw_root || name_len) return fail;
                saw_root = 1;
            } else if (depth == 2) {
                if (equals_name(name, name_len, "memory") ||
                    starts_with(name, name_len, "memory@"))
                    memory_depth = 2;
                if (equals_name(name, name_len, "reserved-memory")) {
                    reserved_depth = 2;
                    saw_reserved_root = 1;
                }
            } else if (depth == 3 && reserved_depth == 2) {
                reserved_child_depth = 3;
                child_has_reg = 0;
                child_has_size = 0;
            }
            at = (at + 4U) & ~3U;
            if (at > end_struct) return fail;
        } else if (token == T_END_NODE) {
            if (!depth) return fail;
            if (depth == 3 && reserved_child_depth == 3) {
                if (child_has_size && !child_has_reg) {
                    if (r.dynamic_unknown == UINT32_MAX) return fail;
                    ++r.dynamic_unknown;
                }
                reserved_child_depth = -1;
            }
            if (depth == 2 && memory_depth == 2) memory_depth = -1;
            if (depth == 2 && reserved_depth == 2) reserved_depth = -1;
            --depth;
        } else if (token == T_PROP) {
            if (!depth || end_struct - at < 8U) return fail;
            uint32_t len = u32be(f + at);
            uint32_t name_off = u32be(f + at + 4);
            at += 8;
            if (len > end_struct - at || name_off >= sz_strings) return fail;
            uint32_t name_len = 0;
            while (name_len < sz_strings - name_off &&
                   names[name_off + name_len] != 0) ++name_len;
            if (name_len >= sz_strings - name_off) return fail;
            const char *key = names + name_off;
            const uint8_t *val = f + at;
            if (depth == 1) {
                if (equals(key, name_len, "#address-cells")) {
                    if (len != 4) return fail;
                    root_addr_cells = u32be(val);
                } else if (equals(key, name_len, "#size-cells")) {
                    if (len != 4) return fail;
                    root_size_cells = u32be(val);
                }
            } else if (depth == 2 && reserved_depth == 2) {
                if (equals(key, name_len, "#address-cells")) {
                    if (len != 4) return fail;
                    reserved_addr_cells = u32be(val);
                } else if (equals(key, name_len, "#size-cells")) {
                    if (len != 4) return fail;
                    reserved_size_cells = u32be(val);
                }
            }
            if (depth == memory_depth && equals(key, name_len, "reg")) {
                if (root_addr_cells != 2 || root_size_cells != 2) return fail;
                uint32_t dummy_overlap = 0;
                if (!reg_list(val, len, candidate_lo, candidate_hi,
                              &r.ram_bank_count, &r.candidate_in_ram,
                              &dummy_overlap))
                    return fail;
                saw_ram = 1;
            }
            if (depth == reserved_child_depth) {
                if (equals(key, name_len, "reg")) {
                    if (reserved_addr_cells != 2 || reserved_size_cells != 2)
                        return fail;
                    uint32_t unused_contains = 0;
                    if (!reg_list(val, len, candidate_lo, candidate_hi,
                                  &r.fixed_count, &unused_contains,
                                  &r.fixed_conflict))
                        return fail;
                    child_has_reg = 1;
                } else if (equals(key, name_len, "size") && len) {
                    int any = 0;
                    for (uint32_t i = 0; i < len; ++i)
                        any |= val[i] != 0;
                    if (any) child_has_size = 1;
                }
            }
            at += (len + 3U) & ~3U;
            if (at > end_struct) return fail;
        } else if (token == T_NOP) {
            /* Nothing. */
        } else if (token == T_END) {
            complete = (depth == 0);
            break;
        } else {
            return fail;
        }
    }
    if (!complete || !saw_root || !saw_ram ||
        root_addr_cells != 2 || root_size_cells != 2 ||
        (saw_reserved_root &&
         (reserved_addr_cells != 2 || reserved_size_cells != 2)))
        return fail;

    r.valid = 1;
    return r;
}
