"""The evaluation engine: decide whether an agent version is safe to deploy.

Design: ADR 0008. The agent's decision-making is simulated; its tools are never executed.
What the agent *tried* to do is the signal.
"""
