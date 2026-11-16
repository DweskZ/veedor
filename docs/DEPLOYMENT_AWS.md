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
| Server settings template | `deploy/server.env.template` (placeholders only) |
| Scripts | `deploy/scripts/` (`build-release.sh` on your machine; `server-install.sh`, `server-update.sh`, `server-backup.sh` on the server) |
| Infrastructure | `infra/terraform/` |
| Manual GitHub deploy | `.github/workflows/deploy.yml` (code and images only) |

## Why this size and region

Measured on the dev machine (running containers): api about 370-440 MB, web about 95-130 MB, db about
170-185 MB, observability about 770 MB. The local proof of this kit (below) used 778 MiB for the four
production containers, so **t4g.small (2 GiB)** fits without the observability stack with room for
Docker and the page cache; add the observability profile and you need **t4g.medium (4 GiB)**.

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
   It refuses to continue if any file from `data/raw` or `data/texts` (or a byte-identical copy) is staged.
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
   `chmod 600`, edit: set `POSTGRES_PASSWORD` (`openssl rand -base64 24 | tr -d '/+='`), `SITE_ADDRESS`
   and `PUBLIC_ORIGIN` (same value as `--site-url`). The installer refuses to run while `CHANGE_ME` remains.
8. **Install.** `/srv/veedor/release/<stamp>/deploy/scripts/server-install.sh /srv/veedor/release/<stamp>`.
   It verifies checksums, loads images, unpacks data, restores the database (the HNSW index is rebuilt:
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

`POST /processes/{ocid}/ask` is a 404 unless `VEEDOR_ASK_ENABLED=true`. Without a provider, model and key it
answers by retrieval only and costs nothing. To use a model, build the release with `--with-ask-model` (adds
the local embedding cache; the code comments say the model is about 0.5 GB, the whole `data/models` folder here is 1.3 GB, and I did not measure the
RAM the route adds, so test on t4g.medium first) and set `VEEDOR_LLM_PROVIDER`, `VEEDOR_LLM_MODEL`,
`VEEDOR_LLM_API_KEY` in `/etc/veedor/server.env`, then `docker compose ... up -d api`. The cost is the provider's
bill, which I did not look up. The code limits it to `VEEDOR_ASK_DAILY_BUDGET` model calls per day (default 300,
split across workers), 160 output tokens per answer and 4 requests per minute per IP per worker; set the budget
to 0 to stay on retrieval. Set a spending limit at the provider as well.

## Operations

- **Update code/images:** run the GitHub workflow, or build a release and `server-update.sh <release dir>`.
  Data refresh: `server-update.sh --with-data <release dir>` (also clears the dossier cache).
- **Backup:** `server-backup.sh` runs daily (systemd timer) and keeps 14 dumps in `/srv/veedor/backups`; only the
  reviews table is state, and reviews are disabled in this stack. Everything else is rebuilt from a release.
  Keep your last release folder on your machine.
- **Logs:** `docker compose -p veedor --env-file /etc/veedor/server.env -f /srv/veedor/deploy/compose.prod.yml logs -f --tail=100 api`.
  Containers rotate logs at 10 MB x 3. Caddy's access log drops query strings and masks client IPs to /24.
- **Health:** `/api/v1/health`; `docker compose ... ps`.
- **Observability:** add `--profile observability` (needs t4g.medium), set `GRAFANA_ADMIN_PASSWORD` and
  `VEEDOR_OTEL_ENDPOINT=http://observability:4318`. Grafana listens on the server's loopback only:
  `aws ssm start-session --target <id> --document-name AWS-StartPortForwardingSession --parameters portNumber=3001,localPortNumber=3001`.
- **GitHub deploy (optional):** set `github_repository` and `github_branch` in `terraform.tfvars`, apply, then
  add repository variables `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `AWS_INSTANCE_ID`, `RELEASE_BUCKET`, `SITE_URL`
  and run "deploy" manually. The role may only upload `releases/gh-*` and run Run Command on this instance. The workflow
  uses the arm64 runner label `ubuntu-24.04-arm`; I did not verify that your plan provides it (fallback in the file's comment).
  It deploys **code and images only**: the data is not in the repository.
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

- [ ] Nothing from `data/raw` or `data/texts` left your machine. `build-release.sh` checks paths, an allow-list of 12 Parquet tables and file hashes, then re-lists the archive. Re-check: `tar -tzf data.tar.gz | grep -E 'raw/|texts/|process_texts|person_name_tokens'` prints nothing.
- [ ] The release is still not "public data": it holds unmasked personal fields (see next section). Keep the S3 bucket private; never open `data/` through Caddy.
- [ ] `/etc/veedor/server.env` has a generated password, mode 600, never committed. No secret is in any repository file.
- [ ] Budget e-mail subscription confirmed; a test alert is not possible, so check the budget page shows your e-mail.
- [ ] HTTPS works on the real domain (not the bare-IP mode); `PUBLIC_ORIGIN` matches the address in the browser.
- [ ] Reviews off, `/docs` returns 404, API and database not reachable from the internet (`nmap` or a connection to ports 8000 and 5432 from outside fails).
- [ ] Indexing decision: the repository has no robots.txt or sitemap in `web/src` (searched); decide whether search engines may index a page that ranks real public bodies by risk, and add the file in the web app if not.
- [ ] The honest-limits wording (indicators, not accusations; masking is heuristic: `docs/SECURITY.md`, `docs/DEPLOYMENT.md` checklist) is visible on the site, and data licences were checked (SERCOP CC BY 3.0 EC attribution; SRI and Supercias licence unstated).
- [ ] No rate limiting beyond the API's in-memory limits: Caddy cannot rate limit without a third-party plugin (custom build). Reads are unlimited.

## What the release ships (privacy findings)

Parquet files in the release (row counts and columns read from the files, not from docs): lake `processes`, `tenderers`, `awards`,
`suppliers_sri`, `ghost_companies`, `companies_supercias`, `company_financials`; marts `process_scores`, `process_signals`,
`supplier_profiles`, `process_quotes`, `process_quote_stats`. Not shipped: `person_name_tokens` (a vocabulary of
name tokens; the API works without it and applies its other screens), `process_texts`, `raw/`, `build_summary.json`, dossiers, traces.

Flags: these shipped tables still hold **unmasked** personal fields, because masking happens at the API boundary
(`docs/SECURITY.md`, "Not covered yet"): `awards` and `tenderers` carry `supplier_name` and `supplier_ruc` of natural persons; `processes.description`
is free text that may contain names; `process_scores` has `winner_name`; `supplier_profiles` has `name`; `process_quotes.text`
is third-party text screened at build time. This is required for the API to run, so it ships, but the files
must stay private (S3 bucket private, 14-day expiry, data folder mounted read-only and not served). Recommendation: keep `person_name_tokens`
out (done); do not publish the tarball anywhere. Note `data/investigations` JSON files ship too (26 files, checked at write time by the store for personal RUCs).

## After the credits end

The kit is portable: `deploy/` needs only Docker with Compose v2 on an arm64 or amd64 Linux host with 2 GB RAM or more
(build the images for that architecture: `build-release.sh --platform linux/amd64`). On a VPS, skip Terraform, install Docker, copy a release over SSH or
download, create `/etc/veedor/server.env`, run `server-install.sh`. Staying on AWS costs about $18.3 / month for t4g.small at list price (table above). I did not
verify any VPS provider's current price, so none is quoted: compare a 2 GB / 2 vCPU plan with 30+ GB disk and an included IPv4 address on the providers' own pricing pages, dated the day you decide.
A free-plan account closes at 6 months; to keep running on AWS you must upgrade to Paid before the 90-day retention ends [11].

## Local proof of this kit (2026-11-16)

Run as a separate compose project `veedor-prod` on Colima (4 CPU, 5.8 GiB; the dev stack kept running), from a release built by
`build-release.sh` and installed by `server-install.sh` with local paths: pages `/`, `/procesos`, `/metodologia`, a process page returned 200;
`/api/v1/health`, process detail, `/similar` (3 neighbours from the restored dump) returned 200 through Caddy; `/docs` 404;
production containers used 778 MiB (api 436, db 184, web 128, caddy 30); repository `scripts/smoke_test.py` passed 35/35 against the proxy;
`down` then `up --wait` took 23 s to healthy; the first install restored the dump in a few minutes on this machine. Not tested locally: TLS
issuance, the Terraform apply, Session Manager, S3, the GitHub workflow, a real 2 GiB instance, the ask route, the observability profile.

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
