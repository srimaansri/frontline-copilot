# MCP server

Exposes the copilot's four tools over the Model Context Protocol, so another assistant can use them. They are the same functions the copilot's own agent calls, from `src/copilot/tools.py`.

| Tool | What it does |
|---|---|
| `search_kb` | Searches the help articles and returns passages with their title and URL |
| `get_plan_details` | Reads the plan catalogue: price, data, hotspot and international features |
| `summarize_call` | Summarizes one redacted support call from its transcript id |
| `escalate_to_human` | Opens a hand-off to a human specialist and returns what to tell the customer |

Free text that arrives over MCP is redacted before it is used, because it reaches a search index and, for a hand-off, a table. None of the tools can see or change a customer account. All data is synthetic.

## Run it

Install with the `mcp` extra:

```bash
pip install -e ".[mcp,models]"
```

Over stdio, which is what Claude Code and Claude Desktop use:

```bash
python -m mcp_server.server
```

Over streamable HTTP:

```bash
python -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8000
```

The server reads the same configuration as the rest of the project: `config/settings.yaml`, a local `.env`, and environment variables. It signs in to Databricks the way the Databricks SDK does, so a CLI profile works on a laptop.

## Register it with Claude Code

From the repository root, with the virtual environment's Python:

```bash
claude mcp add frontline-copilot -- python -m mcp_server.server
```

## Register it with Claude Desktop

Add this to the `mcpServers` section of Claude Desktop's configuration file, with the path to this repository's Python and folder:

```json
{
  "mcpServers": {
    "frontline-copilot": {
      "command": "/path/to/repo/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/repo"
    }
  }
}
```

## Docker

`mcp_server/Dockerfile` runs the server over streamable HTTP as a non-root user. Credentials come from the environment only.

```bash
docker build -f mcp_server/Dockerfile -t frontline-mcp .
```

```bash
docker run --rm -p 8000:8000 --env-file .env.mcp frontline-mcp
```

`.env.mcp` is a file you create (git ignores it), holding `DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET` and `SQL_WAREHOUSE_ID` for a service principal.

The image was built and a container started on 2026-11-14: it reported healthy, ran as a non-root user, and answered an MCP `initialize` request over HTTP. The tools were not called inside the container, because that needs a service principal's credentials.

## Status

- Unit tests call each tool in process (`tests/test_mcp_server.py`).
- On 2026-11-14 an MCP client started the server over stdio and called it against the live workspace: the tool list, a plan lookup, an article search and a rejected transcript id all came back correctly.
- It has not yet been registered with Claude Code or Claude Desktop.

One thing worth knowing if you write your own stdio server on Databricks: the SDK signs in by running the Databricks CLI, and that child process inherits standard input, which over stdio is the MCP channel. The first tool call that needed to sign in hung until the server gave the transport its own copy of standard input.
