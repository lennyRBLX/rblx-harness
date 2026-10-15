# React evidence limits

Reuse only within these scopes; recheck changed packages/workloads. Environment:
Studio `0.737.0.7371584`, Apple M4, React/ReactRoblox 17.2.1.

| ID | Evidence | Supported conclusion / limit |
|---|---|---|
| P-react | 18 CPU captures, 1/50/200 dots, 48 synchronous flushSync updates, equal host trees and human-confirmed motion. State scope totals: 7.53–10.79× bindings; CPU frame p95 ranges overlapped. | Use bindings for intermediate values in this workload; no FPS or concurrent-scheduling claim. |
| P-cleanup | 100 removal cycles × 200 useAnimation controllers per policy, delayed/active tweens. All 20,000 unstopped controllers retained listener activity; explicit stop prevented callbacks/value changes after removal or stop return. Hosts/refs detached; stopped-idle checks passed. | Own stop handles. No internal task, connection, GC or leak claim. |

For new comparisons, match native/React host trees and retain wiring, refs, keys
and effect timing. Equal appearance does not prove equal update cost.
