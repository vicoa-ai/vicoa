# Security Policy

We take the security of Vicoa seriously, the daemon runs on users' own machines
and handles their agent credentials and code, so responsible disclosure matters.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Instead, use one of these private channels:

- **Email:** **hi@vicoa.ai**
- **GitHub:** the repository's **Security → Report a vulnerability** (private
  vulnerability reporting), if enabled.

Please include:

- a description of the vulnerability and its impact;
- the affected component and version (CLI/daemon, desktop, web, mobile, plugin);
- step-by-step reproduction, and a proof-of-concept if you have one;
- any suggested remediation.

## What to expect

- We aim to **acknowledge** your report within a few business days.
- We'll keep you updated on our assessment and remediation timeline.
- We'll credit you when a fix ships, unless you prefer to remain anonymous.

Please give us a reasonable opportunity to remediate before any public
disclosure. We do not currently run a paid bug-bounty program.

## Scope

This policy covers everything in this repository: the CLI, daemon, self-hostable
backend, web dashboard, and desktop and mobile clients.

## Supported versions

Security fixes target the **latest released version** of each component. Please
upgrade before reporting, in case the issue is already fixed.
