# Maintainer setup and releases

This checklist separates contributor readiness from a stable software release.
The repository files cannot activate GitHub settings. Complete steps 1–6 before
advertising Prism as ready for outside contributions. Keep the project labeled alpha.

## 1. Merge the readiness PR

Wait for package, documentation, VST and CodeQL checks. Review the diff and squash
merge the PR. Confirm the same workflows pass on main. Do not merge using a blanket
bypass of failing checks. If CodeQL default setup already exists, use one setup mode:
disable default setup and retain this repository's advanced workflow.

## 2. Require passing checks for everyone

Open **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.
Name it **Main quality**, set **Active**, and target the default branch.
Leave the bypass list empty. Enable:

- Restrict deletions.
- Block force pushes.
- Require a pull request before merging, with zero required approvals in this rule.
- Require status checks to pass and require the branch to be up to date.

Add the following checks after they have run successfully. Select GitHub Actions
as the expected source where offered. Use the actual check names in the PR UI:

| Check | Purpose |
| --- | --- |
| Python package (ubuntu-latest) | Tests, coverage, lint, typing and package build |
| Python package (windows-latest) | Same checks on Windows |
| Build documentation | Strict docs build and rendered example |
| Real VST3 (ubuntu-latest) | Real plugin rendering on Linux |
| Real VST3 (windows-latest) | Real plugin rendering on Windows |
| CodeQL (python) | Python security analysis completes |
| CodeQL (actions) | Workflow security analysis completes |

A successful CodeQL analysis does not mean zero alerts: review its findings in the
Security tab. Add code-scanning merge protection for high/critical alerts where
available. Do not require Deploy documentation: it only runs after a push to main.

## 3. Require your approval without locking out your own PRs

Edit existing **Main Protection** to handle review only (Main quality already
protects CI and branch history). Keep it Active and targeting the default branch.
Require a PR, one approval, code-owner review, stale-approval dismissal, approval
of the most recent reviewable push, and resolution of review conversations.

Remove the integration's Always bypass entry. Change administrator bypass to
**For pull requests only**. Keep yourself as the only administrator. Do not add
write-role, app or bot bypass entries. Existing rules combine; review any other
rulesets/classic protections for unexpected bypasses or approval requirements.

Outside PRs need your approval. For a PR you authored, use the review-only
administrator bypass after reviewing your diff; GitHub does not allow self-approval.
Main quality still enforces passing CI and a PR. If you later add administrators,
revisit this exception: the admin role grants it to all administrators.

## 4. Configure security and Actions

Under **Settings → Code security** (sometimes **Code security and analysis**):

- Enable dependency graph, Dependabot alerts and security updates.
- Enable secret scanning and push protection where offered.
- Enable private vulnerability reporting. Confirm the Report a vulnerability
  button appears under Security; this activates the route in SECURITY.md.
- Review CodeQL results for Python and Actions. Weekly dependency updates are
  configured in .github/dependabot.yml and start after merge.

Under **Settings → Actions → General**:

- Require workflow approval for all outside collaborators.
- Set default workflow token permissions to read-only.
- Leave Actions creating/approving PRs disabled unless a reviewed workflow needs it.
- Keep fork PRs on GitHub-hosted runners; never attach a personal workstation runner.
- Never expose secrets or write tokens to fork PRs. Keep deployment privileges in
  the separate deployment job; restrict the github-pages environment to main.

## 5. Secure ownership and test the contribution flow

Review **Settings → Collaborators** and installed GitHub Apps. Keep administrative
access with the lead maintainer and remove unused integrations. Contributors can
fork and open PRs without write access. Protect your account with a passkey/2FA and
store recovery codes safely. Publish a private conduct-reporting contact on your
profile if you want a maintainer channel in addition to GitHub's reporting tools.

Open a harmless PR from a separate contributor account/fork. Verify that your
review is requested, workflows need outside-contributor approval, and the PR cannot
merge without passing checks and your review. Close it when done. Inspect the
rules UI to confirm Main quality has no bypass actors. This is the readiness gate.

## 6. Record remaining limitations

- Shared song scripts and native plugins must be trusted; subprocess isolation is
  not a sandbox. A hung VST worker currently has no operation deadline. This remains
  a runtime-hardening task; do not offer an untrusted rendering service.
- Surge 1.3.4 installers are pinned by SHA-256 before installation. Their upstream
  release metadata has no SHA-256 digest; the pins were observed from the fixed
  publisher URLs in [CI run 33977585860](https://github.com/SeucheAchat9115/Prism/actions/runs/33977585860).
  This records downloaded bytes, not an independent publisher signature. When
  upgrading, review the upstream release and update URLs and hashes together in
  a PR. Never replace expected hashes automatically from the download being checked.
- No complete repository-history secret scan or dependency vulnerability audit is
  claimed. Review security alerts and rotate any exposed credential rather than
  merely deleting it from the latest source.

These limitations do not prevent trusted contributors from collaborating on alpha
software. They do prevent calling the project fully audited or production hardened.

## Preparing the first versioned release

A GitHub release is not required to accept contributions. When ready to publish:

1. Choose an alpha version, update pyproject.toml and src/prism/version.py together,
   update version assertions/examples/docs, and regenerate uv.lock with uv lock.
2. Update CHANGELOG.md with delivered features, breaking changes and known issues.
3. Run the contributor checks and uv build. Inspect the wheel and source archive
   for the complete license and unintended private assets. Install the wheel in a
   clean Python 3.12 environment and render the generated starter song outside the
   source checkout. Test without VST extras to preserve the headless path.
4. Merge the release PR only after required CI passes. Create a v-prefixed tag on
   that reviewed commit; publish a GitHub pre-release with the alpha label and
   changelog. Do not move a published tag to new code.
5. Before the first tag, add an active tag ruleset targeting v* that blocks updates
   and deletions without bypass. Keep tag creation/release authority with the lead
   maintainer. An organization can provide finer-grained roles later if needed.
6. PyPI publishing is a separate decision. Confirm package-name ownership first;
   configure trusted publishing with a protected release environment rather than
   adding a long-lived publishing token. Do not assume the name prism is available.

## GitHub references

- [Creating rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
- [Code owners](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)
- [Repository security](https://docs.github.com/en/code-security/getting-started/quickstart-for-securing-your-repository)
- [Secure Actions](https://docs.github.com/en/actions/reference/security/secure-use)
