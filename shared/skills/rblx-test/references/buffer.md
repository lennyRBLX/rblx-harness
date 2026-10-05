# HTB1 buffer protocol

The runner calls `RunService:IsServer()` once per execution. True selects SERVER;
false selects CLIENT. A LocalScript and every called ModuleScript use CLIENT.
Every record and notice is `SIDE|TEST_SCRIPT_NAME|ALL_OTHER_DATA`.

Transport: `SIDE|NAME|BUF|1|RUN|SEQUENCE|COUNT|BYTES|ADLER32|HEX`.
Payload: actual buffer bytes, encoded as lowercase hexadecimal. Do not print the
buffer object. Chunks contain 512 bytes except the final chunk. Sequence is
one-based; count must equal ceil(bytes / 512). Maximum payload is 65,536 bytes,
128 chunks per record, 64 collected runs. Ordering may vary; all chunks must be
present. Identical chunk IDs/bytes are duplicate delivery. Conflicting metadata
or bytes reject the entire result. Equal-valued observations remain distinct.
Adler-32 covers ASCII `SIDE|NAME|RUN`, a zero byte, and the full payload. It detects
transport damage; it is not authentication. Collection requires expected side,
script and run. Reject unsupported versions, lengths, bad checksums, missing
chunks, corrupt rows, conflicting records and incorrect runtime prefixes.

Payload is an ASCII buffer, LF terminated, starting `HTB1\n`. Fields are separated
by TAB; rows follow in this order:

- `R ID STATUS PASSED FAILED SKIPPED REASON`
- `M METHOD WORKLOAD KIND COUNT TOTAL_US MAX_US THRESHOLD_US SPIKES OVERFLOW WINDOW_US`
- `P METHOD WORKLOAD KIND INDEX DURATION_US` for each stored spike after its M row.

Identifiers are 1–96 characters from letters, digits, underscore, dot, colon,
slash and hyphen. Status is pass, fail, cancelled, timeout or unrun. Reasons are
at most 160 printable ASCII characters without a pipe; `-` means absent. A pass
requires at least one assertion and no failures. Other statuses need a reason.
At most 32 metrics. Kinds: script, scheduling, setup, teardown. Frame claims require the independent
profiler pipeline. Durations are integer microseconds, rounded to nearest 1 us;
integers are nonnegative and at most 2^53−1. Missing observations have no M row;
missing values are never zero. Thresholds are positive and fixed before execution.
A spike is strictly greater than its threshold. P indices are one-based observation
indices. Store at most 256 spikes; overflow plus stored spikes equals SPIKES.
No trailing rows or fields, NaN, infinity, unsupported kind or duplicate metric.

Summaries show average first (total/count, in ms to three decimals), spikes second.
No dates, wall-clock times, builds, tick values, repeated metadata, per-case success
messages or raw buffers. Run metadata stays once in existing artifacts. Concise
failure reasons and required control notices remain visible, as do relevant errors
outside marker filters. Historical `TEST|` JSON results and native profiler exports
have separate readers; no new authored test or normal decoded summary uses JSON.
