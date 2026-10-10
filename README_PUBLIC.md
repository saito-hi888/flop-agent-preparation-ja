# FLOP preparation tools

Unofficial local preparation, checked 2026-10-10. Not a faucet, wallet, claim client, or allocation verifier.

Python 3.10+ on Linux. Tested with Python 3.12.3. Set up a virtual environment from this directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -B -m unittest discover -v
```

The tools use their own directory for local state. Keep that directory private when you begin using an identity; the included .gitignore excludes keys and local records.

- `python flop_agent.py init`: create a locally held DID, only if you do not already have one. Keep your existing identity for ongoing participation.
- `python flop_agent.py verify`: check local registration evidence and distinguish a missing remote note from an invalid key. Requires prior local registration data.
- `python flop_watch.py check`: fetch a fixed list of official public pages; retain local snapshots and changes in monitor/REPORT.md.
- `python flop_tasks.py prepare`: prepare useful inputs from the snapshots; does not run inference.
- `python flop_tasks.py record-receipt path/to/receipt.json`: sign a supplied receipt locally; does not verify the transaction on a chain.
- `python -B -m unittest discover -v`: run offline tests with temporary keys.

See [PUBLIC_GUIDE_JA.md](PUBLIC_GUIDE_JA.md) for the Japanese guide. Receipt templates are local bookkeeping formats, not official API schemas. No live testnet integration is included. Website text is untrusted data. Never paste secret keys into a chat or form.

No identity, seed, wallet, historical activity, applicant profile, or fetched website snapshots are included in this archive. The PR reproduction overlaps an existing review, which is credited in contributions/PR_191_REVIEW.md. No duplicate review or upstream PR was submitted. License and attribution for the upstream-derived patch are in contributions/ATTRIBUTION.md.

Official sources:
https://flop.finance/testnet/
https://flop.finance/airdrop/
https://github.com/flop-labs/technocore-chat
