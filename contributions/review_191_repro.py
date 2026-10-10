"""Standalone reproduction of the assertion weakness in PR #191; no network."""
import re
edge = "| `CHAT_EDGE_CACHE_SECONDS` | `1` | stale-while-revalidate` at 5 times; 6 seconds old, not 1; 0 disables |"
static = "| `CHAT_STATIC_CACHE_SECONDS` | `300` | stale-while-revalidate` is a flat 60; 360 seconds; 0 disables |"
old_edge = lambda value: value // 2 in {int(n) for n in re.findall(r"\d+", edge)}
new_edge = lambda value: value == 2 * int(re.search(r"at (\d+) times", edge).group(1))
old_static = lambda value: value in {int(n) for n in re.findall(r"\d+", static)}
new_static = lambda value: value == int(re.search(r"flat (\d+)", static).group(1))
assert old_edge(10) and new_edge(10)
assert old_edge(11) and not new_edge(11)
assert old_edge(12) and not new_edge(12)
assert old_static(300) and not new_static(300)
assert old_static(60) and new_static(60)
print("Reproduced false positives; proposed exact comparisons reject them.")
