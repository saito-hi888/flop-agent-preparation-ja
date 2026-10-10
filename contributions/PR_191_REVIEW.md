# Independent reproduction for technocore-chat PR #191

Prepared 2026-10-10. Not submitted: a pre-publication check found the same edge/static number-membership issue already reported by Minh3132:
https://github.com/flop-labs/technocore-chat/pull/191#pullrequestreview-5132077664

This document preserves an independent reproduction and a possible implementation of that existing suggestion. It is not a claim of a new upstream finding. The reproduction also covers integer-division truncation at an edge SWR value of 11.

PR: https://github.com/flop-labs/technocore-chat/pull/191
Reviewed head: `3894ba3a38830350ade5ba5254a4b3c23efed891`
Current main checked: `0e47f770b13cc27e1e2e199d4cdf70a4778c97cc`

## Finding

The new test can still pass after the cache policy drifts from the README. Its edge assertion checks whether an integer-divided multiplier appears anywhere among the row's digits. That row contains both the documented multiplier 5 and the combined window 6. With EDGE_CACHE_SECONDS=2, changing stale-while-revalidate from 10 to 12 therefore passes even though the stated multiplier remains 5. A value of 11 also passes because integer division truncates it.

The static assertion has the same issue: the row contains 300 and 360 as well as the stated fixed 60. A header changed to 300 passes the membership assertion.

Suggested change: extract the number from the specific multiplier/fixed-seconds phrase and compare the exact header value. The attached patch is against this PR's head, available as supporting material for the existing review; no competing PR or duplicate comment was submitted.

## Validation and limits

Isolated reproductions passed: the original predicates accept edge values 11 and 12 and static value 300; the suggested predicates reject those while accepting edge 10 and static 60. This validates the assertion defect, not the full upstream test suite. The upstream suite was not run.

Current main still contains the cache-header calculation; matching implementation lines:

```python
stale-while-revalidate, and defaults to the 5x the polled reads have always used).
f"public, max-age=0, s-maxage={secs}, stale-while-revalidate={swr or secs * 5}"
`stale-while-revalidate` is a flat 60 rather than the 5x the polled reads use. 5x300 is
holds the copy instead, and `stale-while-revalidate` lets it answer from that copy while
```

Patch: `pr-191-assertions.patch`. Re-check the PR head before applying or submitting.
