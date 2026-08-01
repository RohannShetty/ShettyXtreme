# Triage Labels

Triage state is recorded as a `Status:` line near the top of each issue file.

## Vocabulary

| Label | Meaning |
|---|---|
| `needs-triage` | Newly filed; not yet categorised or verified |
| `needs-info` | Waiting on missing information from the reporter or the user |
| `ready-for-agent` | Verified and agent-actionable; an agent may pick it up |
| `ready-for-human` | Verified but requires a human decision or hands-on action |
| `wontfix` | Closed by decision — won't be fixed (with reason recorded) |

These are the default role strings; the local-markdown tracker stores them verbatim in the `Status:` line of each issue file under `.scratch/<feature-slug>/issues/`.
