# Big Five Scoring Index

A static website covering the NFL, NBA, MLB, NHL and MLS. It has:
- scoring trends since 2019
- searchable player stats (full stat lines) for every team
- team stats with league ranks

The site rebuilds itself every morning.

## How it works

| Piece | What it does |
|---|---|
| `site/index.html` | The whole web page. It loads its numbers from `site/data/*.json`. |
| `scripts/scrape.py` | Pulls each league's current season from the reference sites and writes the JSON files. |
| `scripts/build.py` | Shapes the scraped tables into the JSON format the page reads. |
| `.github/workflows/update.yml` | Runs the scraper daily at 10:17 UTC, commits the new data and publishes the site to GitHub Pages. |

Each run makes about 50 page requests, spaced 4 seconds apart per site.

**Sources:**
- Basketball-Reference, Hockey-Reference, Baseball-Reference and Pro-Football-Reference league pages
- Stats Crew team pages for MLS

**Which season each league shows:** the scraper picks the current season automatically. Before a new season has games, it keeps showing the last completed one. For example, the NBA switches to 2026–27 after opening night.

**When a source fails:** if a source is down or changes its layout, that league keeps yesterday's data and the page footer says so. The workflow run is marked failed, so GitHub emails you. The other leagues still update.

## One-time setup

1. Settings → Pages → Build and deployment → Source: **GitHub Actions**.
2. Actions tab → *Daily stats refresh* → **Run workflow**. This runs the first refresh right away.
3. The site appears at `https://<your-user>.github.io/<repo>/`.

## Running it yourself

```bash
pip install -r requirements.txt
python scripts/scrape.py            # all leagues
python scripts/scrape.py nfl mls    # just some leagues
python -m http.server -d site 8000  # preview at http://localhost:8000
```

## Notes

- Please keep the request pacing as it is. Sports-Reference asks automated tools to stay under 20 requests a minute, and it attributes its data. Its terms of use govern reuse of its data.
- The "Ask the analyst" tab only works when the page is opened inside Claude. On the public site it stays hidden.
