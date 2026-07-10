# CLI reference

`sepg` is a single command with five subcommands: `download`, `pipeline`, `shard`, `load`, `ddl`.

Run `sepg --help` or `sepg <command> --help` for the full flag list at any time.

Invocation:

- Local venv (after `./bootstrap/setup-host-venv.sh`): `sepg <command> ...`
- Inside a Docker container (package isn't pip-installed there, only `PYTHONPATH=/sepg/src`):
  `python -m sepg.cli <command> ...`

Both forms run the exact same code (`src/sepg/cli.py`).

Scripts read `SEPG_ROOT` to resolve `data/`, `db/schema/`, `db/ddl/` etc. relative to the project
root; it's set to `/sepg` inside Docker.

---

## `sepg pipeline`

Run the full pipeline: shard XML to CSV, then load into Postgres.

```
sepg pipeline
  --site SITE              StackExchange site name (matches data/xml/<site>/)
  --all                    Process all tables defined in db/schema/
  --tables badges,posts    Process specific tables (comma-separated)
  --host HOST              Postgres host (default: localhost)
  --port PORT              Postgres port (default: 5432)
  --user USER              Postgres user (default: se)
  --password PASS          Postgres password (default: sepass)
  --database DB            Target database (default: se)
  --schema SCHEMA          Postgres schema (default: public)
  --shards N               Number of output shards (default: 8)
  --shard-workers N        Parallel XML shard workers (default: 1)
  --max-rows-per-part N    Rows per CSV part file (default: 5_000_000)
  --load-workers N         Parallel COPY workers (default: cpu_count)
  --truncate-first         Truncate table before loading
  --force-shard            Force re-shard even if manifest exists
  --rm-staging             Delete staging directory after successful load
```

Example:

```sh
docker compose --env-file docker/.env -f docker/compose.yml --profile db --profile loader run --rm loader \
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

### Tuning `--shard-workers` and `--load-workers`

These two parallelism knobs have different bottlenecks:

- **`--shard-workers`** is I/O bound. Multiple workers read byte ranges of the same XML file
  concurrently and write to CSV shards. Adding workers past what your storage can feed causes
  contention without throughput gains. Default is 1, increase only if profiling shows the disk
  is underutilised.

- **`--load-workers`** is CPU/network bound. Each worker runs an independent `COPY` stream into
  Postgres from a separate CSV part file. Parallelism here is limited by Postgres write throughput
  and available cores. Defaults to `cpu_count`, tune down if Postgres becomes the bottleneck.

---

## `sepg shard`

Shard an XML file into CSV parts.

```
sepg shard
  --xml PATH               Path to <Table>.xml
  --site SITE              Used to default --out-dir to data/staging/<site>/<table>/
  --schema-dir DIR         Schema directory (default: db/schema/<table>/)
  --out-dir DIR            Output directory (requires --site if omitted)
  --shards N               Number of shards (default: 8)
  --shard-workers N        Parallel workers (default: 1)
  --max-rows-per-part N    Rows per part (default: 5_000_000)
```

Example:

```sh
docker compose --env-file docker/.env -f docker/compose.yml --profile db --profile loader run --rm loader \
  python -m sepg.cli shard \
    --xml data/xml/vi/Comments.xml \
    --site vi \
    --shards 8 \
    --shard-workers 8 \
    --max-rows-per-part 5000000
```

---

## `sepg load`

Load CSV parts listed in a manifest into Postgres.

```
sepg load
  --manifest PATH          Path to manifest.json (data/staging/<site>/<table>/manifest.json)
  --ddl PATH               Path to DDL SQL file (optional; db/ddl/postgres/create_<table>.sql)
  --host HOST              Postgres host (default: localhost)
  --port PORT              Postgres port (default: 5432)
  --user USER              Postgres user (default: se)
  --password PASS          Postgres password (default: sepass)
  --database DB            Target database (default: se)
  --schema SCHEMA          Postgres schema (default: public)
  --truncate-first         Truncate table before loading
  --load-workers N         Parallel COPY workers (default: 1)
  --delimiter CHAR         CSV delimiter (default: ,)
  --rm-staging             Delete staging directory after successful load
```

Example:

```sh
docker compose --env-file docker/.env -f docker/compose.yml --profile db --profile loader run --rm loader \
  python -m sepg.cli load \
    --manifest data/staging/vi/comments/manifest.json \
    --ddl db/ddl/postgres/create_comments.sql \
    --host db \
    --port 5432 \
    --user se \
    --password sepass \
    --database vi \
    --schema public \
    --load-workers 4 \
    --truncate-first
```

---

## `sepg ddl`

Generate a `CREATE TABLE` SQL file from a `schema.yml`.

```
sepg ddl
  --table TABLE            Table name (e.g. posts), auto-resolves schema and output paths
  --schema-dir DIR         Schema directory (if not using --table)
  --out-sql PATH           Output SQL path (if not using --table)
```

Example:

```sh
docker compose --env-file docker/.env -f docker/compose.yml --profile db --profile loader run --rm loader \
  python -m sepg.cli ddl \
    --table posts
```

---

## `sepg download`

Download a torrent via Transmission and optionally extract 7z archives.

```
sepg download
  --torrent URL|PATH       Torrent URL or local .torrent file
  --out-dir DIR            Download destination (must be absolute)
  --filter PATTERN         File filter: substring match or re:<regex>
  --list-files             List matching files and exit (no download)
  --extract                Extract .7z archives after download
  --extract-dir DIR        Extraction destination (default: --out-dir)
  --rm-archives            Delete .7z files after extraction
  --keep-torrent           Keep torrent in Transmission after finish
  --verify-hashes          Hash-check downloaded files against the torrent's own piece list
  --rpc-url URL            Transmission RPC URL (default: http://transmission:9091/transmission/rpc)
  --wait-seconds N         Download timeout in seconds (default: 604800)
  --poll SECS              Progress poll interval (default: 1.0)
  --force-torrent          Re-download .torrent file even if cached
```

### `--verify-hashes`

Opt-in post-download integrity check: re-hashes each wanted file's on-disk bytes against the SHA1
piece hashes recorded in the `.torrent` file itself, scoped to just the files downloaded.

Examples:

```sh
COMPOSE="docker compose --env-file docker/.env -f docker/compose.yml"
TORRENT="https://archive.org/download/stackexchange/stackexchange_archive.torrent"

# List all files
$COMPOSE --profile downloader run --rm downloader \
  python -m sepg.cli download \
    --torrent "$TORRENT" \
    --list-files

# Download, extract and remove archive for a single site
$COMPOSE --profile downloader run --rm downloader \
  python -m sepg.cli download \
    --torrent "$TORRENT" \
    --out-dir "/downloads/vi" \
    --filter "stackexchange/vi.stackexchange.com.7z" \
    --extract \
    --rm-archives

# Download all stackoverflow per-table archives
$COMPOSE --profile downloader run --rm downloader \
  python -m sepg.cli download \
    --torrent "$TORRENT" \
    --out-dir "/downloads/stackoverflow.com" \
    --filter 're:(^|/)stackoverflow\.com-[^/]+\.7z$' \
    --extract \
    --rm-archives
```
