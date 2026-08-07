/*
 * Reproducible fixture source. The checked-in ELF was built with:
 * arm-none-eabi-gcc 14.3.1 -mcpu=cortex-m4 -mthumb -g3 -Og -nostdlib
 *   -Wl,-e,main -Wl,-Ttext=0x08000000 -Wl,-Tdata=0x20000000
 */
#include <stdbool.h>
#include <stdint.h>

enum RunMode { MODE_IDLE = 0, MODE_RUN = 7 };

typedef int32_t signed_word_t;
typedef const volatile signed_word_t qualified_word_t;

struct Point {
    int16_t x;
    uint16_t y;
};

struct Packet {
    uint8_t tag;
    struct Point point;
    int32_t samples[3];
};

struct Bits {
    unsigned active : 1;
    unsigned count : 7;
};

int8_t signed8 = -7;
uint8_t unsigned8 = 250;
int16_t signed16 = -1234;
uint16_t unsigned16 = 54321;
int32_t signed32 = -1234567;
uint32_t unsigned32 = 3456789012U;
int64_t signed64 = -1234567890123LL;
uint64_t unsigned64 = 12345678901234567890ULL;
bool enabled = true;
float ratio32 = 1.25f;
double ratio64 = -3.5;
enum RunMode mode_known = MODE_RUN;
enum RunMode mode_unknown = (enum RunMode)99;
qualified_word_t qualified = -42;
int32_t values[3] = {11, 22, 33};
struct Packet packet = {5, {-12, 34}, {101, 202, 303}};
int32_t *value_pointer = &values[1];
struct Bits packed_bits = {1, 3};
float _Complex unsupported_complex = 1.0f + 2.0fi;

__attribute__((used, noinline)) int local_case_one(int argument) {
    int ambiguous = argument + 1;
    int register_local = ambiguous * 2;
    const int optimized_out = 123;
    return register_local + optimized_out;
}

__attribute__((used, noinline)) int local_case_two(int argument) {
    int ambiguous = argument - 1;
    return ambiguous;
}

int main(void) {
    return signed8 + (int)packet.tag + local_case_one(2) + local_case_two(2);
}
