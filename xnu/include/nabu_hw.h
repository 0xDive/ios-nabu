/*
 * Xiaomi Pad 5 (nabu) — verified properties from one running-Android FDT.
 * Reference values ONLY. NOT an XNU PlatformExpert, memory allocator, or driver.
 *
 * Copyright (c) 2026 ios-nabu contributors. SPDX-License-Identifier: MIT
 */
#ifndef IOS_NABU_HW_H
#define IOS_NABU_HW_H

#define NABU_SOC_QCOM_SM8150 1
#define NABU_CPU_COUNT 8U
#define NABU_ARCH_TIMER_HZ 19200000U
#define NABU_ARM_VTIMER_INTID 19U

#define NABU_GICD_PA 0x17A00000ULL
#define NABU_GICD_SIZE 0x10000ULL
#define NABU_GICR_PA 0x17A60000ULL
#define NABU_GICR_SIZE 0x100000ULL

#define NABU_UFS_BASE_PA 0x01D84000ULL
#define NABU_UFS_MMIO_SIZE 0x2500ULL

/*
 * Reserved splash address, NOT validated framebuffer.
 * MUST NOT use this constant for direct physical memory writes.
 */
#define NABU_SPLASH_RESERVED_PA 0x9C000000ULL
#define NABU_SPLASH_RESERVED_SIZE (36ULL * 1024ULL * 1024ULL)

/*
 * Only observed on a DTB captured from running Android.
 * Bootloader-supplied FDT and transient boot allocations can differ.
 * DO NOT assume any high-memory range is writable/free based on this file.
 */
#define NABU_PSCI_SMC 1
#define NABU_PSCI_VERSION_MAJOR 1U
#define NABU_PSCI_VERSION_MINOR 0U

#endif
