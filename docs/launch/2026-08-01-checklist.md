# AgentGuard launch checklist — 2026-08-01

## Release candidate

- [ ] `make check` passes.
- [ ] `cd website && npm run check && npm run build` passes.
- [ ] Wheel and source distribution pass `twine check`.
- [ ] Clean Python 3.12 environment installs the wheel and runs `agentguard --version`.
- [ ] Installed wheel does not pull in FastAPI or the server stack.
- [ ] `make demo-record` ends with `BLOCKED` and exit code `20`.
- [ ] Generated HTML report contains the refund-limit evidence.

## TestPyPI rehearsal

- [ ] In TestPyPI, configure a pending trusted publisher for:
  - owner/repository: `Nagamiji/agentguard`
  - workflow: `publish-cli-test.yml`
  - environment: `testpypi`
- [ ] In GitHub, create the `testpypi` environment without production credentials.
- [ ] Run the **Publish CLI to TestPyPI** workflow manually.
- [ ] Install from TestPyPI in a clean environment:

  ```bash
  python3.12 -m venv /tmp/agentguard-testpypi
  /tmp/agentguard-testpypi/bin/pip install \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    agentguard-dev==0.1.1
  /tmp/agentguard-testpypi/bin/agentguard --version
  ```

- [ ] Confirm the installed version is `0.1.1`.

## Website

- [ ] `/`, `/docs`, `/km/`, `/ja/`, and `/zh-cn/` return successfully.
- [ ] Desktop and mobile layouts have no clipped terminal or code blocks.
- [ ] GitHub, PyPI, Docs, and install links work.
- [ ] Social preview image and description render correctly.
- [ ] Deploy only after the final domain and hosting project are confirmed.

## LinkedIn

- [ ] Record at 1440×900 or 1920×1080 with notifications disabled.
- [ ] Keep the demo between 60 and 90 seconds.
- [ ] Show the actual terminal result and actual generated report.
- [ ] Add captions; many LinkedIn viewers watch muted.
- [ ] Upload the MP4 directly rather than posting only an external link.
- [ ] Put GitHub and PyPI links in the post or first comment.

## Production release — requires founder confirmation

- [ ] TestPyPI rehearsal is green.
- [ ] Main CI and scheduled security workflow are green.
- [ ] Founder approves the exact `0.1.1` artifact and release notes.
- [ ] Merge through the repository's normal human gate.
- [ ] Tag `cli-v0.1.1`; the tag-triggered workflow publishes to production PyPI.
- [ ] Verify `pip install agentguard-dev==0.1.1` from production PyPI.
