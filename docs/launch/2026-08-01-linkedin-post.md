# LinkedIn post draft

An AI agent can write a perfectly polite response—and still attempt a dangerous action.

I built AgentGuard to catch that action before deployment.

In this demo, a customer-support agent follows a prompt injection and attempts a **$9,000 refund**. The policy limit is **$100**. AgentGuard intercepts the proposed tool call, records the evidence, and exits with code `20`, so CI blocks the deployment.

What it does today:

- Offline static checks with no account or API key
- Honest coverage reporting: skipped behavioural tests are never called “passed”
- Behavioural simulation through an AgentGuard control plane
- SARIF and self-contained evidence reports
- Reproducible agent fingerprints and fail-closed exit codes

What it does **not** claim: a static check alone cannot prove how a live model will behave. AgentGuard reports that boundary explicitly.

The CLI is open source and available on PyPI:

`pip install agentguard-dev`

GitHub: https://github.com/Nagamiji/agentguard
PyPI: https://pypi.org/project/agentguard-dev/

I would especially value feedback from people shipping tool-calling agents: which framework should I integrate next?

#AIAgents #AISecurity #OpenSource #DevTools #LLMOps
