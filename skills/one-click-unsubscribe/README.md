# One-click Unsubscribe

Standalone Python CLI and API for validating and sending RFC 8058 one-click unsubscribe requests.

## CLI

Install the project with `uv tool install --force --editable .`, then provide exactly one endpoint
URL on stdin or in a file:

```bash
one-click-unsubscribe --url-file endpoint.txt
cat endpoint.txt | one-click-unsubscribe
```

The default is a dry run: it validates the HTTPS endpoint and reports `{"status": "dry_run"}`
without sending a request. Add `--execute` to POST the RFC 8058 request. Output is JSON and never
includes the endpoint URL; failures use a generic, redacted error. Input is limited to 16 KiB.

```bash
one-click-unsubscribe --execute --url-file endpoint.txt
```

## Python API

```python
from one_click_unsubscribe import post_one_click

endpoint_url = get_endpoint_url()
post_one_click(endpoint_url)
```

The transport validates public HTTPS destinations, pins DNS resolution for each request, and
revalidates redirects. Callers are responsible for authorization, recipient eligibility, and
unsubscribe history; this library does not determine whether an unsubscribe should be performed.
