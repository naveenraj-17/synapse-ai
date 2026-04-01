# CLI — synapse-ai

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
synapse-ai start

# start in background (writes pidfiles)
synapse-ai start --detach

# start but don't open browser
synapse-ai start --no-browser

# stop processes (reads pidfiles)
synapse-ai stop

# show status
synapse-ai status

# restart
synapse-ai restart
```

PID files are written to the data directory, e.g.:

- `~/.synapse/data/backend.pid`
- `~/.synapse/data/frontend.pid`

Example quick flow:

```bash
# install and run in background
python -m pip install -e .
synapse-ai start --detach
synapse-ai status
# when finished
synapse-ai stop
```

If you prefer running without installing, use:

```bash
python -m synapse start
```

This CLI is extensible — future commands (migrations, backup, logs) can be added to `synapse.cli`.
