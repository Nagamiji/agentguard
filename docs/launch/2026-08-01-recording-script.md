# AgentGuard LinkedIn demo — 75-second recording script

## Before recording

1. Start Docker Desktop and run `make install` once.
2. Set the terminal to a large font and a clean 16:9 window.
3. Close notifications and unrelated tabs.
4. Open the website hero in one tab and the terminal in another.
5. Run one rehearsal with `DEMO_OPEN_REPORT=0 make demo-record`.

## Shot list and voice-over

### 0–8 seconds — the problem

**Screen:** Website hero and the blocked `$9,000` refund finding.

**Voice-over:**

> An AI agent can sound perfectly helpful while making a dangerous tool call. AgentGuard checks the action before deployment.

### 8–18 seconds — the safety boundary

**Screen:** Scroll just enough to show “simulate, never execute.”

**Voice-over:**

> It challenges the agent against policy, intercepts the proposed tool call, and never executes the real refund tool.

### 18–52 seconds — actual terminal demo

**Screen:** Clean terminal. Run:

```bash
make demo-record
```

Let the output reach `BLOCKED`, the `tool_arg_limit` finding, and exit code `20`.

**Voice-over:**

> Here is a deterministic demo. The support agent attempts a nine-thousand-dollar refund. The organization policy caps refunds at one hundred dollars, so AgentGuard produces evidence and returns exit code twenty—the CI build stops.

### 52–66 seconds — evidence report

**Screen:** The generated HTML report opens. Point to the decision, expected limit, observed amount, and fingerprint.

**Voice-over:**

> The result is not just a red badge. The report records the exact configuration, expected boundary, observed action, and reproducible fingerprint.

### 66–75 seconds — call to action

**Screen:** Return to the install command on the website.

**Voice-over:**

> AgentGuard is open source. Install the CLI from PyPI, run the offline check, and tell me which agent framework you want supported next.

## Recording command

Use macOS Screenshot (`Shift` + `Command` + `5`) and select **Record Selected Portion**.
Record the website and terminal region only. Export as MP4, trim dead time, and add burned-in
captions before uploading to LinkedIn.
