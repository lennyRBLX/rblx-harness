# HTB1 protocol

Use shared TestSupport/collector; do not reimplement this codec for a test.

## Transport

Call `RunService:IsServer()` once: true → SERVER, false → CLIENT. LocalScripts
and their ModuleScripts use CLIENT. Every record/notice starts
`SIDE|TEST_SCRIPT_NAME|`.

`SIDE|NAME|BUF|1|RUN|SEQUENCE|COUNT|BYTES|ADLER32|HEX`

- Encode actual buffer bytes as lowercase hex, not the buffer object.
- Chunks: 512 bytes except final; one-based sequence; count = ceil(bytes/512).
  Limits: 65,536 payload bytes, 128 chunks/record, 64 collected runs.
- Adler-32 covers ASCII `SIDE|NAME|RUN`, zero byte, full payload; damage detection,
  not authentication.
- Require expected side/script/run and all chunks; order may vary. Identical
  chunk IDs/bytes are duplicate delivery; equal observations remain distinct.
  Reject conflicting metadata/bytes, unsupported versions, invalid lengths,
  checksums, rows or runtime prefixes.

## Payload

ASCII, LF-terminated, starts `HTB1\n`; TAB-separated fields, ordered rows:

```text
R ID STATUS PASSED FAILED SKIPPED REASON
M METHOD WORKLOAD KIND COUNT TOTAL_US MAX_US THRESHOLD_US SPIKES OVERFLOW WINDOW_US
P METHOD WORKLOAD KIND INDEX DURATION_US
```

Each P follows its M. Identifiers: 1–96 letters/digits/underscore/dot/colon/slash/
hyphen. Status: pass/fail/cancelled/timeout/unrun. Pass requires assertions and no
failures; other statuses require reason. Reason: ≤160 printable ASCII, no pipe;
`-` is absent.

≤32 metrics; kinds: script/scheduling/setup/teardown. Durations: nearest integer
microsecond; integers: 0..2^53−1. Missing observations omit M, never imply zero.
Positive thresholds are fixed before execution; spike means strictly greater.
One-based P observation indices; ≤256 stored spikes, stored + overflow = SPIKES.
Reject trailing rows/fields, nonfinite values, unsupported kinds and duplicate metrics.

## Display

Average first (total/count, ms to three decimals), spikes second. Keep metadata
once in artifacts; omit dates, clocks, builds, ticks, per-case success and raw
buffers. Preserve concise failure/control notices and relevant errors outside
marker filters. Historical TEST JSON and native profiler exports have separate
readers. New test output and normal summaries never use JSON.
