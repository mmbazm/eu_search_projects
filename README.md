# 🇪🇺 EU Project Search

Search the European Commission's [SEDIA Funding & Tenders](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/home) project database, explore participant organisations on a map, see who collaborates with whom, and compare EU funding across countries — all from a self-contained, two-container app.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![Docker Compose](https://img.shields.io/badge/docker-compose-2496ED.svg)](https://docs.docker.com/compose/)

This is an open source project — issues, forks, and pull requests are welcome. See [Contributing](#contributing) below.

## Features

- 🗺️ **Participant map** — every participant's city plotted on an interactive map, with hover tooltips.
- 🧭 **Filters** — by participant country, by participant organisation, and by project start/end year (range sliders).
- 💶 **EU contribution by country** — a bar chart summing each participant's EU funding, grouped by country, across the current results.
- 🔗 **Collaboration network** — a graph of which participant organisations have worked together, with edge thickness showing how many projects they share.
- 🔗 **Website links** — direct links to each participant's website and to the project's own page.

## Screenshot

Screenshot of the running app `docs/eu_screenshot_1.png`

## Architecture

```
┌─────────────┐      HTTP        ┌─────────────┐      HTTPS       ┌───────────────────┐
│  frontend   │ ───────────────▶ │   backend   │ ───────────────▶ │  EU SEDIA search  │
│ (Streamlit) │ ◀─────────────── │  (FastAPI)  │ ◀─────────────── │  API (external)   │
└─────────────┘   JSON results   └─────────────┘   raw JSON       └───────────────────┘
```

- **backend** — a FastAPI service that calls the EU search API, reshapes its (very verbose) response into a compact structure, and merges/deduplicates results that reference the same project.
- **frontend** — a Streamlit app that provides the search UI, filters, map, charts, and network graph. All computed client-side from whatever the backend returns — no database involved.

Two containers, wired together with Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [`Docker-Compose`](https://docs.docker.com/compose/install/)


## Quick start

```bash
git clone https://github.com/mmbazm/eu_search_projects.git
cd eu_project_search
docker-compose up --build
```

Then open:

- **App**: http://localhost:8501
- **API docs** (interactive Swagger UI): http://localhost:8000/docs

Type a keyword (e.g. `telco`), hit Search, and explore the results on the left, details on the right, and the funding/network charts below.

To stop:

```bash
docker-compose down
```

## Project structure

```
eu-project-search/
├── docker-compose.yml       # wires the two containers together
├── LICENSE
├── README.md
├── docs/ # contains files and screenshots
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py
│       └── main.py          # FastAPI app: EU API client + response reshaping
└── frontend/
    ├── Dockerfile
    ├── requirements.txt
    └── app.py                # Streamlit UI: search, filters, map, charts, graph
```

## API reference

`GET /api/search?text=<keyword>`

`text` accepts one keyword `text=telco`.

<details>
<summary>Example response</summary>

```json
{
  "results": {
    "projects": [
      {
        "id": "101234567",
        "title": "...",
        "summary": "...",
        "acronym": "3CNET",
        "url": "https://...",
        "start_date": "2024-01-01",
        "end_date": "2027-06-30",
        "participants": [
          {
            "legalName": "PRORAIL BV",
            "city": "Utrecht",
            "country": "Netherlands",
            "countryCode": "NL",
            "role": "coordinator",
            "website": "https://www.prorail.nl",
            "euContribution": 151495.0,
            "latitude": 52.0884998,
            "longitude": 5.1141631
          }
        ]
      }
    ]
  },
  "warnings": []
}
```

</details>

Try it directly:

```bash
curl "http://localhost:8000/api/search?text=telco"
```

## Configuration

All configuration is via environment variables, set in `docker-compose.yml`.

| Service  | Variable          | Default                                                      | Notes                                            |
|----------|-------------------|----------------------------------------------------------------|---------------------------------------------------|
| backend  | `EU_API_BASE_URL` | `https://api.tech.ec.europa.eu/search-api/prod/rest/search`  | The upstream EU search API                       |
| backend  | `EU_API_KEY`      | `SEDIA_NONH2020_PROD`                                          | Override for a different dataset (e.g. H2020)     |
| backend  | `EU_API_TIMEOUT`  | `20`                                                            | Seconds, per keyword request                      |
| frontend | `BACKEND_URL`     | `http://localhost:8000`                                          | Must use the Docker Compose service name           |

## Design notes / assumptions

These are worth knowing if you're extending the project:

- **`metadata.participants` parsing**: this field is a one-element list containing a JSON-*encoded string* (an array of participant objects), not actual JSON — the backend does a nested `json.loads` and skips any entry it can't parse rather than failing the whole request.
- **Dates trimmed to `YYYY-MM-DD`**: the EU API returns full timestamps like `2026-09-01T00:00:00.000+0100`; the time/timezone part is always midnight and meaningless here, so it's dropped.
- **Year filters are ranges, not exact matches**: "filter by start/end year" is a slider range (e.g. 2022–2025), which is usually more useful than an exact-year dropdown.
- **EU API requires POST**: despite taking its parameters as a query string (matching how you'd expect a GET request to look), the upstream API only accepts POST — GET returns `405 Method not allowed`.
- **Charts and the network graph are recomputed per view, not stored**: they reflect only whatever's currently in the filtered results — there's no database or persistence layer.
- **`latitude`/`longitude`/`euContribution` are additions beyond a minimal participant record**: the source data already carries them, and they're what power the map and the funding chart respectively.

## Contributing

Contributions are welcome:

1. Fork the repo and create a branch (`git checkout -b feature/my-feature`).
2. Make your changes. Both services are plain Python — no build step beyond `pip install -r requirements.txt` if you want to run them outside Docker for faster iteration.
3. Test locally with `docker-compose up --build`.
4. Open a pull request describing what changed and why.

Bug reports and feature requests are welcome via [Issues](../../issues).

## License

[MIT](LICENSE) — see the LICENSE file for details.

## Acknowledgements

Data from the European Commission's [SEDIA Funding & Tenders](https://ec.europa.eu/info/funding-tenders/opportunities/portal/) search API. This project is not affiliated with or endorsed by the European Commission.
