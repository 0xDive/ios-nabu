#ifndef NABU_STAGE6_SURVEY_H
#define NABU_STAGE6_SURVEY_H
#include <stdint.h>
#include <stddef.h>
/* Strictly read-only inventory of the FDT actually passed in bootloader mode.
 * All checks are descriptive; no possible result authorizes physical writes. */
struct survey_result {
    uint8_t fdt_valid;
    uint8_t root_cells_2_2;
    uint8_t reserved_cells_2_2;
    uint8_t candidate_inside_dram;
    uint8_t fixed_overlap;
    uint8_t dynamic_unresolved;
    uint8_t ramdisk_present;
    uint8_t ramdisk_overlap;
    uint8_t fdt_self_overlap;
    uint8_t reserve_table_valid;
    uint8_t reserve_table_overlap;
    uint32_t reserve_entries;
    uint32_t dynamic_nodes;
};
struct survey_result survey_fdt(const void *dtb, uint64_t candidate_start, uint64_t candidate_end);
#endif
