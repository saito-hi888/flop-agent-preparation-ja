# Documentation discrepancy: Agent introduction vs airdrop unlock rules

Prepared 2026-10-10. Not submitted to FLOP Labs.

The current Agent introduction says the agent release schedule is still open. The Airdrop page and Yellow Paper §8.2 instead describe spend-based release at a 3:1 ratio. The pages are presented as drafts, but readers cannot tell whether the Agent introduction is stale or the newer rule is still awaiting a particular approval.

Sources:
- https://flop.finance/intro/agent/ — Swaps and the airdrop
- https://flop.finance/airdrop/ — Unlock terms
- https://flop.finance/intro/yellowpaper/ — §8.2, R8.7–R8.8

Suggested correction: make the Agent introduction reference the current Yellow Paper rule and explicitly label it provisional. If release conditions are intentionally still open, annotate the Airdrop page to explain the status instead. Confirm the authoritative interpretation before changing protocol semantics.

Impact: users may confuse allocation with immediately transferable funds or misunderstand which stage of spending unlocks the grant. This is a documentation discrepancy, not a reported vulnerability.

The local monitor stores retrieval timestamps and content hashes in monitor/state.json. Re-check the live pages and existing reports before submitting. No source repository for the website was identified, so this is a report draft rather than a fabricated website patch.
