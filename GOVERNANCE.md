# Governance

Prism uses a lead-maintainer model. Maximilian Menke (@SeucheAchat9115) leads the
project and has final authority over scope, architecture, contribution acceptance,
maintainer appointments and official releases. Discussion and technical evidence
inform decisions; contributing does not automatically grant voting or merge rights.

Contributors propose changes through issues and pull requests. The lead maintainer
may decline work that does not fit Prism's goals, with an explanation when practical.
Disagreements should focus on the technical tradeoffs and remain respectful.

Only explicitly appointed maintainers receive write access. Administrative access
and release authority remain with the lead maintainer unless explicitly delegated.
Automation may prepare PRs and checks but must not replace human acceptance decisions.
Code-owner review must be enabled in GitHub settings to enforce CODEOWNERS.

The lead maintainer cannot approve their own PR. A documented PR-only administrator
bypass may satisfy the review rule for their own work; required CI remains enforced
by a separate ruleset without bypass actors. Do not bypass failing checks.

Official releases come from this repository and are authorized by the lead maintainer.
Contributors retain their copyrights. This governance policy controls the official
project; it does not remove rights granted by the software license.
