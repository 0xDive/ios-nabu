/* Freestanding byte copies/zeroing required by Clang's ARM64 struct ABI.
 * All destinations belong to the diagnostic's own stack/structs.
 * Do not implement any physical memory allocator or MMIO.
 */
#include <stddef.h>
#include <stdint.h>

void *memset(void *dst, int value, size_t count)
{
    volatile uint8_t *p = (volatile uint8_t *)dst;
    for (size_t i = 0; i < count; ++i)
        p[i] = (uint8_t)value;
    return dst;
}

void *memcpy(void *dst, const void *src, size_t count)
{
    volatile uint8_t *d = (volatile uint8_t *)dst;
    const volatile uint8_t *s = (const volatile uint8_t *)src;
    for (size_t i = 0; i < count; ++i)
        d[i] = s[i];
    return dst;
}

void *memmove(void *dst, const void *src, size_t count)
{
    volatile uint8_t *d = (volatile uint8_t *)dst;
    const volatile uint8_t *s = (const volatile uint8_t *)src;
    if ((uintptr_t)dst < (uintptr_t)src) {
        for (size_t i = 0; i < count; ++i) d[i] = s[i];
    } else if (dst != src) {
        while (count) { --count; d[count] = s[count]; }
    }
    return dst;
}
