# CLI — synapse

Install the package (system-wide or in a virtualenv):

```bash
# editable install (recommended for development)
python -m pip install -e .

# or install normally
python -m pip install .
```

Run the interactive setup (optional) before first start to configure keys and settings:

```bash
python setup.py
```

Environment variables (optional):

- `SYNAPSE_DATA_DIR` — path to data dir (default: `~/.synapse/data`).
- `SYNAPSE_BACKEND_PORT` — backend port (default: `8000`).
- `SYNAPSE_FRONTEND_PORT` — frontend port (default: `3000`).

Basic commands:

```bash
# start in foreground (opens browser)
synapse start

# start in background (writes pidfiles)
synapse start --detach

# start but don't open browser
synapse start --no-browser

# start on custom ports
synapse start --backend-port 8080 --frontend-port 4000

# start with performance profiling enabled
synapse start --profile

# stop processes (reads pidfiles)
synapse stop

# show status
synapse status

# restart
synapse restart

# restart detached on custom ports
synapse restart --detach --backend-port 8080 --frontend-port 4000

# run interactive setup wizard (configure API keys and settings)
synapse setup
```

### `start` flags

| Flag | Default | Description |
|------|---------|-------------|
| `--detach`, `-d` | off | Run in background and write pidfiles |
| `--no-browser` | off | Do not open a browser on start |
| `--backend-port PORT` | `8000` | Port for the backend API server |
| `--frontend-port PORT` | `3000` | Port for the frontend web UI |
| `--profile` | off | Enable performance profiling (`SYNAPSE_PROFILING=true`) |

### `restart` flags

Same as `start` except `--no-browser` and `--profile` are not available.

PID files are written to the data directory, e.g.:

- `~/.synapse/data/backend.pid`
- `~/.synapse/data/frontend.pid`

## Profiling

The `profile` subcommand queries and controls backend performance profiling. Requires the backend to be running with `--profile`.

```bash
# show per-endpoint latency table (avg, p50, p95, p99, max)
synapse profile stats

# clear collected timing stats
synapse profile reset

# start CPU profiling
synapse profile cpu-start

# print CPU profile report (text or HTML)
synapse profile cpu-report
synapse profile cpu-report --output report.html

# start memory profiling
synapse profile memory-start

# snapshot current memory allocations (top 20 by default)
synapse profile memory-snapshot
synapse profile memory-snapshot --limit 50

# record a py-spy flame graph (requires: pip install py-spy)
synapse profile spy
synapse profile spy --output profile.svg --duration 60
```

### `profile` flags

| Flag | Default | Description |
|------|---------|-------------|
| `--output FILE`, `-o` | — | Output file (`cpu-report`: `.html`, `spy`: `.svg`) |
| `--limit N` | `20` | Top allocations to show (`memory-snapshot`) |
| `--duration SECS` | `30` | Recording duration in seconds (`spy`) |

## Example quick flow

```bash
# install and run in background
python -m pip install -e .
synapse start --detach
synapse status
# when finished
synapse stop
```

If you prefer running without installing, use:

```bash
python -m synapse start
```

This CLI is extensible — future commands (migrations, backup, logs) can be added to `synapse.cli`.
