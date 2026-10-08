"""Build per-league JSON files for the Scoring Index page from the gathered CSVs."""
import csv, json, os, sys

HERE = os.environ.get("CSV_DIR") or os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("OUT_DIR") or os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)


def num(v):
    v = (v or "").strip()
    if v == "":
        return None
    try:
        f = float(v)
        return int(f) if f.is_integer() and "." not in v else f
    except ValueError:
        return v


def read(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


NBA_TEAMS = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BRK": "Brooklyn Nets", "CHO": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans", "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHO": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz", "WAS": "Washington Wizards",
}


def build_nba():
    players = read("nba_players.csv")
    teams = read("nba_teams.csv")
    cols = [
        ("G", "G", 0), ("GS", "GS", 0), ("MP", "MIN", 1), ("PTS", "PTS", 1), ("TRB", "REB", 1), ("AST", "AST", 1),
        ("STL", "STL", 1), ("BLK", "BLK", 1), ("TOV", "TOV", 1), ("FG", "FGM", 1), ("FGA", "FGA", 1), ("FG%", "FG%", 3),
        ("3P", "3PM", 1), ("3PA", "3PA", 1), ("3P%", "3P%", 3), ("FT", "FTM", 1), ("FTA", "FTA", 1), ("FT%", "FT%", 3),
        ("ORB", "OREB", 1), ("DRB", "DREB", 1), ("PF", "PF", 1),
    ]
    rows = []
    for r in players:
        row = {"name": r["Player"], "team": r["Team"], "pos": r["Pos"], "age": num(r["Age"])}
        for k, _, _ in cols:
            row[k] = num(r[k])
        rows.append(row)
    team_rows = []
    for t in teams:
        team_rows.append({
            "abbr": t["Team"], "name": NBA_TEAMS[t["Team"]], "W": num(t["W"]), "L": num(t["L"]),
            "PF": num(t["PTS"]), "PA": num(t["OPP"]), "Pace": num(t["Pace"]),
        })
    return {
        "league": "NBA", "season": "2025–26 regular season", "unit": "points",
        "source": {"label": "Basketball-Reference team pages", "url": "https://www.basketball-reference.com/leagues/NBA_2026.html"},
        "teamCols": [
            {"k": "W", "label": "W", "dp": 0}, {"k": "L", "label": "L", "dp": 0},
            {"k": "PF", "label": "PTS/G", "dp": 1}, {"k": "PA", "label": "OPP/G", "dp": 1},
            {"k": "DIFF", "label": "DIFF", "dp": 1}, {"k": "Pace", "label": "PACE", "dp": 1},
        ],
        "teams": team_rows,
        "groups": [{
            "id": "per_game", "label": "Per game", "sortDefault": "PTS", "minKey": "G",
            "shareKey": "PTS", "shareMult": "G", "shareLabel": "Share of team points",
            "cols": [{"k": k, "label": lab, "dp": dp} for k, lab, dp in cols],
            "rows": rows,
        }],
    }


NHL_TEAMS = {
    "ANA": "Anaheim Ducks", "BOS": "Boston Bruins", "BUF": "Buffalo Sabres", "CGY": "Calgary Flames",
    "CAR": "Carolina Hurricanes", "CHI": "Chicago Blackhawks", "COL": "Colorado Avalanche", "CBJ": "Columbus Blue Jackets",
    "DAL": "Dallas Stars", "DET": "Detroit Red Wings", "EDM": "Edmonton Oilers", "FLA": "Florida Panthers",
    "LAK": "Los Angeles Kings", "MIN": "Minnesota Wild", "MTL": "Montreal Canadiens", "NSH": "Nashville Predators",
    "NJD": "New Jersey Devils", "NYI": "New York Islanders", "NYR": "New York Rangers", "OTT": "Ottawa Senators",
    "PHI": "Philadelphia Flyers", "PIT": "Pittsburgh Penguins", "SJS": "San Jose Sharks", "SEA": "Seattle Kraken",
    "STL": "St. Louis Blues", "TBL": "Tampa Bay Lightning", "TOR": "Toronto Maple Leafs", "UTA": "Utah Mammoth",
    "VAN": "Vancouver Canucks", "VEG": "Vegas Golden Knights", "WSH": "Washington Capitals", "WPG": "Winnipeg Jets",
}


def mmss(v):
    v = (v or "").strip()
    if ":" not in v:
        return None
    m, s = v.split(":")
    return round(int(m) + int(s) / 60, 2)


def build_nhl():
    sk_cols = [
        ("GP", "GP", 0), ("G", "G", 0), ("A", "A", 0), ("PTS", "PTS", 0), ("PM", "+/-", 0), ("PIM", "PIM", 0),
        ("PPG", "PPG", 0), ("SHG", "SHG", 0), ("GWG", "GWG", 0), ("S", "SOG", 0), ("SPct", "SH%", 1),
        ("ATOI", "TOI/G", 1), ("BLK", "BLK", 0), ("HIT", "HIT", 0), ("FOPct", "FO%", 1),
    ]
    g_cols = [
        ("GP", "GP", 0), ("GS", "GS", 0), ("W", "W", 0), ("L", "L", 0), ("OTL", "OTL", 0), ("GA", "GA", 0),
        ("SA", "SA", 0), ("SV", "SV", 0), ("SVPct", "SV%", 3), ("GAA", "GAA", 2), ("SO", "SO", 0),
    ]
    sk = []
    for r in read("nhl_sk.csv"):
        row = {"name": r["Player"], "team": r["Team"], "pos": r["Pos"], "age": num(r["Age"])}
        for k, _, _ in sk_cols:
            row[k] = mmss(r[k]) if k == "ATOI" else num(r[k])
        sk.append(row)
    gl = []
    for r in read("nhl_g.csv"):
        row = {"name": r["Player"], "team": r["Team"], "pos": "G", "age": num(r["Age"])}
        for k, _, _ in g_cols:
            row[k] = num(r[k])
        gl.append(row)
    teams = []
    for t in read("nhl_teams.csv"):
        teams.append({
            "abbr": t["Team"], "name": NHL_TEAMS[t["Team"]], "W": num(t["W"]), "L": num(t["L"]), "OTL": num(t["OTL"]),
            "PTS": num(t["PTS"]), "PF": num(t["GF"]), "PA": num(t["GA"]),
            "GFG": round(num(t["GF"]) / num(t["GP"]), 2), "GAG": round(num(t["GA"]) / num(t["GP"]), 2),
            "PPPct": num(t["PPPct"]), "PKPct": num(t["PKPct"]),
        })
    return {
        "league": "NHL", "season": "2025–26 regular season", "unit": "goals",
        "source": {"label": "Hockey-Reference team pages", "url": "https://www.hockey-reference.com/leagues/NHL_2026.html"},
        "teamSort": "PTS",
        "teamCols": [
            {"k": "PTS", "label": "PTS", "dp": 0}, {"k": "W", "label": "W", "dp": 0}, {"k": "L", "label": "L", "dp": 0},
            {"k": "OTL", "label": "OTL", "dp": 0}, {"k": "PF", "label": "GF", "dp": 0}, {"k": "PA", "label": "GA", "dp": 0},
            {"k": "DIFF", "label": "DIFF", "dp": 0}, {"k": "GFG", "label": "GF/G", "dp": 2}, {"k": "GAG", "label": "GA/G", "dp": 2},
            {"k": "PPPct", "label": "PP%", "dp": 1}, {"k": "PKPct", "label": "PK%", "dp": 1},
        ],
        "teams": teams,
        "groups": [
            {"id": "skaters", "label": "Skaters", "sortDefault": "PTS", "minKey": "GP",
             "shareKey": "G", "shareLabel": "Share of team goals",
             "cols": [{"k": k, "label": lab, "dp": dp} for k, lab, dp in sk_cols], "rows": sk},
            {"id": "goalies", "label": "Goalies", "sortDefault": "W", "minKey": "GP", "minDefault": 10,
             "cols": [dict({"k": k, "label": lab, "dp": dp}, **({"low": True} if k in ("GAA", "GA", "L", "OTL") else {}))
                      for k, lab, dp in g_cols], "rows": gl},
        ],
    }

MLB_TEAMS = {
    "ARI": "Arizona Diamondbacks", "ATH": "Athletics", "ATL": "Atlanta Braves", "BAL": "Baltimore Orioles",
    "BOS": "Boston Red Sox", "CHC": "Chicago Cubs", "CHW": "Chicago White Sox", "CIN": "Cincinnati Reds",
    "CLE": "Cleveland Guardians", "COL": "Colorado Rockies", "DET": "Detroit Tigers", "HOU": "Houston Astros",
    "KCR": "Kansas City Royals", "LAA": "Los Angeles Angels", "LAD": "Los Angeles Dodgers", "MIA": "Miami Marlins",
    "MIL": "Milwaukee Brewers", "MIN": "Minnesota Twins", "NYM": "New York Mets", "NYY": "New York Yankees",
    "PHI": "Philadelphia Phillies", "PIT": "Pittsburgh Pirates", "SDP": "San Diego Padres", "SEA": "Seattle Mariners",
    "SFG": "San Francisco Giants", "STL": "St. Louis Cardinals", "TBR": "Tampa Bay Rays", "TEX": "Texas Rangers",
    "TOR": "Toronto Blue Jays", "WSN": "Washington Nationals",
}
POSMAP = {"1": "P", "2": "C", "3": "1B", "4": "2B", "5": "3B", "6": "SS", "7": "LF", "8": "CF", "9": "RF"}


def mlb_pos(p):
    p = (p or "").strip()
    if not p or p.isalpha():
        return p
    for ch in p:
        if ch in POSMAP:
            return POSMAP[ch]
        if ch == "D":
            return "DH"
    return "PH"


def ip_dec(v):
    if v in (None, ""):
        return None
    whole, _, frac = str(v).partition(".")
    return int(whole) + (int(frac or 0) / 3)


def build_mlb():
    bcols = [("G", "G", 0), ("PA", "PA", 0), ("AB", "AB", 0), ("R", "R", 0), ("H", "H", 0), ("2B", "2B", 0),
             ("3B", "3B", 0), ("HR", "HR", 0), ("RBI", "RBI", 0), ("SB", "SB", 0), ("CS", "CS", 0), ("BB", "BB", 0),
             ("SO", "SO", 0), ("BA", "AVG", 3), ("OBP", "OBP", 3), ("SLG", "SLG", 3), ("OPS", "OPS", 3), ("OPSp", "OPS+", 0)]
    pcols = [("W", "W", 0), ("L", "L", 0), ("ERA", "ERA", 2), ("G", "G", 0), ("GS", "GS", 0), ("SV", "SV", 0),
             ("IP", "IP", 1), ("H", "H", 0), ("R", "R", 0), ("ER", "ER", 0), ("HR", "HR", 0), ("BB", "BB", 0),
             ("SO", "SO", 0), ("WHIP", "WHIP", 2), ("K9", "K/9", 1), ("BB9", "BB/9", 1)]
    bat = []
    for r in read("mlb_bat.csv"):
        row = {"name": r["Player"], "team": r["Team"], "pos": mlb_pos(r["Pos"]), "age": num(r["Age"])}
        for k, _, _ in bcols:
            row[k] = num(r[k])
        bat.append(row)
    pit = []
    for r in read("mlb_pit.csv"):
        ip = ip_dec(r["IP"])
        g, gs = num(r["G"]) or 0, num(r["GS"]) or 0
        pos = r["Pos"].strip() or ("SP" if gs and gs * 2 >= g else "RP")
        row = {"name": r["Player"], "team": r["Team"], "pos": pos, "age": num(r["Age"])}
        for k, _, _ in pcols:
            if k in ("K9", "BB9"):
                continue
            row[k] = num(r[k])
        row["IP"] = num(r["IP"])
        row["K9"] = round(row["SO"] * 9 / ip, 2) if ip else None
        row["BB9"] = round(row["BB"] * 9 / ip, 2) if ip else None
        if row.get("ERA") == "" or (ip == 0):
            row["ERA"] = None
        pit.append(row)
    teams = []
    for t in read("mlb_teams.csv"):
        gp = num(t["W"]) + num(t["L"])
        teams.append({"abbr": t["Team"], "name": MLB_TEAMS[t["Team"]], "W": num(t["W"]), "L": num(t["L"]),
                      "WPct": round(num(t["W"]) / gp, 3), "PF": num(t["R"]), "PA": num(t["RA"]),
                      "RG": round(num(t["R"]) / gp, 2), "RAG": round(num(t["RA"]) / gp, 2)})
    low = {"L", "ERA", "H", "R", "ER", "HR", "BB", "WHIP", "BB9"}
    return {
        "league": "MLB", "season": "2026 regular season", "unit": "runs",
        "source": {"label": "Baseball-Reference team pages", "url": "https://www.baseball-reference.com/leagues/majors/2026.shtml"},
        "teamSort": "W",
        "teamCols": [
            {"k": "W", "label": "W", "dp": 0}, {"k": "L", "label": "L", "dp": 0}, {"k": "WPct", "label": "PCT", "dp": 3},
            {"k": "PF", "label": "R", "dp": 0}, {"k": "PA", "label": "RA", "dp": 0}, {"k": "DIFF", "label": "DIFF", "dp": 0},
            {"k": "RG", "label": "R/G", "dp": 2}, {"k": "RAG", "label": "RA/G", "dp": 2},
        ],
        "teams": teams,
        "groups": [
            {"id": "batting", "label": "Batting", "sortDefault": "HR", "minKey": "PA", "minLabel": "Min PA",
             "minOpts": [0, 50, 200, 400], "minDefault": 200, "shareKey": "R", "shareLabel": "Share of team runs scored",
             "cols": [{"k": k, "label": lab, "dp": dp} for k, lab, dp in bcols], "rows": bat},
            {"id": "pitching", "label": "Pitching", "sortDefault": "SO", "minKey": "IP", "minLabel": "Min IP",
             "minOpts": [0, 20, 50, 100], "minDefault": 50, "shareKey": "SO", "shareLabel": "Share of team strikeouts",
             "cols": [dict({"k": k, "label": lab, "dp": dp}, **({"low": True} if k in low else {})) for k, lab, dp in pcols],
             "rows": pit},
        ],
    }

NFL_TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GNB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KAN": "Kansas City Chiefs",
    "LAC": "Los Angeles Chargers", "LAR": "Los Angeles Rams", "LVR": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NOR": "New Orleans Saints", "NWE": "New England Patriots", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SFO": "San Francisco 49ers", "TAM": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}
OFFENSE_POS = {"QB", "RB", "WR", "TE", "FB", "C", "G", "T", "OT", "OL", "OG", "K", "P", "LS"}


def build_nfl():
    def n0(v):
        x = num(v)
        return x if isinstance(x, (int, float)) else 0
    pass_rows = []
    for r in read("nfl_pass.csv"):
        att = n0(r["Att"])
        if att <= 0:
            continue
        row = {"name": r["Player"], "team": r["Team"], "pos": r["Pos"], "age": num(r["Age"])}
        for k in ("G", "GS", "Cmp", "Att", "Yds", "TD", "Int", "Rate", "Sk"):
            row[k] = num(r[k])
        row["Pct"] = round(100 * n0(r["Cmp"]) / att, 1)
        row["YA"] = round(n0(r["Yds"]) / att, 1)
        pass_rows.append(row)
    rr = []
    for r in read("nfl_rr.csv"):
        row = {"name": r["Player"], "team": r["Team"], "pos": r["Pos"], "age": num(r["Age"])}
        for k in ("G", "GS", "RushAtt", "RushYds", "RushTD", "Tgt", "Rec", "RecYds", "RecTD", "Fmb"):
            row[k] = n0(r[k])
        row["YPC"] = round(row["RushYds"] / row["RushAtt"], 1) if row["RushAtt"] else None
        row["YPR"] = round(row["RecYds"] / row["Rec"], 1) if row["Rec"] else None
        row["Scrim"] = row["RushYds"] + row["RecYds"]
        row["TotTD"] = row["RushTD"] + row["RecTD"]
        rr.append(row)
    de = []
    for r in read("nfl_def.csv"):
        pos = r["Pos"].split("/")[0].upper()
        row = {"name": r["Player"], "team": r["Team"], "pos": r["Pos"], "age": num(r["Age"])}
        for k in ("G", "GS", "Comb", "Solo", "TFL", "Sk", "QBHits", "Int", "IntYds", "IntTD", "PD", "FF", "FR"):
            row[k] = n0(r[k])
        if pos in OFFENSE_POS or not (row["Comb"] or row["Int"] or row["Sk"] or row["PD"]):
            continue
        de.append(row)
    kick = []
    for r in read("nfl_kick.csv"):
        fga, xpa = n0(r["FGA"]), n0(r["XPA"])
        if not fga and not n0(r["XPM"]):
            continue
        row = {"name": r["Player"], "team": r["Team"], "pos": "K", "age": num(r["Age"])}
        for k in ("G", "FGM", "FGA", "Lng", "XPM", "XPA"):
            row[k] = num(r[k])
        row["FGPct"] = round(100 * n0(r["FGM"]) / fga, 1) if fga else None
        row["Pts"] = 3 * n0(r["FGM"]) + n0(r["XPM"])
        kick.append(row)
    teams = []
    for t in read("nfl_teams.csv"):
        gp = n0(t["W"]) + n0(t["L"]) + n0(t["Ties"])
        teams.append({"abbr": t["Team"], "name": NFL_TEAMS[t["Team"]], "W": num(t["W"]), "L": num(t["L"]), "T": num(t["Ties"]),
                      "PF": num(t["PF"]), "PA": num(t["PA"]), "PFG": round(n0(t["PF"]) / gp, 1), "PAG": round(n0(t["PA"]) / gp, 1),
                      "OffYds": num(t["OffYds"]), "DefYds": num(t["DefYds"]), "TO": num(t["TO"]), "TK": num(t["Takeaways"]),
                      "TOM": n0(t["Takeaways"]) - n0(t["TO"])})
    C = lambda k, lab, dp=0, low=False: dict({"k": k, "label": lab, "dp": dp}, **({"low": True} if low else {}))
    return {
        "league": "NFL", "season": "2025 regular season", "unit": "points",
        "source": {"label": "Pro-Football-Reference team pages", "url": "https://www.pro-football-reference.com/years/2025/"},
        "teamSort": "W",
        "teamCols": [C("W", "W"), C("L", "L"), C("T", "T"), C("PF", "PF"), C("PA", "PA"), C("DIFF", "DIFF"),
                     C("PFG", "PF/G", 1), C("PAG", "PA/G", 1), C("OffYds", "OFF YDS"), C("DefYds", "DEF YDS", 0, True),
                     C("TO", "GIVEAWAYS", 0, True), C("TK", "TAKEAWAYS"), C("TOM", "TO +/-")],
        "teams": teams,
        "groups": [
            {"id": "passing", "label": "Passing", "sortDefault": "Yds", "minKey": "Att", "minLabel": "Min attempts",
             "minOpts": [0, 50, 150, 300], "minDefault": 150, "shareKey": "Yds", "shareLabel": "Share of team passing yards",
             "cols": [C("G", "G"), C("GS", "GS"), C("Cmp", "CMP"), C("Att", "ATT"), C("Pct", "CMP%", 1), C("Yds", "YDS"),
                      C("YA", "Y/A", 1), C("TD", "TD"), C("Int", "INT", 0, True), C("Rate", "RATE", 1), C("Sk", "SK", 0, True)],
             "rows": pass_rows},
            {"id": "scrimmage", "label": "Rushing & receiving", "sortDefault": "Scrim", "minKey": "G", "minLabel": "Min games",
             "minOpts": [0, 4, 8, 12], "minDefault": 4, "shareKey": "TotTD", "shareLabel": "Share of team scrimmage TDs",
             "cols": [C("G", "G"), C("GS", "GS"), C("RushAtt", "RUSH"), C("RushYds", "RUSH YDS"), C("YPC", "YPC", 1),
                      C("RushTD", "RUSH TD"), C("Tgt", "TGT"), C("Rec", "REC"), C("RecYds", "REC YDS"), C("YPR", "Y/R", 1),
                      C("RecTD", "REC TD"), C("Scrim", "SCRIM YDS"), C("TotTD", "TOT TD"), C("Fmb", "FMB", 0, True)],
             "rows": rr},
            {"id": "defense", "label": "Defense", "sortDefault": "Comb", "minKey": "G", "minLabel": "Min games",
             "minOpts": [0, 4, 8, 12], "minDefault": 4, "shareKey": "Sk", "shareLabel": "Share of team sacks",
             "cols": [C("G", "G"), C("GS", "GS"), C("Comb", "TKL"), C("Solo", "SOLO"), C("TFL", "TFL"), C("Sk", "SACKS", 1),
                      C("QBHits", "QB HITS"), C("Int", "INT"), C("IntYds", "INT YDS"), C("IntTD", "INT TD"), C("PD", "PD"),
                      C("FF", "FF"), C("FR", "FR")],
             "rows": de},
            {"id": "kicking", "label": "Kicking", "sortDefault": "Pts", "minKey": "FGA", "minLabel": "Min FG attempts",
             "minOpts": [0, 5, 15, 25], "minDefault": 5,
             "cols": [C("G", "G"), C("FGM", "FGM"), C("FGA", "FGA"), C("FGPct", "FG%", 1), C("Lng", "LNG"), C("XPM", "XPM"),
                      C("XPA", "XPA"), C("Pts", "PTS")],
             "rows": kick},
        ],
    }


MLS_TEAMS = {
    "MIA": "Inter Miami CF", "CLB": "Columbus Crew", "CIN": "FC Cincinnati", "PHI": "Philadelphia Union",
    "CLT": "Charlotte FC", "NYC": "New York City FC", "NSH": "Nashville SC", "ORL": "Orlando City SC",
    "ATL": "Atlanta United", "CHI": "Chicago Fire", "RBNY": "New York Red Bulls", "NE": "New England Revolution",
    "DC": "D.C. United", "TOR": "Toronto FC", "MTL": "CF Montréal", "SD": "San Diego FC", "LAFC": "Los Angeles FC",
    "LAG": "LA Galaxy", "VAN": "Vancouver Whitecaps", "SEA": "Seattle Sounders", "POR": "Portland Timbers",
    "MIN": "Minnesota United", "ATX": "Austin FC", "SJ": "San Jose Earthquakes", "COL": "Colorado Rapids",
    "DAL": "FC Dallas", "HOU": "Houston Dynamo", "SKC": "Sporting Kansas City", "RSL": "Real Salt Lake",
    "STL": "St. Louis City SC",
}


def build_mls():
    def n0(v):
        x = num(v)
        return x if isinstance(x, (int, float)) else 0
    pos_map = {"M-F": "M", "F-M": "F", "W": "F", "GK": "G"}
    field = []
    for r in read("mls_p.csv"):
        if r["Player"] == "Player":
            continue
        pos = pos_map.get(r["Pos"].strip(), r["Pos"].strip())
        if pos == "G":
            continue
        row = {"name": r["Player"], "team": r["Team"], "pos": pos}
        for k in ("GP", "GS", "G", "A", "FC", "FS", "Y", "R", "OFF", "Shts", "SOG"):
            row[k] = n0(r[k])
        row["GA_"] = row["G"] + row["A"]
        row["SPct"] = round(100 * row["G"] / row["Shts"], 1) if row["Shts"] else None
        row["SOGPct"] = round(100 * row["SOG"] / row["Shts"], 1) if row["Shts"] else None
        field.append(row)
    gk = []
    for r in read("mls_k.csv"):
        if r["Player"] == "Player":
            continue
        row = {"name": r["Player"], "team": r["Team"], "pos": "GK"}
        for k in ("GP", "GS", "Min", "SHO", "GA", "Shts", "SVS"):
            row[k] = n0(r[k])
        row["GAA"] = round(90 * row["GA"] / row["Min"], 2) if row["Min"] else None
        row["SVPct"] = round(100 * row["SVS"] / row["Shts"], 1) if row["Shts"] else None
        gk.append(row)
    teams = []
    for t in read("mls_teams.csv"):
        gp = n0(t["W"]) + n0(t["L"]) + n0(t["D"])
        teams.append({"abbr": t["Team"], "name": MLS_TEAMS[t["Team"]], "Pts": num(t["Pts"]), "W": num(t["W"]),
                      "L": num(t["L"]), "D": num(t["D"]), "PF": num(t["GF"]), "PA": num(t["GA"]),
                      "GFG": round(n0(t["GF"]) / gp, 2), "GAG": round(n0(t["GA"]) / gp, 2)})
    C = lambda k, lab, dp=0, low=False: dict({"k": k, "label": lab, "dp": dp}, **({"low": True} if low else {}))
    return {
        "league": "MLS", "season": "2025 regular season", "unit": "goals",
        "source": {"label": "Stats Crew MLS 2025 team pages", "url": "https://www.statscrew.com/soccer/l-MLS/y-2025"},
        "teamSort": "Pts",
        "teamCols": [C("Pts", "PTS"), C("W", "W"), C("L", "L"), C("D", "D"), C("PF", "GF"), C("PA", "GA"),
                     C("DIFF", "GD"), C("GFG", "GF/G", 2), C("GAG", "GA/G", 2)],
        "teams": teams,
        "groups": [
            {"id": "field", "label": "Field players", "sortDefault": "G", "minKey": "GP", "minLabel": "Min games",
             "minOpts": [0, 5, 10, 20], "minDefault": 10, "shareKey": "G", "shareLabel": "Share of team goals",
             "cols": [C("GP", "GP"), C("GS", "GS"), C("G", "G"), C("A", "A"), C("GA_", "G+A"), C("Shts", "SHOTS"),
                      C("SOG", "SOG"), C("SPct", "G/SH%", 1), C("SOGPct", "SOG%", 1), C("FC", "FOULS", 0, True),
                      C("FS", "FOULED"), C("OFF", "OFFSIDE", 0, True), C("Y", "YC", 0, True), C("R", "RC", 0, True)],
             "rows": field},
            {"id": "keepers", "label": "Goalkeepers", "sortDefault": "SVS", "minKey": "GP", "minLabel": "Min games",
             "minOpts": [0, 5, 10, 20], "minDefault": 5,
             "cols": [C("GP", "GP"), C("GS", "GS"), C("Min", "MIN"), C("SHO", "CS"), C("GA", "GA", 0, True),
                      C("GAA", "GAA", 2, True), C("Shts", "SOG FACED"), C("SVS", "SAVES"), C("SVPct", "SV%", 1)],
             "rows": gk},
        ],
    }


BUILDERS = {"nba": build_nba, "nhl": build_nhl, "mlb": build_mlb, "nfl": build_nfl, "mls": build_mls}

def finalize(data):
    for c in data["teamCols"]:
        if c["k"] in ("PA", "GAG", "L", "OTL", "RAG", "PAG"):
            c["low"] = True
    for t in data["teams"]:
        if t.get("PF") is not None and t.get("PA") is not None:
            t["DIFF"] = round(t["PF"] - t["PA"], 2)
    return data


if __name__ == "__main__":
    which = sys.argv[1:] or list(BUILDERS)
    for lg in which:
        data = finalize(BUILDERS[lg]())
        with open(os.path.join(OUT, f"{lg}.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
        n = sum(len(g["rows"]) for g in data["groups"])
        print(lg, len(data["teams"]), "teams", n, "player rows")
