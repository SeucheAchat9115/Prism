# Security policy

Prism is alpha software. Security fixes currently target the latest main branch;
older snapshots have no separate maintenance promise. This is not a claim that
main has been exhaustively audited or is suitable for untrusted workloads.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/SeucheAchat9115/Prism/security/advisories/new).
The repository owner must enable this feature before inviting contributors.
If the private reporting option is unavailable, do not disclose exploit details in
a public issue. Ask the maintainer to enable it, without including sensitive details.
Include affected commit/version, reproduction steps, impact and a suggested fix if
available. Do not include real secrets or private audio. There is no guaranteed
response time; coordinated fixes and disclosure are preferred.

## Trust boundaries

A Prism song is executable Python. Running a downloaded main.py gives it the same
access as other Python code under your account. Review scripts before running them;
use a disposable environment without credentials for unfamiliar projects.

VST plugins are native executable code. The worker process separates plugin crashes
from the parent process; it is not an OS security sandbox and inherits account
permissions and environment. Only load trusted plugins and presets. The current
worker has no render/inspection deadline, so a hung plugin may require terminating
the process. Do not expose Prism as an untrusted upload/render service.

Never provide secrets to fork PR workflows or run them on a personal workstation
runner. Review workflow and dependency changes before approving execution. The
Surge 1.3.4 CI installers are verified against reviewed SHA-256 pins before execution.
Pins detect changed bytes; they do not certify that upstream code is safe. See the
[maintainer checklist](docs/development/maintainer-checklist.md) for updating them.
Lockfiles and passing tests are not vulnerability audits.
