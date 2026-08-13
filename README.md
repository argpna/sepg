# sepg

Stackexchange data importer for PostgreSQL. Downloads
[StackExchange data dumps](https://archive.org/details/stackexchange) from archive.org and
bulk-loads them into PostgreSQL.

---

## Requires

- Docker
- Python 3.11+ (only for local development)

---

## Docker stack

Available services

| Profile | Services |
|---|---|
| **db** | db |
| **loader** | loader |
| **downloader** | transmission, downloader |
| **tools** | pgadmin |

### Configuration

Copy `docker/.env.example` to `docker/.env` and edit ports, credentials, image versions etc. to
match your environment:

```sh
cp docker/.env.example docker/.env
```

---

## Quickstart

### Download a site archive

> [!NOTE]
> The torrent URL below points to the 2024 data dump. Other releases can be browsed at
> [archive.org](https://archive.org/search?query=creator%3A%22Stack%20Exchange%22), pick the
> appropriate torrent and substitute the URL.

> [!CAUTION]
> Archives, extracted XML, and staging CSV files can consume significant disk space. Browse the
> torrent contents first (or list them via cli with `--list-files`) and pick only the sites
> and tables you need, smaller sites are a good starting point
> for a local setup. You can also reclaim space as you go: `download --rm-archives` deletes `.7z`
> files after extraction, and `pipeline --rm-staging` / `pipeline --rm-source-xml` delete staging
> CSVs / source XML once a table has loaded successfully.

> [!NOTE]
> On Windows, Docker Desktop's WSL2 backend bind-mounts this repo through a slow Windows<->Linux
> filesystem bridge if the checkout lives on a Windows drive (`C:\...` or `/mnt/c/...`) - shard/load
> steps can be ~20x slower (tests done on a vagrant box). Check out the git repo inside a WSL2 distro's
> own filesystem (e.g. `~/projects/sepg`), and prefer running a **native Docker Engine** inside that
> distro over **Docker Desktop**. (i.e follow the Docker engine Linux install docs -
> See [install](https://docs.docker.com/engine/install/) and [post-install](https://docs.docker.com/engine/install/linux-postinstall/) instructions for more information

List files matching a filter:

```sh
COMPOSE="docker compose --env-file docker/.env -f docker/compose.yml"
TORRENT="https://archive.org/download/stackexchange/stackexchange_archive.torrent"
FILTER="stackexchange/vi.stackexchange.com.7z"

$COMPOSE --profile downloader run --rm downloader \
  python -m sepg.cli download \
    --torrent "$TORRENT" \
    --filter "$FILTER" \
    --list-files
```
> [!NOTE]
> `--out-dir` is a path inside the downloader container. It is mounted from
> the host `/downloads` -> `data/xml/`, so `--out-dir /downloads/vi` writes to
> `data/xml/vi/` on the host.

Download, extract and remove the 7z:

```sh
$COMPOSE --profile downloader run --rm downloader \
  python -m sepg.cli download \
    --torrent "$TORRENT" \
    --out-dir "/downloads/vi" \
    --filter "$FILTER" \
    --extract \
    --rm-archives
```

XML files are placed in `data/xml/vi/`.

> [!NOTE]
> Sites with per-table archives (e.g. `stackoverflow.com`) ship one 7z per table rather than
> a single site archive.
>
> ```sh
> OUT_DIR="/downloads/stackoverflow.com"
> FILTER="re:(^|/)stackoverflow\.com-[^/]+\.7z$"
> ```
> Pass `--out-dir "$OUT_DIR" --filter "$FILTER"` in the same way as the single-archive example above.


### Run the postgres pipeline

```sh
$COMPOSE --profile db --profile loader run --rm loader \
  python -m sepg.cli pipeline \
    --site vi \
    --host db \
    --port 5432 \
    --user se \
    --password sepass \
    --database vi \
    --schema public \
    --all \
    --shards 4 \
    --shard-workers 1 \
    --load-workers 4 \
    --truncate-first
```

This will:
1. Create the `vi` database (cloned from `se_template`) if it doesn't exist
2. Emit DDL and create tables
3. Shard each XML table into CSV parts under `data/staging/vi/<table>/`
4. COPY all parts into Postgres

### Tear down and delete volumes

```sh
docker compose \
  --env-file docker/.env \
  -f docker/compose.yml \
  --profile db \
  --profile loader \
  --profile tools \
  --profile downloader \
  down -v
```

---

## Schema format

Each table has a `db/schema/<table>/schema.yml`, for e.g.

```yaml
table: Posts
primary_key: Id
columns:
  Id: integer
  PostTypeId: integer
  CreationDate: timestamp
  Score: integer
  Body: text
  Title: varchar(512)
  Tags: varchar(1024)
```

XML attribute names (CamelCase) are automatically converted to snake_case Postgres
column names by `_pg_ident()`:

| XML attribute | Postgres column |
|---|---|
| `Id` | `id` |
| `PostTypeId` | `post_type_id` |
| `CreationDate` | `creation_date` |
| `OwnerDisplayName` | `owner_display_name` |

and so on.

### Available tables

| Table name | Description |
|---|---|
| `badges` | Tracks badges awarded to users |
| `comments` | Stores comments on posts |
| `post_history` | Maintains edit and revision history of posts |
| `post_links` | Stores relationships between related posts |
| `posts` | Stores all questions and answers |
| `tags` | Defines tags used to categorize questions |
| `users` | Contains user profile and reputation data |
| `votes` | Records all voting activity on posts |

---

## Sharding design

The XML sharding stage splits large XML files across multiple workers and routes rows to N
output shards:

- XML file is split into byte ranges (one per shard worker), aligned to newlines
- Each worker routes rows to N shard files by `Id % N`
- Part files named `shard-{shard_id:02d}-{part_id:06d}.csv`
- `part_id` uses `worker_id * stride + local_part_id` to avoid collisions across workers
- After all workers finish, `manifest.json` is written listing all parts with row counts
  and byte sizes
- Re-sharding uses an atomic temp-dir swap, shards written to `<table>.tmp-<uuid>/`, then
  renamed over the final dir on success (or cleaned up on failure)

The pipeline skips re-sharding if a valid manifest exists with the same shard count and
source XML path. Use `--force-shard` to override.

XML files are searched in `data/xml/<site>/<Table>.xml`

---

## Postgres setup

### Template database

At initdb, a `se_template` database is created with extensions pre-installed:

- `pg_stat_statements`
- `pg_buffercache`

Each new site database is created via `CREATE DATABASE <site> TEMPLATE se_template`, inheriting
these extensions automatically.

### Default credentials

| Setting | Value |
|---|---|
| Host | `localhost` (or `db` inside Docker network) |
| Port | `5432` |
| User | `se` |
| Password | `sepass` |
| Maintenance DB | `postgres` |

pgAdmin: `http://localhost:8081` (email: `admin@example.com`, password: `adminpass`)

---

## CLI reference

All commands are subcommands of a single unified CLI: `sepg <command> ...` or, inside the Docker
containers where the package isn't pip-installed, `python -m sepg.cli <command> ...`. See [`docs/cli.md`](docs/cli.md) for the full reference.

---

## Development

Set up a local virtualenv with dev dependencies (ruff, pytest):

```sh
./bootstrap/setup-host-venv.sh
source .venv/bin/activate
```

(If you use [direnv](https://direnv.net/), `.envrc` activates `.venv` automatically on `cd`.)

This installs the package in editable mode, so the `sepg` command is available directly on your
`PATH` (e.g. `sepg pipeline --site vi --all ...`) without going through Docker.

### Connecting to Dockerized services

Running `sepg` on the host still relies on the `db` and/or `transmission` containers, so bring
those up first (e.g. `$COMPOSE --profile db --profile downloader up -d db transmission`). Since
the host is outside the compose network, container hostnames like `db` and `transmission` won't
resolve - use the ports published to `localhost` instead (from `docker/.env`):

```sh
sepg pipeline --site vi --host localhost --port "$PG_PORT" ...

sepg download --torrent "$TORRENT" --rpc-url "http://localhost:${TRANSMISSION_PORT}/transmission/rpc" ...
```

> [!NOTE]
> `--out-dir` for `download` is still resolved by the Transmission daemon inside its own
> container, so keep using container paths like `/downloads/vi` even when invoking `sepg`
> from the host.

Omitting `--rpc-url` (or leaving `--host`/`--port` at their defaults) targets the in-container
hostnames and will hang trying to resolve them from the host.

Lint, format-check and test:

```sh
ruff check .
ruff format --check .
pytest
```

## License

MIT - see [LICENSE](LICENSE).
