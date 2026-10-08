#!/usr/bin/env python3
"""Daily updater for the Big Five Scoring Index site.

Pulls the current season for NBA, NHL, MLB, NFL (Sports-Reference sites) and MLS (Stats Crew),
writes the intermediate CSVs that build.py understands, builds site/data/<league>.json,
and refreshes site/data/trends.json and site/data/meta.json.

A league that fails to download or fails its sanity checks keeps yesterday's file, and the
failure is recorded in meta.json (the workflow then flags the run so the owner gets an email).

Usage: python scripts/scrape.py [nba nhl mlb nfl mls] [--offline DIR]
  --offline DIR  read saved pages from DIR instead of the network (for tests); file names are
                 the URL with every non-alphanumeric character replaced by "_".
"""
import csv
import datetime as dt
import json
import os
import re
import sys
import tempfile
import time
import traceback

from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build  # noqa: E402

ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "site", "data")
REPO = os.environ.get("GITHUB_REPOSITORY", "scoring-index")
UA = f"Mozilla/5.0 (compatible; ScoringIndexBot/1.0; +https://github.com/{REPO}) daily stats refresh"
OFFLINE = None
BR, HR, BBR, PFR = ("https://www.basketball-reference.com", "https://www.hockey-reference.com",
                    "https://www.baseball-reference.com", "https://www.pro-football-reference.com")
SC = "https://www.statscrew.com"
COMBINED = re.compile(r"^(\d+TM|TOT|2TM|3TM|4TM|5TM)$", re.I)


# ---------------------------------------------------------------- fetching
class Fetcher:
    """Polite fetcher: Sports-Reference allows ~20 requests/minute, so wait 4 s per host."""

    def __init__(self):
        import requests
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
        self.last = {}
        self.count = 0

    def get(self, url, gap=4.0):
        if OFFLINE:
            p = os.path.join(OFFLINE, re.sub(r"[^A-Za-z0-9]", "_", url))
            if not os.path.exists(p):
                return None
            return open(p, encoding="utf-8").read()
        host = url.split("/")[2]
        for attempt in range(4):
            wait = self.last.get(host, 0) + gap - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last[host] = time.time()
            self.count += 1
            try:
                r = self.s.get(url, timeout=40)
            except Exception as e:  # network hiccup
                print(f"  ! {url}: {e}; retrying", flush=True)
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code == 404:
                return None
            if r.status_code == 429 or r.status_code >= 500:
                delay = int(r.headers.get("Retry-After", "0") or 0) or 60 * (attempt + 1)
                print(f"  ! {url}: HTTP {r.status_code}; waiting {delay}s", flush=True)
                time.sleep(min(delay, 300))
                continue
            r.raise_for_status()
            return r.content.decode("utf-8", errors="replace")
        raise RuntimeError(f"gave up on {url}")


F = None


def soup_of(html):
    # Sports-Reference hides many tables inside HTML comments; unwrap them first.
    return BeautifulSoup(html.replace("<!--", "").replace("-->", ""), "lxml")


# ---------------------------------------------------------------- table parsing
class Row(dict):
    """Cells keyed by header label (first occurrence). .all[label] holds every occurrence,
    .over['Group|label'] keys by over-header, .href[label] holds the cell's first link."""

    def __init__(self):
        super().__init__()
        self.all, self.over, self.href = {}, {}, {}

    def g(self, *labels, default=""):
        for lab in labels:
            v = self.get(lab)
            if v not in (None, ""):
                return v
        return default


def _expand(tr):
    out = []
    for c in tr.find_all(["th", "td"], recursive=False):
        out += [c.get_text(" ", strip=True)] * int(c.get("colspan", 1) or 1)
    return out


def parse_table(tbl):
    head = tbl.find("thead")
    trs = head.find_all("tr", recursive=False) if head else []
    if not trs:
        first = tbl.find("tr")
        trs = [first] if first else []
    if not trs:
        return [], []
    labels = _expand(trs[-1])
    overs = _expand(trs[-2]) if len(trs) > 1 else [""] * len(labels)
    overs += [""] * (len(labels) - len(overs))
    body = tbl.find_all("tbody") or [tbl]
    rows = []
    for tb in body:
        for tr in tb.find_all("tr", recursive=False):
            cls = " ".join(tr.get("class", []))
            if "thead" in cls or "over_header" in cls:
                continue
            cells = tr.find_all(["th", "td"], recursive=False)
            if len(cells) < 2:
                continue
            vals, hrefs = [], []
            for c in cells:
                n = int(c.get("colspan", 1) or 1)
                a = c.find("a")
                vals += [c.get_text(" ", strip=True)] * n
                hrefs += [a.get("href") if a else None] * n
            if vals[:len(labels)] == labels[:len(vals)]:
                continue  # repeated header row
            r = Row()
            for i, lab in enumerate(labels):
                if i >= len(vals):
                    break
                v = vals[i]
                r.all.setdefault(lab, []).append(v)
                r.over[f"{overs[i]}|{lab}"] = v
                if lab not in r:
                    r[lab] = v
                    r.href[lab] = hrefs[i]
            rows.append(r)
    return labels, rows


def find_table(soup, ids=(), need=(), nth=0):
    for i in ids:
        t = soup.find("table", id=i)
        if t is not None:
            labels, rows = parse_table(t)
            if all(n in labels for n in need):
                return rows
    hits = []
    for t in soup.find_all("table"):
        labels, rows = parse_table(t)
        if need and all(n in labels for n in need) and rows:
            hits.append(rows)
    if len(hits) > nth:
        return hits[nth]
    raise LookupError(f"no table with columns {list(need)} (ids tried: {list(ids)})")


def clean_name(s):
    return re.sub(r"[\*\+#\?†]+$", "", (s or "").strip()).strip()


def team_code(r, *labels):
    for lab in labels:
        h = r.href.get(lab)
        if h:
            m = re.search(r"/teams/([A-Za-z0-9]+)/", h)
            if m:
                return m.group(1)
    return None


def write_csv(d, name, header, rows):
    with open(os.path.join(d, name), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([r.get(h, "") for h in header])


def fnum(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0


def player_rows(rows):
    """Keep one row per player per team: drop combined (2TM/TOT) rows, league-average and blank rows."""
    out = []
    for r in rows:
        name = clean_name(r.g("Player"))
        team = r.g("Team", "Tm")
        if not name or name in ("Player", "League Average") or not team or COMBINED.match(team):
            continue
        r["_name"], r["_team"] = name, team
        out.append(r)
    return out


def season_years(kind, today):
    y, m = today.year, today.month
    if kind == "winter":   # NBA / NHL, labelled by end year on the reference sites
        e = y + 1 if m >= 8 else y
        return [e, e - 1]
    if kind == "mlb":
        return [y, y - 1] if m >= 4 else [y - 1]
    if kind == "nfl":
        return [y, y - 1] if m >= 9 else [y - 1]
    if kind == "mls":
        return [y, y - 1] if m >= 3 else [y - 1]


# ---------------------------------------------------------------- NBA
def scrape_nba(E, d):
    s = soup_of(F.get(f"{BR}/leagues/NBA_{E}_per_game.html") or "")
    ps = player_rows(find_table(s, ["per_game_stats"], ["Player", "G", "PTS"]))
    cols = ["G", "GS", "MP", "FG", "FGA", "FG%", "3P", "3PA", "3P%", "FT", "FTA", "FT%", "ORB", "DRB", "TRB",
            "AST", "STL", "BLK", "TOV", "PF", "PTS"]
    out = [dict({"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": r.g("Pos")},
                **{c: r.g(c) for c in cols}) for r in ps]
    write_csv(d, "nba_players.csv", ["Team", "Player", "Age", "Pos"] + cols, out)

    s = soup_of(F.get(f"{BR}/leagues/NBA_{E}.html") or "")
    tm = find_table(s, ["per_game-team"], ["Team", "G", "PTS", "FG%"])
    op = find_table(s, ["per_game-opponent"], ["Team", "G", "PTS", "FG%"], nth=1)
    adv = find_table(s, ["advanced-team"], ["Team", "W", "L", "Pace"])
    T = {}
    for r in tm:
        c = team_code(r, "Team")
        if c:
            T[c] = {"Team": c, "PTS": r.g("PTS"), "G": r.g("G"), "_name": clean_name(r.g("Team"))}
    for r in op:
        c = team_code(r, "Team")
        if c in T:
            T[c]["OPP"] = r.g("PTS")
    for r in adv:
        c = team_code(r, "Team")
        if c in T:
            T[c].update(W=r.g("W"), L=r.g("L"), Pace=r.g("Pace"))
    for c, t in T.items():
        build.NBA_TEAMS.setdefault(c, t["_name"])
    write_csv(d, "nba_teams.csv", ["Team", "W", "L", "PTS", "OPP", "Pace"], T.values())
    gp = sum(fnum(t["G"]) for t in T.values())
    pts = sum(fnum(t["PTS"]) * fnum(t["G"]) for t in T.values())
    return {"players": len(out), "teams": len(T), "gp": gp, "pf": pts, "full": 82,
            "url": f"{BR}/leagues/NBA_{E}.html"}


# ---------------------------------------------------------------- NHL
def scrape_nhl(E, d):
    s = soup_of(F.get(f"{HR}/leagues/NHL_{E}_skaters.html") or "")
    ps = player_rows(find_table(s, ["player_stats", "skaters"], ["Player", "GP", "G", "A", "PTS"]))
    out = []
    for r in ps:
        pp = r.all.get("PP", [""])
        sh = r.all.get("SH", [""])
        out.append({"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": r.g("Pos"),
                    "GP": r.g("GP"), "G": r.g("G"), "A": r.g("A"), "PTS": r.g("PTS"), "PM": r.g("+/-"),
                    "PIM": r.g("PIM"), "PPG": r.over.get("Goals|PP") or pp[0], "SHG": r.over.get("Goals|SH") or sh[0],
                    "GWG": r.g("GW", "GWG"), "S": r.g("S", "SOG"), "SPct": r.g("S%", "SH%"), "ATOI": r.g("ATOI"),
                    "BLK": r.g("BLK"), "HIT": r.g("HIT"), "FOPct": r.g("FO%")})
    write_csv(d, "nhl_sk.csv", ["Team", "Player", "Age", "Pos", "GP", "G", "A", "PTS", "PM", "PIM", "PPG", "SHG",
                                "GWG", "S", "SPct", "ATOI", "BLK", "HIT", "FOPct"], out)
    s = soup_of(F.get(f"{HR}/leagues/NHL_{E}_goalies.html") or "")
    gs = player_rows(find_table(s, ["goalie_stats", "goalies"], ["Player", "GP", "GA", "SV%"]))
    gout = [{"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "GP": r.g("GP"), "GS": r.g("GS"),
             "W": r.g("W"), "L": r.g("L"), "OTL": r.g("T/O", "OTL", "T/OL", "OL"), "GA": r.g("GA"), "SA": r.g("SA"),
             "SV": r.g("SV"), "SVPct": r.g("SV%"), "GAA": r.g("GAA"), "SO": r.g("SO")} for r in gs]
    write_csv(d, "nhl_g.csv", ["Team", "Player", "Age", "GP", "GS", "W", "L", "OTL", "GA", "SA", "SV", "SVPct",
                               "GAA", "SO"], gout)
    s = soup_of(F.get(f"{HR}/leagues/NHL_{E}.html") or "")
    T = {}
    for r in find_table(s, ["stats"], ["GP", "W", "L", "PTS", "GF", "GA"]):
        c = None
        for lab in list(r.href):
            c = c or team_code(r, lab)
        if not c:
            continue
        name = next((clean_name(v) for k, v in r.items() if r.href.get(k) and "/teams/" in (r.href.get(k) or "")), c)
        build.NHL_TEAMS.setdefault(c, name)
        T[c] = {"Team": c, "GP": r.g("GP"), "W": r.g("W"), "L": r.g("L"), "OTL": r.g("OL", "OTL", "OTL "),
                "PTS": r.g("PTS"), "GF": r.g("GF"), "GA": r.g("GA"), "PPPct": r.g("PP%"), "PKPct": r.g("PK%")}
    write_csv(d, "nhl_teams.csv", ["Team", "GP", "W", "L", "OTL", "PTS", "GF", "GA", "PPPct", "PKPct"], T.values())
    return {"players": len(out) + len(gout), "teams": len(T), "gp": sum(fnum(t["GP"]) for t in T.values()),
            "pf": sum(fnum(t["GF"]) for t in T.values()), "full": 82, "url": f"{HR}/leagues/NHL_{E}.html"}


# ---------------------------------------------------------------- MLB
def scrape_mlb(Y, d):
    s = soup_of(F.get(f"{BBR}/leagues/majors/{Y}-standard-batting.shtml") or "")
    bs = player_rows(find_table(s, ["players_standard_batting"], ["Player", "PA", "HR", "OPS"]))
    bcols = ["G", "PA", "AB", "R", "H", "2B", "3B", "HR", "RBI", "SB", "CS", "BB", "SO", "BA", "OBP", "SLG", "OPS"]
    bat = [dict({"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": r.g("Pos", "Pos Summary"),
                 "OPSp": r.g("OPS+")}, **{c: r.g(c) for c in bcols}) for r in bs]
    write_csv(d, "mlb_bat.csv", ["Team", "Player", "Age", "Pos"] + bcols + ["OPSp"], bat)
    s = soup_of(F.get(f"{BBR}/leagues/majors/{Y}-standard-pitching.shtml") or "")
    pr = player_rows(find_table(s, ["players_standard_pitching"], ["Player", "IP", "ERA"]))
    pcols = ["W", "L", "ERA", "G", "GS", "SV", "IP", "H", "R", "ER", "HR", "BB", "SO", "WHIP"]
    pit = [dict({"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": "", "ERAp": r.g("ERA+")},
                **{c: r.g(c) for c in pcols}) for r in pr]
    write_csv(d, "mlb_pit.csv", ["Team", "Player", "Age", "Pos"] + pcols + ["ERAp"], pit)
    s = soup_of(F.get(f"{BBR}/leagues/majors/{Y}-standings.shtml") or "")
    T = {}
    for r in find_table(s, ["expanded_standings_overall"], ["W", "L", "R", "RA"]):
        c = team_code(r, "Tm", "Team")
        if not c:
            continue
        build.MLB_TEAMS.setdefault(c, clean_name(r.g("Tm", "Team")))
        T[c] = {"Team": c, "W": r.g("W"), "L": r.g("L"), "R": r.g("R"), "RA": r.g("RA")}
    write_csv(d, "mlb_teams.csv", ["Team", "W", "L", "R", "RA"], T.values())
    return {"players": len(bat) + len(pit), "teams": len(T),
            "gp": sum(fnum(t["W"]) + fnum(t["L"]) for t in T.values()),
            "pf": sum(fnum(t["R"]) for t in T.values()), "full": 162, "url": f"{BBR}/leagues/majors/{Y}.shtml"}


# ---------------------------------------------------------------- NFL
PFR_CODES = {"crd": "ARI", "atl": "ATL", "rav": "BAL", "buf": "BUF", "car": "CAR", "chi": "CHI", "cin": "CIN",
             "cle": "CLE", "dal": "DAL", "den": "DEN", "det": "DET", "gnb": "GNB", "htx": "HOU", "clt": "IND",
             "jax": "JAX", "kan": "KAN", "sdg": "LAC", "ram": "LAR", "rai": "LVR", "mia": "MIA", "min": "MIN",
             "nor": "NOR", "nwe": "NWE", "nyg": "NYG", "nyj": "NYJ", "phi": "PHI", "pit": "PIT", "sea": "SEA",
             "sfo": "SFO", "tam": "TAM", "oti": "TEN", "was": "WAS"}


def nfl_team(r):
    c = team_code(r, "Tm", "Team")
    if c and c.lower() in PFR_CODES:
        return PFR_CODES[c.lower()]
    name = clean_name(r.g("Tm", "Team"))
    for k, v in build.NFL_TEAMS.items():
        if v == name:
            return k
    return None


def scrape_nfl(Y, d):
    base = f"{PFR}/years/{Y}"
    s = soup_of(F.get(f"{base}/passing.htm") or "")
    pa = player_rows(find_table(s, ["passing"], ["Player", "Cmp", "Att", "Yds"]))
    passing = [{"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": r.g("Pos"), "G": r.g("G"),
                "GS": r.g("GS"), "Cmp": r.g("Cmp"), "Att": r.g("Att"), "Yds": r.all["Yds"][0], "TD": r.g("TD"),
                "Int": r.g("Int"), "Lng": r.g("Lng"), "Rate": r.g("Rate"), "Sk": r.g("Sk")} for r in pa]
    write_csv(d, "nfl_pass.csv", ["Team", "Player", "Age", "Pos", "G", "GS", "Cmp", "Att", "Yds", "TD", "Int", "Lng",
                                  "Rate", "Sk"], passing)
    rr = {}

    def slot(r):
        k = (r["_name"], r["_team"])
        if k not in rr:
            rr[k] = {"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": r.g("Pos"), "G": 0, "GS": 0,
                     "Fmb": 0}
        o = rr[k]
        o["Pos"] = o["Pos"] or r.g("Pos")
        o["G"] = max(fnum(o["G"]), fnum(r.g("G")))
        o["GS"] = max(fnum(o["GS"]), fnum(r.g("GS")))
        o["Fmb"] = max(fnum(o["Fmb"]), fnum(r.g("Fmb")))
        return o
    s = soup_of(F.get(f"{base}/rushing.htm") or "")
    for r in player_rows(find_table(s, ["rushing"], ["Player", "Att", "Yds", "TD"])):
        o = slot(r)
        o.update(RushAtt=r.g("Att"), RushYds=r.all["Yds"][0], RushTD=r.all["TD"][0], RushLng=r.g("Lng"))
    s = soup_of(F.get(f"{base}/receiving.htm") or "")
    for r in player_rows(find_table(s, ["receiving"], ["Player", "Rec", "Yds", "TD"])):
        o = slot(r)
        o.update(Tgt=r.g("Tgt"), Rec=r.g("Rec"), RecYds=r.all["Yds"][0], RecTD=r.all["TD"][0], RecLng=r.g("Lng"))
    for o in rr.values():
        for k in ("G", "GS", "Fmb"):
            o[k] = int(o[k])
    write_csv(d, "nfl_rr.csv", ["Team", "Player", "Age", "Pos", "G", "GS", "RushAtt", "RushYds", "RushTD", "RushLng",
                                "Tgt", "Rec", "RecYds", "RecTD", "RecLng", "Fmb"], rr.values())
    s = soup_of(F.get(f"{base}/defense.htm") or "")
    de = []
    for r in player_rows(find_table(s, ["defense"], ["Player", "Comb", "Sk"])):
        yds, tds = r.all.get("Yds", [""]), r.all.get("TD", [""])
        de.append({"Team": r["_team"], "Player": r["_name"], "Age": r.g("Age"), "Pos": r.g("Pos"), "G": r.g("G"),
                   "GS": r.g("GS"), "Int": r.g("Int"), "IntYds": yds[0], "IntTD": tds[0], "PD": r.g("PD"),
                   "FF": r.g("FF"), "FR": r.g("FR"), "Sk": r.g("Sk"), "Comb": r.g("Comb"), "Solo": r.g("Solo"),
                   "TFL": r.g("TFL"), "QBHits": r.g("QBHits")})
    write_csv(d, "nfl_def.csv", ["Team", "Player", "Age", "Pos", "G", "GS", "Int", "IntYds", "IntTD", "PD", "FF", "FR",
                                 "Sk", "Comb", "Solo", "TFL", "QBHits"], de)
    s = soup_of(F.get(f"{base}/kicking.htm") or "")
    kick = []
    for r in player_rows(find_table(s, ["kicking"], ["Player", "XPM", "FGM"])):
        kick.append({"Player": r["_name"], "Team": r["_team"], "Age": r.g("Age"), "G": r.g("G"),
                     "FGM": r.all["FGM"][-1], "FGA": r.all["FGA"][-1], "Lng": r.g("Lng"), "FGPct": r.g("FG%"),
                     "XPM": r.g("XPM"), "XPA": r.g("XPA")})
    write_csv(d, "nfl_kick.csv", ["Player", "Team", "Age", "G", "FGM", "FGA", "Lng", "FGPct", "XPM", "XPA"], kick)

    s = soup_of(F.get(f"{base}/") or "")
    T = {}
    for conf in ("AFC", "NFC"):
        for r in find_table(s, [conf], ["W", "L", "PF", "PA"], nth=0 if conf == "AFC" else 1):
            c = nfl_team(r)
            if c:
                T[c] = {"Team": c, "W": r.g("W"), "L": r.g("L"), "Ties": r.g("T", default="0"), "PF": r.g("PF"),
                        "PA": r.g("PA")}
    for tid, nth, yk, tk in (("team_stats", 0, "OffYds", "TO"), ("opp_stats", 1, "DefYds", "Takeaways")):
        for r in find_table(s, [tid], ["PF", "Yds", "Ply", "TO"], nth=nth):
            c = nfl_team(r)
            if c in T:
                T[c][yk] = r.all["Yds"][0]
                T[c][tk] = r.g("TO")
    write_csv(d, "nfl_teams.csv", ["Team", "W", "L", "Ties", "PF", "PA", "OffYds", "DefYds", "TO", "Takeaways"],
              T.values())

    weeks = {}
    try:
        s = soup_of(F.get(f"{base}/games.htm") or "")
        for r in find_table(s, ["games"], ["Week", "PtsW", "PtsL"]):
            w, a, b = r.g("Week"), r.g("PtsW"), r.g("PtsL")
            if w.isdigit() and a != "" and b != "":
                x = weeks.setdefault(int(w), {"w": int(w), "p": 0, "games": 0})
                x["p"] += int(fnum(a) + fnum(b))
                x["games"] += 1
    except Exception as e:
        print("  ! NFL weekly scores skipped:", e)
    gp = sum(fnum(t["W"]) + fnum(t["L"]) + fnum(t["Ties"]) for t in T.values())
    return {"players": len(passing) + len(rr) + len(de) + len(kick), "teams": len(T), "gp": gp,
            "pf": sum(fnum(t["PF"]) for t in T.values()), "full": 17, "url": f"{base}/",
            "weeks": [weeks[k] for k in sorted(weeks)]}


# ---------------------------------------------------------------- MLS
SC_CODES = {"ATL": "ATL", "AUS": "ATX", "MON": "MTL", "CHA": "CLT", "CHI": "CHI", "COL": "COL", "CLB": "CLB",
            "DC": "DC", "CIN": "CIN", "DAL": "DAL", "HOU": "HOU", "IMI": "MIA", "LA": "LAG", "LAF": "LAFC",
            "MIN": "MIN", "NAS": "NSH", "NE": "NE", "NYC": "NYC", "ORC": "ORL", "PHI": "PHI", "POR": "POR",
            "RSL": "RSL", "NY": "RBNY", "SD": "SD", "SJ": "SJ", "SEA": "SEA", "KC": "SKC", "SLC": "STL",
            "TOR": "TOR", "VAN": "VAN"}


def minutes(v):
    v = (v or "").replace(",", "").strip()
    if ":" in v:
        m, _, s = v.partition(":")
        return str(int(fnum(m) + (1 if fnum(s) >= 30 else 0)))
    return v


def scrape_mls(Y, d):
    s = BeautifulSoup(F.get(f"{SC}/soccer/l-MLS/y-{Y}", gap=2) or "", "lxml")
    links = {}
    for a in s.find_all("a", href=True):
        m = re.search(r"/soccer/stats/t-([A-Za-z0-9]+)/y-(\d{4})", a["href"])
        if m and int(m.group(2)) == Y and a.get_text(strip=True):
            links.setdefault(m.group(1), a.get_text(strip=True))
    P, K, T = [], [], []
    for code, name in sorted(links.items()):
        ab = SC_CODES.get(code, code)
        build.MLS_TEAMS.setdefault(ab, name)
        html = F.get(f"{SC}/soccer/stats/t-{code}/y-{Y}", gap=2) or ""
        ts = BeautifulSoup(html, "lxml")
        field = find_table(ts, [], ["Player", "Pos", "GP", "G", "A"])
        keep = find_table(ts, [], ["Player", "GP", "Min", "SVS"])
        gf = None
        for r in field:
            n = clean_name(r.g("Player"))
            if n.lower() in ("totals", "total", "team totals"):
                gf = r.g("G")
                continue
            if not n or n == "Player":
                continue
            P.append({"Team": ab, "Player": n, "Pos": r.g("Pos"), "GP": r.g("GP"), "GS": r.g("GS"), "G": r.g("G"),
                      "A": r.g("A"), "FC": r.g("FC"), "FS": r.g("FS"), "Y": r.g("Y"), "R": r.g("R"),
                      "OFF": r.g("OFF"), "Shts": r.g("Shts"), "SPct": r.g("S%"), "SOG": r.g("SOG"),
                      "SGPct": r.g("SG%")})
        ga = 0
        for r in keep:
            n = clean_name(r.g("Player"))
            if not n or n == "Player" or n.lower() in ("totals", "total", "team totals"):
                continue
            ga += fnum(r.g("GA"))
            K.append({"Team": ab, "Player": n, "GP": r.g("GP"), "GS": r.g("GS"), "Min": minutes(r.g("Min")),
                      "W": "", "L": "", "T": "", "SHO": r.g("SHO"), "GA": r.g("GA"), "GAA": r.g("GAA"),
                      "Shts": r.g("Shts"), "SVS": r.g("SVS"), "SVPct": r.g("SV%")})
        text = ts.get_text(" ", strip=True)
        m = re.search(r"Team Record:\s*(\d+)-(\d+)-(\d+)\s*-\s*(\d+)\s*points?", text)
        if not m:
            raise LookupError(f"no team record on {code}")
        if gf in (None, ""):
            gf = sum(fnum(p["G"]) for p in P if p["Team"] == ab)
        T.append({"Team": ab, "W": m.group(1), "L": m.group(2), "D": m.group(3), "GF": int(fnum(gf)),
                  "GA": int(ga), "Pts": m.group(4)})
    write_csv(d, "mls_p.csv", ["Team", "Player", "Pos", "GP", "GS", "G", "A", "FC", "FS", "Y", "R", "OFF", "Shts",
                               "SPct", "SOG", "SGPct"], P)
    write_csv(d, "mls_k.csv", ["Team", "Player", "GP", "GS", "Min", "W", "L", "T", "SHO", "GA", "GAA", "Shts", "SVS",
                               "SVPct"], K)
    write_csv(d, "mls_teams.csv", ["Team", "W", "L", "D", "GF", "GA", "Pts"], T)
    gp = sum(fnum(t["W"]) + fnum(t["L"]) + fnum(t["D"]) for t in T)
    return {"players": len(P) + len(K), "teams": len(T), "gp": gp, "pf": sum(fnum(t["GF"]) for t in T),
            "full": 34, "url": f"{SC}/soccer/l-MLS/y-{Y}"}


# ---------------------------------------------------------------- orchestration
LEAGUES = {
    #  id     kind      scraper     teams  min players  start-year offset  source label
    "nba": ("winter", scrape_nba, 30, 150, -1, "Basketball-Reference"),
    "nhl": ("winter", scrape_nhl, 32, 300, -1, "Hockey-Reference"),
    "mlb": ("mlb", scrape_mlb, 30, 500, 0, "Baseball-Reference"),
    "nfl": ("nfl", scrape_nfl, 32, 300, 0, "Pro-Football-Reference"),
    "mls": ("mls", scrape_mls, 29, 300, 0, "Stats Crew"),
}


def season_label(lg, yr):
    if LEAGUES[lg][0] == "winter":
        return f"{yr - 1}–{str(yr)[2:]}"
    return str(yr)


def run_league(lg, today):
    kind, fn, n_teams, n_players, off, src = LEAGUES[lg]
    errors = []
    for yr in season_years(kind, today):
        tmp = tempfile.mkdtemp(prefix=f"{lg}{yr}_")
        try:
            print(f"{lg.upper()} {yr}: fetching", flush=True)
            info = fn(yr, tmp)
            if info["teams"] < n_teams or info["players"] < n_players or info["gp"] <= 0:
                raise ValueError(f"only {info['teams']} teams / {info['players']} player rows / {info['gp']:.0f} team-games")
            build.HERE = tmp
            data = build.finalize(build.BUILDERS[lg]())
            partial = info["gp"] / info["teams"] < info["full"] - 0.5
            data["season"] = f"{season_label(lg, yr)} regular season" + (" (in progress)" if partial else "")
            data["source"] = {"label": src, "url": info["url"]}
            for g in data["groups"]:
                if not g["rows"]:
                    raise ValueError(f"stat group {g['id']} is empty")
            info.update(year=yr, start=yr + off, partial=partial, label=season_label(lg, yr), data=data)
            return info, errors
        except Exception as e:
            msg = f"{season_label(lg, yr)}: {type(e).__name__}: {e}"
            print("  !", msg, flush=True)
            traceback.print_exc(limit=2)
            errors.append(msg)
    return None, errors


def load(name, default):
    try:
        with open(os.path.join(DATA, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def dump(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, separators=(",", ":"))


def fmt(v, dp):
    return f"{v:.{dp}f}"


def write_insights(trends):
    out = []
    for L in trends["leagues"]:
        data = {int(k): v for k, v in L["data"].items()}
        base = [data[y] for y in range(2019, 2026) if y in data]
        if not data or not base:
            continue
        cur_y = max(data)
        cur = data[cur_y]
        avg = sum(base) / len(base)
        pct = (cur / avg - 1) * 100
        lab = L.get("curLabel") or str(cur_y)
        dp = L["dp"]
        when = f"{lab} to date" if L.get("partial") == cur_y else lab
        s = f"{when}: {fmt(cur, dp)} {L['unit']} per team per game, {pct:+.1f}% against the 2019–25 average of {fmt(avg, dp)}."
        hist = [v for y, v in data.items() if y != cur_y]
        if hist and cur > max(hist):
            s += " That is the highest in this span."
        elif hist and cur < min(hist):
            s += " That is the lowest in this span."
        prev = data.get(cur_y - 1)
        if prev:
            s += f" The previous season finished at {fmt(prev, dp)}."
        if L["id"] == "NFL" and trends.get("nflWeeks", {}).get("weeks"):
            wk = trends["nflWeeks"]["weeks"][-1]
            s += f" Week {wk['w']} averaged {wk['p'] / (2 * wk['games']):.1f}."
        out.append([L["id"], s])
    trends["insights"] = out


def main(argv):
    global OFFLINE, F
    if "--offline" in argv:
        i = argv.index("--offline")
        OFFLINE = argv[i + 1]
        del argv[i:i + 2]
    which = [a for a in argv if a in LEAGUES] or list(LEAGUES)
    F = Fetcher()
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    trends = load("trends.json", None)
    meta = load("meta.json", {"leagues": {}})
    failed = []
    for lg in which:
        info, errors = run_league(lg, today)
        m = meta["leagues"].setdefault(lg.upper(), {})
        m["checked"] = now.isoformat(timespec="minutes")
        if not info:
            m["ok"] = False
            m["error"] = "; ".join(errors)
            failed.append(lg.upper())
            continue
        dump(f"{lg}.json", info["data"])
        m.update(ok=True, error=None, updated=now.isoformat(timespec="minutes"), season=info["data"]["season"])
        print(f"{lg.upper()} {info['label']}: {info['teams']} teams, {info['players']} player rows", flush=True)
        if trends:
            T = next((t for t in trends["leagues"] if t["id"] == lg.upper()), None)
            if T:
                ppg = info["pf"] / info["gp"]
                T["data"][str(info["start"])] = round(ppg, 3)
                T["partial"] = info["start"] if info["partial"] else None
                T["curLabel"] = info["label"]
                games = info["gp"] / 2
                total = info["teams"] * info["full"] / 2
                if lg == "nfl":
                    wk = info.get("weeks") or []
                    T["status"] = f"{len(wk)} of 18 weeks played" if info["partial"] else "Regular season final"
                    if wk:
                        trends["nflWeeks"] = {"season": info["year"], "weeks": wk,
                                              "prevAvg": T["data"].get(str(info["start"] - 1))}
                elif info["partial"]:
                    T["status"] = f"{games:,.0f} of {total:,.0f} {'matches' if lg == 'mls' else 'games'} played"
                else:
                    T["status"] = "Regular season final"
                if info["year"] != season_years(LEAGUES[lg][0], today)[0]:
                    T["status"] = "Last season final · next season not started"
    meta["updated"] = now.isoformat(timespec="minutes")
    meta["failed"] = failed
    if trends:
        trends["updated"] = meta["updated"]
        write_insights(trends)
        dump("trends.json", trends)
    dump("meta.json", meta)
    print(f"Done: {F.count} page requests; failed: {failed or 'none'}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("| League | Status | Season |\n|---|---|---|\n")
            for k, v in meta["leagues"].items():
                fh.write(f"| {k} | {'updated' if v.get('ok') else 'kept previous data: ' + (v.get('error') or '')} | {v.get('season', '')} |\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
