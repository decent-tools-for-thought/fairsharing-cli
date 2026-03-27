<div align="center">

# fairsharing-cli

[![Release](https://img.shields.io/github/v/release/decent-tools-for-thought/fairsharing-cli?sort=semver&color=0f766e)](https://github.com/decent-tools-for-thought/fairsharing-cli/releases)
![Python](https://img.shields.io/badge/python-3.11%2B-0ea5e9)
![License](https://img.shields.io/badge/license-MIT-14b8a6)

Command-line wrapper for the FAIRsharing REST API, with record browsing, search, auth-aware operations, exports, and batch workflows.

</div>

> [!IMPORTANT]
> This codebase is entirely AI-generated. It is useful to me, I hope it might be useful to others, and issues and contributions are welcome.

## Map
- [Install](#install)
- [Functionality](#functionality)
- [Configuration](#configuration)
- [Quick Start](#quick-start)
- [Credits](#credits)

## Install
$$\color{#0EA5E9}Install \space \color{#14B8A6}Tool$$

```bash
python -m pip install .
fairsharing --help
```

For local development:

```bash
python -m pip install -e ".[dev]"
pytest
```

## Functionality
$$\color{#0EA5E9}Record \space \color{#14B8A6}Browse$$
- `fairsharing fairsharing-records` and `fairsharing fairsharing-record`: list and fetch FAIRsharing records.
- `fairsharing subjects|domains|taxonomies|licences|organisations|standards|policies|databases|collections`: browse named API families.
- `fairsharing routes`: inspect published API routes.

$$\color{#0EA5E9}Search \space \color{#14B8A6}Workflows$$
- `fairsharing search ...`: run family-specific search commands.
- `fairsharing records resolve`: resolve FAIRsharing IDs, DOIs, and legacy identifiers.
- `fairsharing records search-expand`: search and expand matching records to fuller payloads.
- `fairsharing list-all`: unified list entrypoint across families.

$$\color{#0EA5E9}Auth \space \color{#14B8A6}Operations$$
- `fairsharing auth login|whoami|logout`: manage JWT-backed sessions.
- `fairsharing users` and `fairsharing user-admin`: access user and admin endpoints.
- `fairsharing config show|set|clear`: manage saved API defaults.

$$\color{#0EA5E9}Export \space \color{#14B8A6}Batch$$
- `fairsharing export search|records`: export searches and record sets to structured files.
- `fairsharing maintain request`: submit maintenance shortcuts.
- `fairsharing batch --file ops.jsonl`: run batched API operations from JSONL.
- `fairsharing docs routes|endpoint` and `fairsharing api-call`: inspect or call the API directly.

## Configuration
$$\color{#0EA5E9}Save \space \color{#14B8A6}Defaults$$

FAIRsharing uses JWT bearer authentication for most protected endpoints.

Credential precedence:

1. CLI flags: `--token`, `--email`, `--password`
2. Environment: `FAIRSHARING_TOKEN`, `FAIRSHARING_EMAIL`, `FAIRSHARING_PASSWORD`
3. Config file: `$XDG_CONFIG_HOME/fairsharing-cli/config.json` or `~/.config/fairsharing-cli/config.json`

Base URL precedence:

1. CLI `--base-url`
2. Environment `FAIRSHARING_BASE_URL`
3. Config file value
4. Built-in default `https://api.fairsharing.org`

Manage config:

```bash
fairsharing config show
fairsharing config set --token <jwt>
fairsharing config set --base-url https://api.fairsharing.org
fairsharing config clear --token
```

## Quick Start
$$\color{#0EA5E9}Try \space \color{#14B8A6}Lookup$$

```bash
fairsharing routes
fairsharing auth login --login user@example.org --password '***' --save-token
fairsharing fairsharing-records list --page-number 1 --page-size 20
fairsharing standards get --id FAIRsharing.v0z5x1
fairsharing search organisations --q "EMBL"
fairsharing records resolve 10.25504/FAIRsharing.abc123
fairsharing export search --family organisations --q EMBL --format jsonl --out orgs.jsonl
fairsharing batch --file ops.jsonl
```

## Credits

This client is built for the FAIRsharing API and is not affiliated with FAIRsharing.

Credit goes to FAIRsharing for the registry content, API, and documentation this tool depends on.
