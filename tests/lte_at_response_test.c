#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "lte_at_response.h"

static bool feed(lte_at_response_t *state, const char *data, size_t size)
{
    bool ok = false;
    for (size_t i = 0; i < size; ++i) {
        ok |= lte_at_response_feed(state, (uint8_t)data[i]);
    }
    return ok;
}

int main(void)
{
    lte_at_response_t state = {0};
    assert(!feed(&state, "AT\r\n", 4)); // Echo alone is insufficient.
    assert(!feed(&state, "O", 1));
    assert(!feed(&state, "K", 1));
    assert(feed(&state, "\r\n", 2)); // Chunk-split OK needs a terminator.

    const char *bad[] = {
        "BROKEN\r\n", "NOK\r\n", "OKAY\r\n", " OK\r\n", "OK \r\n",
        "ERROR\r\n", "ok\r\n", "ATOK\r\n", "O\rK\r", "\x7fOK\r"
    };
    for (size_t i = 0; i < sizeof(bad) / sizeof(bad[0]); ++i) {
        state = (lte_at_response_t){0};
        assert(!feed(&state, bad[i], strlen(bad[i])));
    }
    const char binary[] = {'O', 0, 'K', '\n', 'O', 'K'};
    state = (lte_at_response_t){0};
    assert(!feed(&state, binary, sizeof(binary)));
    assert(feed(&state, "\n", 1)); // Recovery only after line boundary.

    state = (lte_at_response_t){0};
    for (int i = 0; i < 100; ++i) assert(!lte_at_response_feed(&state, 'X'));
    assert(!feed(&state, "OK\r", 3)); // Overlong prefix cannot expose suffix.
    assert(feed(&state, "\nOK\n", 4));
    state = (lte_at_response_t){0};
    const char response[] = "\r\n+CPIN: READY\r\nAT\r\nOK\r\n";
    assert(feed(&state, response, sizeof(response) - 1));
    puts("LTE AT response parser: PASS (echo, split/terminated OK, binary, overflow, recovery)");
    return 0;
}
