# Win64 Phase 3 — DnsProbe hang on real Windows

**Symptom (host stack):** `select` / `Java_libcore_io_Linux_poll` blocked forever under
`ServerSocket.accept` → `IoBridge.poll(..., -1)`.

**Cause:**
1. `DnsProbe` did **not** call `server.setSoTimeout(...)`. Java maps SO_TIMEOUT 0 to
   `poll(fd, POLLIN, -1)` (infinite) in `PlainSocketImpl.socketAccept`.
2. Client connected to `"localhost"`, which on many Win10 systems resolves to **`::1`**,
   while the server was bound only to **`127.0.0.1`**. Client failed; accept never completed.

**Fix:**
- Resolve/assert localhost separately.
- Connect data path to `InetAddress.getByName("127.0.0.1")`.
- Set `server.setSoTimeout(10000)` (and peer timeouts).
- GoldenApp also got `server.setSoTimeout(15000)` so a failed client cannot hang the suite.

**Note:** Infinite poll is valid Java for timeout 0; product apps should set SO_TIMEOUT when
they need bounded accept. Host suite probes must always set it.
