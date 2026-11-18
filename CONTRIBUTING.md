# Contributing

Bug reports, fixes and new tools are welcome. Open an issue first for
anything larger than a small fix, so the approach can be agreed before you
write it.

## Set up

```bash
git clone https://github.com/rvartanov/slurp-garmin-mcp
cd slurp-garmin-mcp
uv sync
uv run pytest          # unit and integration tests, Garmin is mocked
```

## Tests

```bash
uv run pytest                                   # everything except e2e
uv run pytest tests/unit/test_http_url_secret.py -v
uv run pytest tests/integration/ -v
```

- `tests/unit/`: server behaviour (startup, auth, transport, filtering).
- `tests/integration/`: every tool through FastMCP, with mocked Garmin
  responses from `tests/fixtures/`.
- `tests/e2e/`: against a real Garmin account. Only runs with
  `uv run pytest tests/e2e/ -m e2e`; some of these create and delete foods,
  food logs and workouts in the account. Never needed for a pull request.

Every change comes with tests. A new tool needs at least an integration test
with a fixture, and a test for the error path.

## Adding or changing a tool

1. Check whether [python-garminconnect](https://github.com/cyberjunky/python-garminconnect)
   has a method for it. If so, use it.
2. If not, call the endpoint through the generic client and return a clear
   error when Garmin answers with something unexpected. Garmin does not
   document these endpoints: record the method, path, payload and a sample
   response in the pull request, and add a fixture.
3. Register the tool in its module's `register_tools`, with a docstring whose
   first line says what it does.
4. Classify it in `src/garmin_mcp/tool_annotations.py` (read, additive or
   destructive) and add it to the fitting profiles in
   `src/garmin_mcp/tool_profiles.py`.
5. Regenerate the tool lists:

   ```bash
   uv run python scripts/generate_tools_doc.py    # docs/tools.md
   uv run python scripts/generate_dxt_tools.py    # dxt/manifest.json
   ```

   CI fails when either is out of date.

[CLAUDE.md](CLAUDE.md) describes the module layout and conventions in more
detail.

## Pull requests

- One subject per pull request, small enough to review.
- Describe what changed and why, and how you tested it.
- Update `docs/` and add a line to `CHANGELOG.md` under "Unreleased" when
  behaviour changes.
- No secrets, tokens or personal data, also not in fixtures: replace names,
  ids, coordinates and device serial numbers with made-up values.

## Upstream

This project is a fork of
[Taxuspt/garmin_mcp](https://github.com/Taxuspt/garmin_mcp). The module path
`garmin_mcp` is kept so upstream changes can be merged:

```bash
git remote add upstream https://github.com/Taxuspt/garmin_mcp
git fetch upstream
git merge upstream/main
```

Fixes that are not specific to this fork are best contributed upstream as
well.

## License

By contributing you agree that your contribution is licensed under the
[MIT License](LICENSE).
