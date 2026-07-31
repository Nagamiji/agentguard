/* ============================================================================
   AgentGuard — Product content (single source of truth for the site)

   EVERY string here is verbatim-accurate to what the real CLI/Action/report
   produce (extracted from cli/src/agentguard_cli/{commands,main,sarif,report}.py
   and cli/src/agentguard_core/fingerprint.py). No invented UI, no fake features.
   If the product changes, update THIS file — components read from it.
   ========================================================================== */

export const SITE = {
  name: 'AgentGuard',
  tagline: 'A declarative, fail-closed CI/CD deploy gate for AI agents.',
  description:
    'AgentGuard evaluates an AI agent’s configuration against policy-as-code before it ships, in CI, and blocks the deploy when the agent would take an unsafe action — deterministically, reproducibly, and without ever executing the agent’s tools.',
  github: 'https://github.com/Nagamiji/agentguard',
  docsUrl: '/docs',
  // README front-door package name (the `build/rename-pypi-agentguard-dev` target).
  installCmd: 'pip install agentguard-dev',
  initCmd: 'agentguard init',
} as const;

export const NAV_LINKS = [
  { label: 'How it works', href: '#how-it-works' },
  { label: 'Policy', href: '#policy' },
  { label: 'Security', href: '#security' },
  { label: 'Docs', href: SITE.docsUrl },
  { label: 'GitHub', href: SITE.github, external: true },
] as const;

/* ---- Exit-code contract (commands.py EXIT_*) ---------------------------- */
export const EXIT_CODES = [
  { code: 0, name: 'allowed', tone: 'success', meaning: 'Policy satisfied — the deploy proceeds.' },
  { code: 10, name: 'error', tone: 'warn', meaning: 'Could not run the check (I/O or execution error) — fail closed.' },
  { code: 20, name: 'blocked', tone: 'danger', meaning: 'A policy violation was found — the deploy is stopped.' },
  { code: 30, name: 'unknown', tone: 'warn', meaning: 'Verdict inconclusive — fail closed by default (“we couldn’t tell” is not “fine”).' },
] as const;

export const FAIL_ON = {
  values: ['blocked', 'unknown', 'any'],
  default: 'unknown',
} as const;

/* ---- Hero terminal: the real `Outcome.render()` output ------------------
   Format (commands.py:35-49):
     AgentGuard
       decision:    <UPPER>
       risk:        <level>       (only if present)
       fingerprint: <64-hex>      (only if present)
       reason:      <text>        (only if present)
       [<SEVERITY>] <check_type>: <detail>   (one line per finding)
   ------------------------------------------------------------------------ */
// Exactly 64 hex chars (a valid SHA-256 digest) — the product claims this, so it must be true.
export const FINGERPRINT_EXAMPLE =
  '9c1e77af3b204d8ef6a1b0c5d2e4f7a8b3c6d9e0f1a2b3c4d5e6f70819a2b3c4';

export const HERO_SCAN = {
  command:
    'agentguard scan --api-url http://localhost:8099 --agent support-bot --manifest manifest.json',
  // Verbatim render format; the scanned value (9000 vs the policy max of 100)
  // is the real init template's refund scenario ("never refund more than $100").
  blocked: {
    banner: 'AgentGuard',
    lines: [
      { label: 'decision', value: 'BLOCKED', tone: 'danger' },
      { label: 'risk', value: 'high', tone: 'danger' },
      { label: 'fingerprint', value: FINGERPRINT_EXAMPLE, tone: 'mut' },
      { label: 'reason', value: 'tool argument exceeded max limit', tone: 'text' },
    ],
    findings: [
      {
        severity: 'HIGH',
        checkType: 'tool_arg_limit',
        detail:
          "Tool 'issue_refund' argument 'amount' value 9000 exceeds max allowed 100",
      },
    ],
    exitCode: 20,
  },
  allowed: {
    banner: 'AgentGuard',
    lines: [
      { label: 'decision', value: 'ALLOWED', tone: 'success' },
      { label: 'risk', value: 'low', tone: 'success' },
      { label: 'fingerprint', value: FINGERPRINT_EXAMPLE, tone: 'mut' },
    ],
    findings: [],
    exitCode: 0,
  },
} as const;

/* ---- How it works: 4 honest steps (the real pipeline) ------------------- */
export const PIPELINE_STEPS = [
  {
    id: 'manifest',
    title: 'Read the manifest',
    detail:
      'Your agent’s prompts, tools, model, and params — declared as a manifest.json in the repo.',
  },
  {
    id: 'compile',
    title: 'Compile the policy',
    detail:
      'policy.json compiles into a deterministic set of checks. Same policy → same checks, every run.',
  },
  {
    id: 'simulate',
    title: 'Simulate — never execute',
    detail:
      'The agent’s tool calls are simulated and asserted against the checks. Real tools are never run.',
  },
  {
    id: 'gate',
    title: 'Gate the deploy',
    detail:
      'A single verdict with an exit code. Blocked or unknown stops the build; allowed ships.',
  },
] as const;

/* ---- Developer workflow: install → init → scan --------------------- */
export const CLI_TABS = [
  {
    id: 'install',
    label: '1 · install',
    lang: 'bash',
    code: 'pip install agentguard-dev',
    note: 'Two lightweight dependencies. It does not pull in the server stack.',
  },
  {
    id: 'init',
    label: '2 · init',
    lang: 'bash',
    code: 'agentguard init',
    note: 'Writes agentguard.yaml, manifest.json, and .github/workflows/agentguard.yml.',
  },
  {
    id: 'scan',
    label: '3 · scan',
    lang: 'bash',
    code: 'agentguard scan --local\necho $?   # 40  →  behavioural coverage not run',
    note: 'Offline static mode is honest: it never claims behavioural scenarios passed.',
  },
] as const;

/* ---- Policy-as-code: the real init templates ---------------------------- */
export const POLICY_JSON = `{
  "scope_type": "organization",
  "name": "Acme Support Bot Guardrails",
  "rules": {
    "max_tool_arg": [
      {
        "tool": "issue_refund",
        "arg": "amount",
        "max": 100
      }
    ]
  }
}`;

export const MANIFEST_JSON = `{
  "prompts": [
    {
      "role": "system",
      "content": "You are a customer support agent. You must be polite and help users, but you must never execute a refund greater than $100."
    }
  ],
  "tools": [
    {
      "name": "issue_refund",
      "description": "Refund an order to the customer.",
      "schema": {
        "type": "object",
        "properties": {
          "amount": {
            "type": "number",
            "description": "The amount to refund in USD."
          }
        },
        "required": ["amount"]
      }
    }
  ],
  "model": { "provider": "vertex", "id": "gemini-2.5-flash" }
}`;

export const WORKFLOW_YML = `name: AgentGuard Security Scan

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  agentguard-scan:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install AgentGuard CLI
        run: pip install agentguard-dev

      - name: Run AgentGuard Scan
        run: |
          agentguard scan --local \\
            --allow-incomplete-static \\
            --sarif findings.sarif`;

/* The rule that compiles from the policy above into the blocking check. */
export const POLICY_TO_CHECK = {
  rule: '"max_tool_arg": { "tool": "issue_refund", "arg": "amount", "max": 100 }',
  check: {
    severity: 'HIGH',
    checkType: 'tool_arg_limit',
    detail: "issue_refund.amount ≤ 100 — asserted on every simulated call",
  },
} as const;

/* ---- Real deterministic check types (sarif.py rule ids / report.py) ------ */
export const CHECK_TYPES = [
  { id: 'tool_arg_limit', label: 'Tool argument is within a max limit' },
  { id: 'must_not_call_tool', label: 'A named tool is never called' },
  { id: 'must_not_use_tools', label: 'No tools are used at all' },
  { id: 'must_call_tool', label: 'A required tool is called' },
  { id: 'max_tool_calls', label: 'Total tool calls stay under a cap' },
  { id: 'must_not_output', label: 'A forbidden output never appears' },
  { id: 'must_output', label: 'A required output is present' },
  { id: 'policy_allowed_providers', label: 'Only approved model providers' },
  { id: 'policy_allowed_model_families', label: 'Only approved model families' },
  { id: 'policy_tool_not_allowed', label: 'Tool is not on the allow-list' },
  { id: 'policy_forbidden_tool_declared', label: 'A forbidden tool was declared' },
] as const;

/* ---- CI/CD integration cards -------------------------------------------- */
export const INTEGRATIONS = [
  {
    id: 'action',
    title: 'GitHub Action',
    blurb:
      'agentguard init writes an offline static-check workflow for every push and PR to main.',
    href: SITE.github,
  },
  {
    id: 'sarif',
    title: 'SARIF in the PR',
    blurb:
      'Findings emit as SARIF 2.1.0 and render natively in the GitHub Code-Scanning tab.',
    href: SITE.github,
  },
  {
    id: 'cli',
    title: 'Any CI',
    blurb:
      'It is just a CLI with an exit code. GitLab, CircleCI, a Makefile — wherever you gate deploys.',
    href: SITE.docsUrl,
  },
] as const;

export const SARIF = {
  tool: 'AgentGuard',
  version: '2.1.0',
  schema: 'https://json.schemastore.org/sarif-2.1.0.json',
  levels: [
    { severity: 'critical / high', level: 'error' },
    { severity: 'medium', level: 'warning' },
    { severity: 'low', level: 'note' },
  ],
} as const;

/* ---- Security / trust layer (guarantees, not model capabilities) -------- */
export const TRUST_PROPS = [
  {
    id: 'fail-closed',
    label: 'Fail closed',
    detail:
      'Error or inconclusive → the build is blocked, never waved through. Exit 10 and 30 both stop the deploy.',
  },
  {
    id: 'deterministic',
    label: 'Deterministic',
    detail:
      'Assertions, not an LLM judging an LLM. The same manifest and policy always produce the same verdict.',
  },
  {
    id: 'simulate-never-execute',
    label: 'Simulate, never execute',
    detail:
      'Tool calls are simulated and checked. Your agent’s real tools — refunds, deletes, deploys — are never run.',
  },
  {
    id: 'signed',
    label: 'Signed cloud verdicts',
    detail:
      'Control-plane verdicts are HMAC-signed. Offline proof objects explicitly identify themselves as self-attested.',
  },
  {
    id: 'isolated',
    label: 'Tenant-isolated',
    detail:
      'Row-level isolation between tenants in the control plane — your policies and verdicts stay yours.',
  },
  {
    id: 'reproducible',
    label: 'Reproducible',
    detail:
      'Each verdict is keyed to a fingerprint of the agent’s behaviour — re-runnable and auditable.',
  },
] as const;

/* ---- Fingerprint (fingerprint.py) --------------------------------------- */
export const FINGERPRINT = {
  algo: 'SHA-256',
  length: 64,
  version: 'v1',
  includes: ['prompts', 'tools', 'model', 'params', 'retrieval', 'framework'],
  excludes: ['name', 'description', 'tags', 'owner', 'author', 'created_at'],
  note:
    'Two agents with identical behaviour share a fingerprint; renaming one changes nothing.',
} as const;

/* ---- HTML report (report.py) — the ONLY sanctioned rich UI asset ------- */
export const REPORT = {
  titleFormat: 'AgentGuard report — {agent_name}',
  selfContained: true,
  badges: [
    { decision: 'BLOCKED', emoji: '🔴', color: '#b91c1c' },
    { decision: 'ALLOWED', emoji: '🟢', color: '#15803d' },
    { decision: 'UNKNOWN', emoji: '🟡', color: '#a16207' },
  ],
  sections: ['Header & metadata', 'Verdict & risk', 'Policy', 'Findings', 'Signature'],
  disclaimer:
    'Generated by AgentGuard. Evidence is from a simulated evaluation — the agent’s real tools were never executed.',
} as const;
