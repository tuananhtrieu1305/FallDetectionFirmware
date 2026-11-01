#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Streaming line recognition, including split UART reads. An invalid/overlong
 * line stays invalid through its terminator; never accept an embedded OK.
 */
typedef struct {
    char line[64];
    size_t used;
    bool invalid;
} lte_at_response_t;

static inline bool lte_at_response_feed(lte_at_response_t *state, uint8_t byte)
{
    if (byte == '\r' || byte == '\n') {
        bool ok = !state->invalid && state->used == 2 &&
                  state->line[0] == 'O' && state->line[1] == 'K';
        state->used = 0;
        state->invalid = false;
        return ok;
    }
    if (byte < 32 || byte > 126 || state->used == sizeof(state->line)) {
        state->invalid = true;
    } else if (!state->invalid) {
        state->line[state->used++] = (char)byte;
    }
    return false;
}
