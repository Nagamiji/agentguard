"""AgentGuard CLI — the deployment gate a developer runs in CI.

`agentguard scan` evaluates an agent version against its scenarios and policy, prints the
verdict, optionally writes SARIF, and exits non-zero when the deploy must be blocked. That
non-zero exit is the whole product wedge: it is what makes a CI step fail and stop a merge.

Fail closed: any error, or a verdict of `unknown`, exits non-zero by default. A gate that
exits 0 when it could not tell is not a gate.
"""

__version__ = "0.1.0"
