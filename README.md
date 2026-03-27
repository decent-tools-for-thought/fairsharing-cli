# fairsharing-cli

`fairsharing-cli` is a production-focused Python command-line wrapper for the full FAIRsharing REST API surface.

## Install

From this repository:

```bash
python -m pip install .
```

or for development:

```bash
python -m pip install -e ".[dev]"
```

## API Coverage

This CLI wraps all endpoints currently listed in the FAIRsharing OpenAPI document at `https://api.fairsharing.org/openapi.json`:

- `GET /routes`
- `GET/POST/GET/PUT/DELETE` for `fairsharing_records`
- `GET` for `fairsharing_record/{doi}` and `fairsharing_record/{legacy_id}`
- `GET` families: `subjects`, `domains`, `taxonomies`, `licences`, `organisations`, `standards`, `policies`, `databases`, `collections`
- `GET/POST/GET/PUT/DELETE` families: `user_defined_tags`, `organisation_links`, `grants`
- Search endpoints under `/search/*` (all 10)
- User/session flows under `/users/*`
- Admin flows under `/user_admin` and `/user_admin/{id}`
- `POST /maintenance_requests`

## Authentication and Config

FAIRsharing API uses JWT bearer authentication for most endpoints.

Credential/token resolution precedence (highest first):

1. CLI flags (`--token`, `--email`, `--password`)
2. Environment (`FAIRSHARING_TOKEN`, `FAIRSHARING_EMAIL`, `FAIRSHARING_PASSWORD`)
3. Config file (`$XDG_CONFIG_HOME/fairsharing-cli/config.json` or `~/.config/fairsharing-cli/config.json`)

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

```bash
# show top-level help
fairsharing --help

# inspect API routes
fairsharing routes

# login and save token
fairsharing auth login --login user@example.org --password '***' --save-token

# list records with pagination
fairsharing fairsharing-records list --page-number 1 --page-size 20

# lookup standard by id
fairsharing standards get --id FAIRsharing.v0z5x1

# search organisations
fairsharing search organisations --q "EMBL"

# resolve unknown identifier
fairsharing records resolve 10.25504/FAIRsharing.abc123

# export search hits to jsonl
fairsharing export search --family organisations --q EMBL --format jsonl --out orgs.jsonl
```

## Output Modes

- `--output json` (default): full fidelity JSON
- `--output text`: concise, readable summaries
- `--output jsonl`: JSON lines for list-like responses

Additional controls:

- `--select key1,key2`: select top-level fields from object/list items
- `--raw`: print raw response payload without normalization

## Command Surface

Top-level groups:

- `routes`
- `fairsharing-records`
- `fairsharing-record`
- `subjects`
- `domains`
- `taxonomies`
- `user-defined-tags`
- `organisation-links`
- `grants`
- `licences`
- `organisations`
- `standards`
- `policies`
- `databases`
- `collections`
- `search`
- `users`
- `user-admin`
- `maintenance-requests`
- `config`
- `docs`
- `api-call`
- `auth`
- `records`
- `list-all`
- `export`
- `maintain`
- `batch`

Each group supports complete endpoint-level operations for its API family.

## Higher-Order Commands

These commands provide ergonomic workflows on top of endpoint wrappers:

```bash
# identity/auth workflows
fairsharing auth login --login user@example.org --password '***' --save-token
fairsharing auth whoami
fairsharing auth logout --revoke --clear-token

# resolve by DOI/legacy/id
fairsharing records resolve FAIRsharing.v0z5x1 --typed-family standards

# search and expand fairsharing records to full payloads
fairsharing records search-expand --q "metabolomics" --limit 20 --concurrency 4

# unified list entrypoint
fairsharing list-all --family standards --type minimal_reporting_guideline

# export workflows
fairsharing export search --family organisations --q EMBL --out organisations.jsonl --format jsonl
fairsharing export records --ids 1,2,3 --out records.json --format json

# maintenance shortcut
fairsharing maintain request --record 123 --status approved

# OpenAPI introspection
fairsharing docs routes
fairsharing docs endpoint --method GET --path /fairsharing_records

# batch operation execution
fairsharing batch --file ops.jsonl
```

Batch input format (`ops.jsonl`):

```json
{"method":"GET","path":"/routes"}
{"method":"POST","path":"/search/organisations/","params":{"q":"EMBL"}}
{"method":"GET","path":"/fairsharing_records/1"}
```

## Verification

```bash
python -m pip install -e .
pytest
python -m fairsharing_cli --help
fairsharing routes --output text
```

## Caveats

- API docs page (`https://fairsharing.org/API_doc`) is JavaScript-rendered; this CLI uses the machine-readable OpenAPI at `https://api.fairsharing.org/openapi.json`.
- Some upstream endpoints are thin wrappers around Devise-like auth pages and may return minimal payloads.

## Attribution

This tool wraps the FAIRsharing API. FAIRsharing content and API are provided by FAIRsharing and subject to their terms:

- Terms: `https://fairsharing.org/terms`
- API docs: `https://fairsharing.org/API_doc`
