# Deploying Veedor on AWS (one small server)

Written for the owner. Generic notes on hosting are in `docs/DEPLOYMENT.md`; this file is the concrete
AWS recipe. Prices and rules below were read from AWS's own pages on **2026-11-16** (sources in
"Sources"). They change: re-check before relying on them.

## What you get

One small ARM (Graviton) EC2 server running Docker Compose: Caddy (HTTPS, only public port), web, api,
PostgreSQL. Nothing but ports 80/443 is open; there is no SSH and no key pair, you reach the server
through AWS Systems Manager Session Manager. Everything is created by Terraform in `infra/terraform/`
and removed by one `terraform destroy`. Only that Terraform is AWS specific; `deploy/` runs on any
Linux VPS with Docker.

| Piece | File |
|---|---|
| Production compose | `deploy/compose.prod.yml` (self-contained, mirrors `docker-compose.yml`; the header lists settings to keep in sync) |
| Reverse proxy | `deploy/Caddyfile` |
| Optional Grafana stack | `deploy/compose.observability.yml` (separate file so its required password cannot break the main stack) |
| Release column allow-list | `deploy/release-columns.json`, checked by `deploy/scripts/check_release_schema.py` |
| Server settings template | `deploy/server.env.template` (placeholders only) |
| Scripts | `deploy/scripts/` (`build-release.sh` on your machine; `server-install.sh`, `server-update.sh`, `server-backup.sh` on the server) |
| Infrastructure | `infra/terraform/` |
| Manual GitHub deploy | `.github/workflows/deploy.yml` (code and images only) |

## Why this size and region

Measured on the dev machine (running containers): api about 370-440 MB, web about 95-130 MB, db about
170-185 MB, observability about 770 MB. The latest local proof of this kit (below) used about 616 MiB for the four
production containers with **one API worker** (the default; the earlier proof's 778 MiB was with two), so **t4g.small (2 GiB)** fits without the observability
stack with room for Docker and the page cache; add the observability stack and you need **t4g.medium (4 GiB)**.
Two API workers were OOM-killed under the 768 MiB container limit in the proof (details in the proof section), so the default is one; use two only with
`API_MEM_LIMIT=1280m` or more.

Region: default `us-east-1`, the lowest list price I found of the two I compared. `sa-east-1` (Sao Paulo)
is the nearest AWS region to Ecuador but its instance price is about 60 % higher (table below). I did
not measure latency from Ecuador to either, so the closeness benefit is not quantified; for a read-only
dashboard of mostly cached pages, price is the safer default. Change `region` in `terraform.tfvars` if you
prefer lower latency.

## Costs (verified 2026-11-16, Linux on-demand, USD)

| Item | us-east-1 | sa-east-1 | Source |
|---|---|---|---|
| t4g.small (2 vCPU, 2 GiB) | $0.0168 / h | $0.0268 / h | [1] |
| t4g.medium (2 vCPU, 4 GiB) | $0.0336 / h | $0.0536 / h | [1] |
| gp3 volume | $0.08 / GB-month | not checked | [2] |
| Public IPv4 address (in use or idle) | $0.005 / h | not checked | [3] |
| Data transfer out to the internet | first 100 GB / month free, then $0.09 / GB (first 10 TB) | not checked | [4][5] |
| Route 53 hosted zone (only if you use it) | $0.50 / month per zone | | [6] |
| S3 standard storage (release bucket) | $0.023 / GB-month | | [7] |
| Session Manager, Run Command on EC2 | no additional charge | | [8] |
| AWS Budgets (cost budget, no actions) | the price file lists $0.00 for budget-days | | [9] |

Monthly estimate in us-east-1, 730 h, 30 GB gp3, one public IPv4, traffic inside the free allowance,
release bucket emptied after use:

| | Instance | Volume | IPv4 | Total / month | $100 credit lasts | $200 credit lasts |
|---|---|---|---|---|---|---|
| t4g.small, no observability | $12.26 | $2.40 | $3.65 | **about $18.3** | about 5.5 months | about 10.9 months |
| t4g.medium, with observability | $24.53 | $2.40 | $3.65 | **about $30.6** | about 3.3 months | about 6.5 months |

Caveats: the free plan ends after 6 months or when credits run out, whichever comes first, so even the
$200 case stops at 6 months [10][11]. The sa-east-1 total is not computed because its volume and IPv4 prices
were not checked. The domain name is extra and not priced here. A search summary of an AWS page mentioned
a t4g.small free trial of 750 hours per month until 2026-12-31; I did not read that on the AWS page itself,
so it is not counted. Credits may not cover every charge type; read the console's credit page.

### Is EC2 usable on the free plan?

Partly confirmed. The EC2 User Guide says that for accounts created on or after 2025-07-15 the instance
types marked "Free tier eligible" are `t3.micro, t3.small, t4g.micro, t4g.small, c7i-flex.large,
m7i-flex.large`, and that the Free Tier lasts 6 months or until credits are used up [12]. So **t4g.small is
on that list; t4g.medium is not**. The billing guide says the free plan "provides access to select AWS services
and features" and points to https://aws.amazon.com/free/ for the eligible list, which I could not read as a
complete list [11]. Therefore: t4g.small is the free-plan-compatible choice; t4g.medium or other non-listed
services may require upgrading to the Paid plan (credits are still applied there, and charges beyond credits
are billed) [11]. Whether S3, Budgets, Route 53 and IAM resources of this stack are all allowed on the free
plan I could not confirm: check the console's service list, and run `terraform apply` early so any block shows up before you
depend on it. The command `aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true` lists
eligible types in your account [12].

When the plan ends the account closes, you lose access to resources and data, and AWS keeps the content for
90 days before deleting the account unless you upgrade to Paid within that time [11]. Keep a copy of your
release folder on your own machine.

## Prerequisites

On your machine: Docker (Colima is fine) with buildx, `jq`, the AWS CLI v2, the AWS Session Manager plugin,
and OpenTofu or Terraform (`brew install opentofu awscli`). The local data (`data/lake`, `data/marts`,
`data/investigations`) and the local PostgreSQL container with the vectors built (`veedor vectors build`).

You must do yourself (nobody else can): create the AWS account with a payment card, create credentials for
your own use (IAM Identity Center or an IAM user with administrator rights for the first run, then `aws configure sso`),
confirm the budget e-mail subscription, buy a domain if you want one, create the server env file, and push the repository to GitHub if you want the workflow.

## First deployment, step by step

1. **Account.** Create the account, pick the plan, add a card. In Billing, check the credit balance.
2. **Variables.** `cd infra/terraform && cp terraform.tfvars.example terraform.tfvars` and set at least
   `budget_alert_email`. Keep `instance_type = "t4g.small"` unless you will run observability.
3. **Create the infrastructure.** `tofu init && tofu plan` (read it), then `tofu apply`. Note the outputs
   `public_ip`, `instance_id`, `session_manager_command`, `release_bucket`. Open the e-mail AWS sends and
   confirm it if it asks. Wait about 3 minutes; first-boot log: `/var/log/veedor-init.log` on the server.
4. **Build the release (your machine).** The site URL is baked into the web image, so decide it now:
   `http://<public_ip>` without a domain, `https://your.domain` with one.
   ```
   deploy/scripts/build-release.sh --site-url http://<public_ip>
   ```
   It builds the data bundle with `scripts/build_data_bundle.sh`, dumps the vector table, builds both images
   for linux/arm64 and writes `SHA256SUMS` and `manifest.json`. Images are built here and shipped as tarballs
   because building the API (scipy, pyarrow, scikit-learn) and Next.js needs several GB of RAM, which a 2 GiB
   instance does not have; your Apple silicon machine is arm64 like Graviton, so the build is native.
   It refuses to continue if any file from `data/raw` or `data/texts` (or a byte-identical copy) is staged, or if
   any Parquet file has a table or column that is not on the reviewed allow-list (see the checklist below).
   The quotes tables are **not** included unless you pass `--with-quotes` (see the checklist before you do).
   Measured release (this data): data 209 MB, database dump 271 MB, images 309 + 100 MB, base images 182 MB.
5. **Upload.** `aws s3 sync dist/release-<stamp> s3://<release_bucket>/releases/<stamp>/` (about 1.1 GB;
   uploads are free, storage is cents for two weeks: the bucket deletes objects after 14 days). The bucket is private, encrypted,
   blocks public access, and the server reads it through its instance role. No presigned URLs are needed.
6. **Open a shell.** Run the `session_manager_command` output. Then on the server:
   ```
   sudo -i
   aws s3 sync s3://<release_bucket>/releases/<stamp>/ /srv/veedor/release/<stamp>/ --region <region>
   ```
7. **Server settings.** `cp /srv/veedor/release/<stamp>/deploy/server.env.template /etc/veedor/server.env`,
   `chown root:root` and `chmod 600` (the installer enforces both), edit: set `POSTGRES_PASSWORD` (`openssl rand -base64 24 | tr -d '/+='`), `SITE_ADDRESS`
   and `PUBLIC_ORIGIN` (same value as `--site-url`). The installer refuses to run while `CHANGE_ME` remains.
8. **Install.** `/srv/veedor/release/<stamp>/deploy/scripts/server-install.sh /srv/veedor/release/<stamp>`.
   It verifies checksums, creates the `veedor` system user/group (uid/gid 10001, the same numbers the API image runs as),
   sets the file modes (see "What the server holds"), loads images, unpacks data, restores the database (the HNSW index is rebuilt:
   it took a few minutes on a 4-core laptop; expect longer on 2 vCPUs), starts the stack, waits for health,
   enables a daily reviews backup, prints the URL.
9. **Check.** Open the URL. `curl -s http://127.0.0.1/api/v1/health` on the server.

### Moving files without SSH

Session Manager carries a shell, not file copies, so releases travel through the private S3 bucket above.
Cost: storage $0.023 / GB-month [7], so a 1.1 GB release kept 14 days is a few cents; transfer from S3 to an
EC2 instance in the same region is not charged as internet traffic (not re-verified here; check the S3 pricing page).

## Using a domain

A domain costs money (registration is yearly; I did not verify a price). Buy it anywhere, create an A record
to the `public_ip` (or set `domain_name` and `route53_zone_id` for an existing Route 53 zone; a hosted zone is $0.50 / month [6]).
Then `SITE_ADDRESS=your.domain`, `PUBLIC_ORIGIN=https://your.domain`, build the release with
`--site-url https://your.domain` and update. Caddy obtains and renews the certificate itself; ports 80 and 443 must stay open.

**No domain (temporary):** `SITE_ADDRESS=:80` serves plain HTTP on the IP. The default certificate
authorities do not issue certificates for a bare IP address, so there is no HTTPS and traffic is unencrypted. Use it only
to test, then add a domain before publishing.

## Question answering (optional, off by default)

**Do not enable quotes or the ask route in production until the privacy gate and the disclosure are in place** (checklist below).
The ask route reads the stored quotes.

`POST /processes/{ocid}/ask` is a 404 unless `VEEDOR_ASK_ENABLED=true`. Without a provider, model and key it
answers by retrieval only and costs nothing. To use a model, build the release with `--with-ask-model` (adds
the local embedding cache; the code comments say the model is about 0.5 GB, the whole `data/models` folder here is 1.3 GB, and I did not measure the
RAM the route adds, so test on t4g.medium first) and set `VEEDOR_LLM_PROVIDER`, `VEEDOR_LLM_MODEL`,
`VEEDOR_LLM_API_KEY` in `/etc/veedor/server.env`, then `docker compose ... up -d api`. The cost is the provider's
bill, which I did not look up. The code limits it to `VEEDOR_ASK_DAILY_BUDGET` model calls per day (default 300,
split across workers), 160 output tokens per answer and 4 requests per minute per IP per worker; set the budget
to 0 to stay on retrieval. Set a spending limit at the provider as well.

## Operations

- **Update code/images:** run the GitHub workflow, or build a release, upload it, sync it to `/srv/veedor/release/<name>/` and run
  `server-update.sh /srv/veedor/release/<name>`. Data refresh: `server-update.sh --with-data <release dir>` (also clears the dossier cache).
  `server-update.sh` accepts only a folder directly under `/srv/veedor/release/` or `--release-id gh-<run>-<attempt>`; anything else is an error.
- **Backup:** `server-backup.sh` runs daily (systemd timer) and keeps 14 dumps in `/srv/veedor/backups`; only the
  reviews table is state, and reviews are disabled in this stack. Everything else is rebuilt from a release.
  Keep your last release folder on your machine.
- **Logs:** `docker compose -p veedor --env-file /etc/veedor/server.env -f /srv/veedor/deploy/compose.prod.yml logs -f --tail=100 api`.
  Containers rotate logs at 10 MB x 3. Caddy's access log drops query strings and masks client IPs to /24.
- **Health:** `/api/v1/health`; `docker compose ... ps`.
- **Observability:** needs t4g.medium. Set `GRAFANA_ADMIN_PASSWORD` (the stack refuses to start with an empty one) and
  `VEEDOR_OTEL_ENDPOINT=http://observability:4318` in `/etc/veedor/server.env`, then run the compose command with
  `-f compose.prod.yml -f compose.observability.yml` (the scripts do it when `VEEDOR_OBSERVABILITY=1`). Grafana is published on the server's
  loopback only (`127.0.0.1:3001`), never through Caddy. Open it with a Session Manager port forward, then browse to http://localhost:3001 and log in as `admin`:
  `aws ssm start-session --target <instance id> --document-name AWS-StartPortForwardingSession --parameters portNumber=3001,localPortNumber=3001`.
- **GitHub deploy (optional):** set `github_repository` (and, if you want another name, `github_environment`, default `production`) in
  `terraform.tfvars`, apply, then in GitHub create the **environment** `production` (Settings > Environments): add yourself as a *required reviewer*
  (every deploy waits for your approval) and restrict *deployment branches* to `main`. Define these environment variables:
  `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `AWS_INSTANCE_ID`, `RELEASE_BUCKET`, `SSM_DOCUMENT_NAME` (Terraform output `ssm_deploy_document`) and `SITE_URL`,
  then run "deploy" manually.
  What the AWS role can do: (a) assume it only from a job of this repository that declares that environment (trust policy: `aud` = `sts.amazonaws.com`,
  `sub` = `repo:<owner>/<repo>:environment:<name>`); (b) upload `releases/gh-*` to the release bucket; (c) call `ssm:SendCommand` **only** on the custom document
  `veedor-deploy-release` and on this one instance; (d) read command results (`ssm:GetCommandInvocation`, `ssm:ListCommandInvocations`; AWS offers no resource-level
  restriction for those two, so the resource is `*`; they only read command output, so in an account that runs other Run Command jobs the role could read their output).
  It has no right to `AWS-RunShellScript`. The document takes one parameter, `releaseId`, which must match `^gh-[0-9]{1,20}-[0-9]{1,3}$` (SSM validates
  it when the command is sent and again in the agent), reaches the shell as an environment variable (`interpolationType: ENV_VAR`), and runs only
  `server-update.sh --release-id`, which validates it a third time. Residual trust: the people who may approve and run the workflow choose the code and images
  that get deployed; that is what a deploy is. The workflow uses the arm64 runner label `ubuntu-24.04-arm`; I did not verify that your plan provides it
  (fallback in the file's comment). It deploys **code and images only**: the data is not in the repository. Pinning third-party actions to commit SHAs is not done
  (I could not verify SHAs offline); do it when you fork the workflow.
- **Keeping settings in sync:** `deploy/compose.prod.yml` copies service settings from `docker-compose.yml` (list in its header, read 2026-11-16).
  When the dev file changes an environment variable, mount or image tag, repeat it there. `VEEDOR_ASK_*` and `VEEDOR_LLM_*` exist only in `src/veedor/core/settings.py`.

## Teardown (and confirming nothing keeps billing)

1. Copy anything you want to keep (`/srv/veedor/backups`, your release folder).
2. `cd infra/terraform && tofu destroy`. It removes the instance, root volume, Elastic IP, security group, IAM roles,
   budget, the release bucket (with contents) and the DNS record.
3. Confirm in the console (per region you used): EC2 > Instances (none running), Volumes (none), Elastic IPs (none,
   an unattached address is still charged $0.005 / h [3]), Snapshots (none; Terraform creates none), S3 (bucket gone), Budgets.
   Then Billing > Bills for the current month, and check again the next day because charges lag.
4. Resources you created by hand (state bucket, Route 53 zone, registered domain) are not removed by destroy.
5. Closing the account is a separate step in Account settings.

## Pre-publication checklist

- [ ] Nothing from `data/raw` or `data/texts` left your machine. `build-release.sh` checks paths, an allow-list of Parquet tables (10 by default, 13 with `--with-quotes`) and file hashes, then **independently checks the schema of every Parquet file** against `deploy/release-columns.json` (below), then re-lists the archive. Re-check: `tar -tzf data.tar.gz | grep -E 'raw/|texts/|process_texts|person_name_tokens'` prints nothing.
- [ ] **Quotes: do not enable quotes or the ask route in production until the privacy gate and the disclosure are in place.** A release built without `--with-quotes` contains no `process_quotes` / `process_quote_stats` (check: `tar -tzf data.tar.gz | grep quote` prints nothing) and the server runs with `VEEDOR_QUOTES_ENABLED=false` (the default in `compose.prod.yml`; leave it commented out in `server.env`). Quotes are text written by third parties and the review found named persons in them. `--with-quotes` is passed through to `scripts/build_data_bundle.sh` (which runs `scripts/check_quotes_privacy.py` over the source marts and refuses to build on failure), and `build-release.sh` runs that content gate again over the exact staged files; it is refused if the script is missing or fails. The schema gate additionally refuses the quotes tables until their columns are on `deploy/release-columns.json`: `quote_lexicon` is not there yet because that table did not exist when the list was written, so add its columns after reviewing them. Check with `curl -s -o /dev/null -w '%{http_code}' https://<site>/api/v1/processes/<ocid>/quotes`: it must print 404.
- [ ] The release is still not "public data": it holds unmasked personal fields (see next section). Keep the S3 bucket private; never open `data/` through Caddy.
- [ ] `/etc/veedor/server.env` has a generated password, owner root, mode 600, never committed. No secret is in any repository file.
- [ ] Budget e-mail subscription confirmed; a test alert is not possible, so check the budget page shows your e-mail.
- [ ] HTTPS works on the real domain (not the bare-IP mode); `PUBLIC_ORIGIN` matches the address in the browser.
- [ ] Reviews off, `/docs` returns 404, and the API and database ports are not reachable from the internet (`nmap` or a connection to ports 8000 and 5432 from outside fails). The API itself is public by design through Caddy at `/api/*`: anonymous read routes only, masked at the response models. This is the scope of the "no user authentication" limit in `docs/SECURITY.md`: no write route is exposed, so nothing here needs an identity. What remains is that masking of names in free text is heuristic and reads are not rate limited.
- [ ] Indexing decision: the repository has no robots.txt or sitemap in `web/src` (searched); decide whether search engines may index a page that ranks real public bodies by risk, and add the file in the web app if not.
- [ ] The honest-limits wording (indicators, not accusations; masking is heuristic: `docs/SECURITY.md`, `docs/DEPLOYMENT.md` checklist) is visible on the site, and data licences were checked (SERCOP CC BY 3.0 EC attribution; SRI and Supercias licence unstated).
- [ ] No rate limiting beyond the API's in-memory limits: Caddy cannot rate limit without a third-party plugin (custom build). Anonymous reads are limited per client address by the API (`VEEDOR_READ_RATE_PER_MINUTE`, default 240, and `VEEDOR_READ_SEARCH_RATE_PER_MINUTE`, default 60 for `q` searches), in memory and per worker, with the `web` container exempt by its pinned address `10.77.88.20` (page requests to `web` itself are not limited). The limits that exist are per client address and per worker, and reset on restart; see "Client address and forwarded headers".
- [ ] GitHub deploy only: the `production` environment has required reviewers and a `main`-only branch rule.

## What the release ships (privacy findings)

Parquet files in the release (row counts and columns read from the files, not from docs): lake `processes`, `tenderers`, `awards`,
`suppliers_sri`, `ghost_companies`, `companies_supercias`, `company_financials`; marts `process_scores`, `process_signals`,
`supplier_profiles`; with `--with-quotes` also `process_quotes`, `process_quote_stats` (off by default). Not shipped: `person_name_tokens` (a vocabulary of
name tokens; the API works without it and applies its other screens), `process_texts`, `raw/`, `build_summary.json`, dossiers, traces.

Flags: these shipped tables still hold **unmasked** personal fields, because masking happens at the API boundary
(`docs/SECURITY.md`, "Not covered yet"): `awards` and `tenderers` carry `supplier_name` and `supplier_ruc` of natural persons; `processes.description`
is free text that may contain names; `process_scores` has `winner_name`; `supplier_profiles` has `name`; `process_quotes.text`
(only with `--with-quotes`) is third-party text screened at build time. This is required for the API to run, so it ships, but the files
must stay private (S3 bucket private, 14-day expiry, data folder mounted read-only and not served). Recommendation: keep `person_name_tokens`
out (done); do not publish the tarball anywhere. Note `data/investigations` JSON files ship too (26 files, checked at write time by the store for personal RUCs).

### Column allow-list (what stops a new unmasked column)

The first gate looks at file names and hashes; it cannot see inside a Parquet file. `deploy/scripts/check_release_schema.py` reads only the
footers (schemas) of every Parquet file in the staged release and refuses the build if a table, or any column of a table, is not listed in
`deploy/release-columns.json`. Source of the list: the column names read from the Parquet files of the local data on 2026-11-16 and
reviewed by hand against `docs/SECURITY.md`; the file also lists, per table, the columns already known to hold unmasked personal data
(`unmasked_personal`). It is a committed file: when the pipeline adds a column, the build fails until a person decides whether the column is
personal data and adds it to the file in a reviewed change. Limits: it checks names, not what a column contains (a personal value inside an
allow-listed column such as `description` is not detected; that is what the masking and, for quotes, the content gate are for).

## What the server holds

Be clear about this before publishing: **the Parquet files the API reads contain unmasked personal fields**: names and RUCs of natural-person
suppliers (`awards`, `tenderers`, `process_scores`, `supplier_profiles`) and free-text descriptions (`processes.description`) that may contain names.
Masking happens when the API responds (`docs/SECURITY.md`), not in the files. Therefore the server, its volume snapshots and any backup or copy of the
release are **personal-data stores** and must be treated as such, even though the website shows masked values only.

Controls in place (all in this kit):

- No SSH, no key pair; access only through Session Manager (IAM-controlled, logged by AWS).
- Only ports 80/443 are open (security group). `db`, `api` and `web` have no published ports; Grafana, if enabled, is on the loopback only.
- Root volume encrypted (`encrypted = true`, gp3). What that does: protects the data if the physical disk or a snapshot/volume copy is accessed outside
  your account or without access to the KMS key. What it does not: it is transparent to everything running on the instance, so it gives no
  protection against someone with a shell on the server, a compromised container, a flaw in the API that reads files, or an IAM identity allowed to use the
  instance. I did not set a customer-managed KMS key (AWS-managed default key); a snapshot shared with another account would need the key policy checked.
- Dedicated system user/group `veedor` (uid/gid 10001 = the user the API image runs as). Data tree `/srv/veedor/data`: owner `root`, group `veedor`,
  directories 750, files 640: readable by the API container and by root only. `/srv/veedor` is 750 root; `release/`, `backups/` and the
  previous data copy are 700 root; `/etc/veedor/server.env` is root:root 600. The API mounts the data read-only, drops all capabilities and runs
  with a read-only root filesystem.
- No static serving of the data directory: see the verification below.
- Release bucket private, encrypted, public access blocked, objects expire after 14 days.

How "no path serves those files" was verified (by reading, then by test): `deploy/Caddyfile` has no `file_server`, `root`, `browse` or `respond`-from-disk
directive; its only handlers are `reverse_proxy api:8000` for `/api/*` and `reverse_proxy web:3000` for everything else, plus a loopback health
responder. Caddy's container mounts only the Caddyfile and its own `caddy_data`/`caddy_config` volumes, so it cannot read `/srv/veedor` at all.
In `deploy/compose.prod.yml` the data directory is mounted only into the `api` container, read-only, and the API image has no route that serves files (it executes
queries over them, and answers with masked JSON). The web image has no mount of it. In the local proof, `/data/...`, `/lake/processes.parquet`,
`/api/v1/../data` and `/api/v1/lake/processes.parquet` through the proxy returned 404 (results below). This does not prove the API
has no path-traversal bug; it shows no configured route serves the folder.

Residual risk, honestly: (1) a vulnerability in the API, web app or an image dependency that gives file read or code execution exposes the unmasked
files (mitigated by the read-only filesystem, dropped capabilities, no egress filtering, but egress is open); (2) the masking is heuristic
(`docs/SECURITY.md`), so some personal data may be shown even through the normal API; (3) anyone you grant Session Manager or S3 release access
can read the data; (4) copies on your own machine and in `dist/` are unprotected by this kit; (5) free-text descriptions can contain names the files hold
verbatim; (6) a snapshot or AMI taken by someone with EC2 rights contains everything. Keep the account's IAM tight, do not share snapshots,
and delete the release bucket contents and local copies when no longer needed.

## Client address and forwarded headers

The API limits some routes per client and takes the client address from `request.client.host` (`src/veedor/api/security.py`, `v1/ask.py`). uvicorn
(0.54.0 in the image) rewrites that address from `X-Forwarded-For` only when the TCP peer is listed in `FORWARDED_ALLOW_IPS` (`--proxy-headers` is on by
default); with `*` it trusted every peer and took the left-most, client-controlled, value, so a forged header chose the address (the review confirmed it).
Production compose therefore does two things: (1) Caddy (image `caddy:2.11-alpine`, v2.11.9 when this was written) has `trusted_proxies static` with **no
ranges** (`deploy/Caddyfile`). Per the Caddy documentation the default is that no proxy is trusted, and `reverse_proxy` ignores the values of
incoming `X-Forwarded-For/-Proto/-Host` from untrusted clients and sets them itself (https://caddyserver.com/docs/caddyfile/directives/reverse_proxy#defaults,
https://caddyserver.com/docs/caddyfile/options#trusted-proxies); the Caddyfile writes this out explicitly. Nothing sits in front of Caddy, so no range
must be added: add a CDN's ranges only if you ever put one in front. (2) The internal network has a pinned subnet `10.77.88.0/24` and Caddy a fixed
address `10.77.88.10`; the API has `FORWARDED_ALLOW_IPS=10.77.88.10`, so only Caddy may set the client address. The web container (Next.js
server-side calls) is not trusted: requests it makes count as web's own address. Limits stay per worker and per client address; behind a NAT many
visitors share one address.

## After the credits end

The kit is portable: `deploy/` needs only Docker with Compose v2 on an arm64 or amd64 Linux host with 2 GB RAM or more
(build the images for that architecture: `build-release.sh --platform linux/amd64`). On a VPS, skip Terraform, install Docker, copy a release over SSH or
download, create `/etc/veedor/server.env`, run `server-install.sh`. Staying on AWS costs about $18.3 / month for t4g.small at list price (table above). I did not
verify any VPS provider's current price, so none is quoted: compare a 2 GB / 2 vCPU plan with 30+ GB disk and an included IPv4 address on the providers' own pricing pages, dated the day you decide.
A free-plan account closes at 6 months; to keep running on AWS you must upgrade to Paid before the 90-day retention ends [11].

## Local proof of this kit (2026-11-16, re-run after the fifth review)

Run as a separate compose project `veedor-prod` on 127.0.0.1:8088 (the dev stack stayed up and answered 200 on :8000 and :3000 before and after).
To get real Linux file ownership the scripts ran **as root inside the Colima VM** (`server-install.sh`, `server-update.sh` unchanged, with
`VEEDOR_HOME` and the other overrides of `lib.sh` pointing at a throw-away folder). The release was built by `build-release.sh --skip-images` from the local data
and the images already built on the machine (`veedor-api:release` for most checks, a fresh `veedor-api:proofq` built from the current source tree for the quotes check).
Everything was removed afterwards with `down -v`, the throw-away folders, the VM user and the extra image.

- Pages `/`, `/procesos`, `/metodologia`, `/api/v1/health`, a process detail and `/similar` returned 200 through Caddy; `/docs` 404.
- File modes (the env file was created mode 666 on purpose; the installer fixed it). Host: `/srv/veedor`-equivalent root:root 750; `data/`, `data/lake`
  root:veedor 750; `data/lake/processes.parquet` root:veedor 640; `release/` and `backups/` root:root 700; env file root:root 600; no data file with any "other"
  permission bit and no data directory other than 750 (two `find` counts, both 0). Inside the api container: `uid=10001(veedor) gid=10001(veedor)`;
  `/app/data/lake` `root:veedor 750`, `processes.parquet` `root:veedor 640`; the file was readable by the API user and **not** readable by a container started as
  uid 12345 (`Permission denied`). Host user `veedor` is uid/gid 10001 = the image's user.
- Not served: `/data/` (308 to `/data`, then 404 from the web app), `/lake/processes.parquet`, `/api/v1/../data/lake/processes.parquet`,
  `/api/v1/lake/processes.parquet` all 404.
- Forged `X-Forwarded-For` (the route `GET /processes/{ocid}/dossier` is limited to 30 per minute per client and worker; one worker): 45 requests through Caddy, each with a
  different forged address: 30 x 200 then 15 x 429, i.e. the API counted them all as one client (the real peer). Control with the old setting
  (`FORWARDED_ALLOW_IPS=*`, extra container, forged header sent directly): 45 x 200, i.e. the spoof worked. Direct requests with a forged header to the production
  api container (peer not Caddy): 30 x 200, 15 x 429, header ignored. Caveat: on this laptop the peer Caddy saw was the Docker bridge gateway (`10.77.88.x` in
  its log), not a real client address, because of Docker Desktop/Colima port forwarding; on the AWS host the real client address is the peer. Caddy
  config check: `caddy adapt` shows `trusted_proxies: {"source":"static"}` (no ranges) on both servers.
- Quotes: with the source tree containing the backend change (`VEEDOR_QUOTES_ENABLED`), image built from it, default configuration:
  `GET /api/v1/processes/<ocid>/quotes` returned **404** (body `not_found`), `POST .../ask` 404, and `VEEDOR_QUOTES_ENABLED=false` inside the container. With the older
  image the same route returned 503 (tables missing), which is why the first run was repeated. The release had no `quote`, `person_name_tokens`, `texts/` or `raw/` entry.
- `server-update.sh` argument checks (all refused with exit 1): an injected id `gh-1-1; id`, `../../etc`, `--with-data` together with `--release-id`, a folder outside the release
  folder (`/etc`, `release/../backups`, a symlink to `/etc`), no argument, an unknown option, an invalid bucket name. A valid `--with-data` update completed and kept the modes
  (data 750/640, `data.previous` root 700, release folder root 700).
- Memory (api, db, web, caddy), one worker, after the checks: 362 + 160 + 81 + 13 = about 616 MiB (earlier steady readings in the same run: api 340-600 MiB, db up to 360 after the restore).
  **Finding:** with two API workers at the 768 MiB limit the api container was OOM-killed twice (`OOMKilled=true`, `Child process died`, 502 from Caddy
  while it restarted); two workers start together at 525-560 MiB. One worker peaked at 485 MiB without a kill, so one worker is the default now (`compose.prod.yml`).
- Schema gate: refused a test Parquet with an extra column (`national_id`), and refused `--with-quotes` while the content gate was missing (then that script appeared and the
  gate is wired to it; the build with `--with-quotes` itself was **not** run end to end because `data/marts/quote_lexicon.parquet` does not exist yet).
- Not tested locally: TLS issuance, the Terraform apply, the SSM document (SSM validation of `allowedPattern`, `ENV_VAR` interpolation on the real agent), Session Manager, S3,
  the GitHub workflow and environment approval, a real 2 GiB instance, the ask route, the observability stack (the compose merge and the required-password check were validated with `compose config` only),
  encryption of the volume.

## Sources (all read 2026-11-16)

1. EC2 on-demand price data, AWS price list API (the data behind https://aws.amazon.com/ec2/pricing/on-demand/): https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/ec2/USD/current/ec2-ondemand-without-sec-sel/
2. gp3 price, AWS price list (publication 2026-11-14): https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/current/us-east-1/index.json ; performance included: https://aws.amazon.com/ebs/pricing/
3. Public IPv4: https://aws.amazon.com/vpc/pricing/ and https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/current/index.json
4. 100 GB free out: https://aws.amazon.com/ec2/pricing/on-demand/
5. $0.09/GB: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSDataTransfer/current/index.json
6. Route 53: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRoute53/current/index.json
7. S3: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonS3/current/us-east-1/index.json
8. Systems Manager pricing: https://aws.amazon.com/systems-manager/pricing/
9. Budgets: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AWSBudgets/current/index.json
10. Free Tier and FAQ: https://aws.amazon.com/free/ , https://aws.amazon.com/free/free-tier-faqs/
11. Choosing a plan: https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html
12. EC2 Free Tier eligible types: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html
13. AL2023 AMI parameter `al2023-ami-kernel-default-arm64`: https://docs.aws.amazon.com/linux/al2023/ug/ec2.html ; SSM Agent preinstalled on AL2023: https://docs.aws.amazon.com/systems-manager/latest/userguide/ami-preinstalled-agent.html (read through a search summary only)
