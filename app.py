
from flask import Flask, jsonify, render_template, request
from datetime import datetime, timedelta, timezone
from itertools import combinations
import os
import math
import requests

app = Flask(__name__, template_folder="templates", static_folder="static")

KST = timezone(timedelta(hours=9))
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

MIN_START_MINUTES = int(os.getenv("MIN_START_MINUTES", "10"))
MAX_START_MINUTES = int(os.getenv("MAX_START_MINUTES", "720"))

SPORT_KEYS = {
    "football": [
        ("football", "soccer_epl"),
        ("football", "soccer_spain_la_liga"),
        ("football", "soccer_italy_serie_a"),
        ("football", "soccer_germany_bundesliga"),
        ("football", "soccer_france_ligue_one"),
        ("football", "soccer_usa_mls"),
    ],
    "baseball": [
        ("baseball", "baseball_mlb"),
    ],
    "basketball": [
        ("basketball", "basketball_nba"),
    ],
    "ice-hockey": [
        ("ice-hockey", "icehockey_nhl"),
    ],
}

BASEBALL_LEAGUE_ALLOW = {
    "baseball_mlb", "MLB", "KBO", "NPB", "CPBL", "LMB", "MiLB", "NCAA Baseball"
}
BASEBALL_BLOCK_WORDS = {
    "draw", "x", "1x2", "sidama", "welwalo", "adigrat", "bun", "arsenal", "chelsea",
    "valencia", "sevilla", "ethiopia", "premier", "liga", "serie", "bundesliga"
}


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def now_kst():
    return datetime.now(KST)


def start_in_minutes(starts_at):
    if not starts_at:
        return None
    try:
        start = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
        return int((start - datetime.now(timezone.utc)).total_seconds() // 60)
    except Exception:
        try:
            start = datetime.fromisoformat(str(starts_at))
            return int((start - now_kst()).total_seconds() // 60)
        except Exception:
            return None


def format_kst(starts_at):
    if not starts_at:
        return "-"
    try:
        dt = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%m/%d %H:%M")
    except Exception:
        return str(starts_at)


def valid_start_time(starts_at):
    mins = start_in_minutes(starts_at)
    return mins is not None and MIN_START_MINUTES <= mins <= MAX_START_MINUTES


def drop_rate(open_odds, current_odds):
    open_odds = safe_float(open_odds)
    current_odds = safe_float(current_odds)
    if open_odds <= 0 or current_odds <= 0:
        return 0
    return round(((open_odds - current_odds) / open_odds) * 100, 2)


def implied_probability(odds):
    odds = safe_float(odds)
    if odds <= 0:
        return 0
    return round((1 / odds) * 100, 2)


def market_average(values):
    nums = [safe_float(v) for v in values if safe_float(v) > 1]
    if not nums:
        return 0
    return round(sum(nums) / len(nums), 3)


def realistic_probability(score):
    score = safe_float(score)
    if score <= 0:
        return 0
    return min(0.72, max(0.45, score / 135))


def ev_percent(score, odds):
    odds = safe_float(odds)
    if odds <= 1 or score <= 0:
        return 0
    return round((realistic_probability(score) * odds - 1) * 100, 2)


def kelly_percent(score, odds):
    odds = safe_float(odds)
    if odds <= 1 or score <= 0:
        return 0
    p = realistic_probability(score)
    b = odds - 1
    k = ((b * p) - (1 - p)) / b
    return round(max(0, min(k * 100, 15)), 2)


def supported_sports(sport):
    if sport in ("all", "", None):
        keys = []
        for v in SPORT_KEYS.values():
            keys.extend(v)
        return keys
    return SPORT_KEYS.get(sport, [])


def classify_market_type(sport_name, market_key, outcome_count):
    key = str(market_key or "").lower()
    if sport_name == "baseball":
        if key == "h2h":
            return "Moneyline"
        if key == "spreads":
            return "Run Line"
        if key == "totals":
            return "Total"
    if sport_name == "football":
        if key == "h2h" and outcome_count >= 3:
            return "1X2"
        if key == "spreads":
            return "Handicap"
        if key == "totals":
            return "Total"
    if key == "h2h":
        return "Moneyline"
    return key or "-"


def exclusion_reason(game, market=None, requested_sport=None):
    sport = str(game.get("sport", "")).lower()
    league = str(game.get("league", ""))
    home = str(game.get("home", ""))
    away = str(game.get("away", ""))
    game_text = f"{sport} {league} {home} {away}".lower()

    if requested_sport and requested_sport not in ("all", sport):
        return f"선택 종목({requested_sport})과 실제 종목({sport}) 불일치"

    if sport == "baseball":
        if market:
            mtype = str(market.get("type", "")).lower()
            pick = str(market.get("pick", "")).lower()
            if mtype in ("1x2", "draw"):
                return "야구 탭인데 1X2/X 배당 존재"
            if pick in ("x", "draw", "무승부"):
                return "야구에는 무승부/X 마켓 없음"
        if any(w in game_text for w in BASEBALL_BLOCK_WORDS):
            return "야구가 아닌 팀명/리그명 감지"
        if "soccer" in league.lower() or "football" in league.lower():
            return "야구 탭에 축구 리그명 감지"

    return None


def clean_game_markets(game, requested_sport="all"):
    excluded = []
    reason = exclusion_reason(game, requested_sport=requested_sport)
    if reason:
        excluded.append({
            "game": f"{game.get('league')} {game.get('home')} vs {game.get('away')}",
            "sport": game.get("sport"),
            "league": game.get("league"),
            "reason": reason,
        })
        return None, excluded

    clean_markets = []
    for m in game.get("markets", []):
        r = exclusion_reason(game, m, requested_sport)
        if r:
            excluded.append({
                "game": f"{game.get('league')} {game.get('home')} vs {game.get('away')}",
                "pick": m.get("pick"),
                "type": m.get("type"),
                "sport": game.get("sport"),
                "league": game.get("league"),
                "reason": r,
            })
            continue
        clean_markets.append(m)

    if not clean_markets:
        excluded.append({
            "game": f"{game.get('league')} {game.get('home')} vs {game.get('away')}",
            "sport": game.get("sport"),
            "league": game.get("league"),
            "reason": "분석 가능한 정상 마켓 없음",
        })
        return None, excluded

    game = dict(game)
    game["markets"] = clean_markets
    return game, excluded


def demo_games(sport="all"):
    now = now_kst()
    games = [
        {
            "sport": "baseball", "league": "MLB", "country": "USA",
            "home": "LA Dodgers", "away": "Milwaukee Brewers",
            "starts_at": (now + timedelta(minutes=220)).isoformat(),
            "markets": [
                {"pick": "LA Dodgers", "type": "Moneyline", "odds": 1.82, "open_odds": 1.94, "pinnacle_odds": 1.80, "market_avg": 1.86, "bookmaker": "Pinnacle", "is_pinnacle": True},
                {"pick": "Milwaukee Brewers", "type": "Moneyline", "odds": 2.05, "open_odds": 1.96, "pinnacle_odds": 2.02, "market_avg": 2.00, "bookmaker": "Pinnacle", "is_pinnacle": True},
            ],
        },
        {
            "sport": "baseball", "league": "BROKEN Korea NPB", "country": "KR",
            "home": "Sidama Bunna", "away": "Welwalo Adigrat",
            "starts_at": (now + timedelta(minutes=240)).isoformat(),
            "markets": [
                {"pick": "Sidama Bunna", "type": "1X2", "odds": 1.82, "open_odds": 3.10, "pinnacle_odds": 1.82, "market_avg": 3.25, "bookmaker": "BadFeed"},
                {"pick": "X", "type": "1X2", "odds": 3.10, "open_odds": 3.10, "pinnacle_odds": 3.10, "market_avg": 3.25, "bookmaker": "BadFeed"},
            ],
        },
        {
            "sport": "football", "league": "EPL", "country": "UK",
            "home": "Arsenal", "away": "Chelsea",
            "starts_at": (now + timedelta(minutes=250)).isoformat(),
            "markets": [
                {"pick": "Arsenal", "type": "1X2", "odds": 1.78, "open_odds": 1.91, "pinnacle_odds": 1.74, "market_avg": 1.84, "bookmaker": "Pinnacle", "is_pinnacle": True},
                {"pick": "Draw", "type": "1X2", "odds": 3.45, "open_odds": 3.30, "pinnacle_odds": 3.42, "market_avg": 3.50, "bookmaker": "Bet365"},
            ],
        },
    ]
    if sport != "all":
        games = [g for g in games if g["sport"] == sport]
    return [g for g in games if valid_start_time(g.get("starts_at"))]


def fetch_odds_api_games(sport="all"):
    if not ODDS_API_KEY:
        return None

    games = []
    for sport_name, sport_key in supported_sports(sport):
        url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us,eu,uk",
            "markets": "h2h,spreads,totals",
            "oddsFormat": "decimal",
        }

        try:
            response = requests.get(url, params=params, timeout=12)
        except Exception:
            continue

        if response.status_code != 200:
            continue

        for item in response.json():
            starts_at = item.get("commence_time")
            if not valid_start_time(starts_at):
                continue

            raw_markets = []
            for bookmaker in item.get("bookmakers", []):
                book_title = bookmaker.get("title", "Unknown")
                is_pinnacle = "pinnacle" in book_title.lower()
                for market in bookmaker.get("markets", []):
                    outcomes = market.get("outcomes", []) or []
                    mtype = classify_market_type(sport_name, market.get("key"), len(outcomes))
                    for outcome in outcomes:
                        pick = outcome.get("name")
                        price = safe_float(outcome.get("price"))
                        if not pick or price <= 1:
                            continue
                        if sport_name == "baseball" and str(pick).lower() in ("draw", "x"):
                            continue
                        raw_markets.append({
                            "pick": pick,
                            "type": mtype,
                            "odds": price,
                            "bookmaker": book_title,
                            "is_pinnacle": is_pinnacle,
                            "market_key": market.get("key"),
                        })

            grouped = {}
            for row in raw_markets:
                key = (row["type"], row["pick"].lower().strip())
                if key not in grouped:
                    grouped[key] = {
                        "pick": row["pick"], "type": row["type"],
                        "all_odds": [], "pinnacle_odds": None,
                        "best_odds": row["odds"], "best_bookmaker": row["bookmaker"],
                        "bookmakers": [],
                    }
                g = grouped[key]
                g["all_odds"].append(row["odds"])
                g["bookmakers"].append({"bookmaker": row["bookmaker"], "odds": row["odds"]})
                if row["odds"] > g["best_odds"]:
                    g["best_odds"] = row["odds"]
                    g["best_bookmaker"] = row["bookmaker"]
                if row["is_pinnacle"]:
                    g["pinnacle_odds"] = row["odds"]

            markets = []
            for row in grouped.values():
                avg = market_average(row["all_odds"])
                current = safe_float(row["pinnacle_odds"]) or safe_float(row["best_odds"])
                open_proxy = round(avg * 1.025, 2) if avg else round(current * 1.025, 2)
                markets.append({
                    "pick": row["pick"],
                    "type": row["type"],
                    "odds": current,
                    "open_odds": open_proxy,
                    "pinnacle_odds": row["pinnacle_odds"],
                    "market_avg": avg,
                    "best_odds": row["best_odds"],
                    "bookmaker": "Pinnacle" if row["pinnacle_odds"] else row["best_bookmaker"],
                    "is_pinnacle": bool(row["pinnacle_odds"]),
                    "bookmakers": row["bookmakers"][:12],
                    "source": "odds_api_market_average",
                })

            if markets:
                games.append({
                    "sport": sport_name,
                    "sport_label": sport_name.upper(),
                    "league": sport_key,
                    "country": "API",
                    "home": item.get("home_team"),
                    "away": item.get("away_team"),
                    "starts_at": starts_at,
                    "start_in_minutes": start_in_minutes(starts_at),
                    "kst_time": format_kst(starts_at),
                    "markets": markets,
                })

    return games or None


def get_games(sport="all"):
    excluded = []
    try:
        live = fetch_odds_api_games(sport)
        source = "live"
        notice = f"실시간 Odds API 사용 / {MIN_START_MINUTES}~{MAX_START_MINUTES}분 경기만 분석"
    except Exception as e:
        print("Odds API error:", e)
        live = None

    games = live if live else demo_games(sport)
    if not live:
        source = "demo"
        notice = "실시간 API 실패 또는 키 없음. 데모 데이터 사용 중"

    cleaned = []
    for game in games:
        clean, ex = clean_game_markets(game, sport)
        excluded.extend(ex)
        if clean:
            clean["start_in_minutes"] = start_in_minutes(clean.get("starts_at"))
            clean["kst_time"] = format_kst(clean.get("starts_at"))
            cleaned.append(clean)

    return cleaned, excluded, source, notice


def pinnacle_bonus(market):
    return 10 if market.get("is_pinnacle") or "pinnacle" in str(market.get("bookmaker", "")).lower() else 0


def value_gap_component(odds, market_avg):
    odds = safe_float(odds)
    market_avg = safe_float(market_avg)
    if odds <= 1 or market_avg <= 1:
        return 0
    gap = ((odds - market_avg) / market_avg) * 100
    if gap >= 5:
        return 18
    if gap >= 3:
        return 13
    if gap >= 1.5:
        return 8
    if gap >= 0.5:
        return 4
    if gap <= -3:
        return -10
    return 0


def sharp_component(open_odds, current_odds, pinnacle_odds, market_avg, market):
    d = drop_rate(open_odds, current_odds)
    score = 0
    if d >= 6:
        score += 25
    elif d >= 4:
        score += 18
    elif d >= 2:
        score += 10
    elif d >= 0.8:
        score += 5

    current = safe_float(current_odds)
    pin = safe_float(pinnacle_odds)
    avg = safe_float(market_avg)

    if pin and avg and pin < avg:
        score += 16
    elif pin and avg and pin <= avg * 1.01:
        score += 8

    if pin and current and abs(pin - current) / current < 0.015:
        score += 6

    score += pinnacle_bonus(market)
    return max(0, min(45, round(score, 1)))


def steam_component(open_odds, current_odds):
    d = drop_rate(open_odds, current_odds)
    if d >= 8:
        return 22
    if d >= 5:
        return 16
    if d >= 3:
        return 10
    if d >= 1:
        return 4
    return 0


def clv_component(current_odds, pinnacle_odds, market_avg):
    current = safe_float(current_odds)
    pin = safe_float(pinnacle_odds)
    avg = safe_float(market_avg)
    score = 0
    if pin and avg and pin < avg:
        score += 12
    if current and avg and current >= avg:
        score += 8
    if pin and current and current >= pin:
        score += 6
    return min(24, score)


def reverse_line_component(open_odds, current_odds, market_avg):
    d = drop_rate(open_odds, current_odds)
    avg = safe_float(market_avg)
    current = safe_float(current_odds)
    if d >= 2 and avg and current <= avg:
        return 8
    if d >= 1 and avg and current <= avg * 1.01:
        return 4
    return 0


def risk_level(score, ev, kelly, d, ai_edge):
    if score >= 86 and ev >= 2 and kelly > 0 and d >= 1 and ai_edge >= 2:
        return "low"
    if score >= 76 and ev >= -1 and ai_edge >= -1:
        return "medium"
    return "high"


def confidence_score(score, ev, kelly, risk, ai_edge):
    confidence = safe_float(score)
    if ai_edge >= 8:
        confidence += 6
    elif ai_edge >= 4:
        confidence += 3
    elif ai_edge < 0:
        confidence -= 8
    if ev >= 8:
        confidence += 5
    elif ev >= 3:
        confidence += 2
    elif ev < -3:
        confidence -= 8
    if kelly >= 5:
        confidence += 3
    elif kelly <= 0:
        confidence -= 4
    if risk == "low":
        confidence += 4
    elif risk == "high":
        confidence -= 10
    return int(max(0, min(99, round(confidence))))


def recommendation_decision(confidence, ev, kelly, ai_edge, risk):
    if risk == "high" or ev < -3 or ai_edge < -2:
        return "NO_BET"
    if confidence >= 88 and ev >= 3 and kelly > 0 and ai_edge >= 3:
        return "BET"
    if confidence >= 76 and ev >= 0 and ai_edge >= 0:
        return "WATCH"
    return "NO_BET"


def recommendation_grade(confidence, decision):
    if decision == "NO_BET":
        return "No Bet"
    if confidence >= 92:
        return "★★★★★ 강추천"
    if confidence >= 85:
        return "★★★★ 추천"
    if confidence >= 76:
        return "★★★ 관찰"
    return "No Bet"


def reasons_for_pick(market, d, ev, sharp, steam, clv, value_gap, risk, confidence, ai_edge, decision):
    reasons = []
    if decision == "NO_BET":
        if ev < 0:
            reasons.append("EV 부족")
        if ai_edge < 0:
            reasons.append("AI Edge 부족")
        if risk == "high":
            reasons.append("위험도 높음")
        if sharp < 12:
            reasons.append("Sharp 신호 약함")
        return reasons or ["추천 근거 부족"]
    if market.get("is_pinnacle"):
        reasons.append("Pinnacle 기준 배당 사용")
    if d >= 3:
        reasons.append("초기 대비 배당 하락")
    elif d >= 1:
        reasons.append("배당 하락 감지")
    if sharp >= 25:
        reasons.append("Sharp Money 신호")
    if steam >= 10:
        reasons.append("Steam Move")
    if clv >= 14:
        reasons.append("CLV 기대")
    if value_gap >= 8:
        reasons.append("시장 평균 대비 가치")
    if ev >= 5:
        reasons.append("EV 우수")
    elif ev > 0:
        reasons.append("EV 양호")
    if ai_edge >= 5:
        reasons.append("AI Edge 우수")
    if risk == "low":
        reasons.append("위험도 낮음")
    if confidence >= 85:
        reasons.append("AI 신뢰도 높음")
    return reasons or ["관찰 필요"]


def ai_analysis_text(p):
    if p.get("decision") == "BET":
        return f"{p['pick']}은 시장 암시확률 {p['market_probability']}% 대비 AI 예상승률 {p['ai_probability']}%로 Edge {p['ai_edge']}%입니다. EV {p['ev']}%, Kelly {p['kelly']}%."
    if p.get("decision") == "WATCH":
        return f"{p['pick']}은 조건은 나쁘지 않지만 확신은 부족합니다. AI Edge {p['ai_edge']}%, EV {p['ev']}%."
    return f"{p['pick']}은 현재 No Bet입니다. AI Edge {p['ai_edge']}%, EV {p['ev']}%, 위험도 {p['risk']}."


def analyze_market(game, market):
    odds = safe_float(market.get("odds"))
    open_odds = safe_float(market.get("open_odds"))
    pinnacle_odds = safe_float(market.get("pinnacle_odds"))
    market_avg = safe_float(market.get("market_avg"))

    d = drop_rate(open_odds, odds)
    base = 38
    sharp = sharp_component(open_odds, odds, pinnacle_odds, market_avg, market)
    steam = steam_component(open_odds, odds)
    clv = clv_component(odds, pinnacle_odds, market_avg)
    value_gap = value_gap_component(odds, market_avg)
    reverse = reverse_line_component(open_odds, odds, market_avg)

    score = int(max(0, min(99, round(base + sharp + steam + clv + value_gap + reverse))))
    ai_prob = round(realistic_probability(score) * 100, 2)
    market_prob = implied_probability(odds)
    ai_edge = round(ai_prob - market_prob, 2)

    ev = ev_percent(score, odds)
    kelly = kelly_percent(score, odds)
    risk = risk_level(score, ev, kelly, d, ai_edge)
    confidence = confidence_score(score, ev, kelly, risk, ai_edge)
    decision = recommendation_decision(confidence, ev, kelly, ai_edge, risk)

    item = {
        "sport": game.get("sport"),
        "league": game.get("league"),
        "country": game.get("country", "-"),
        "game": f"{game.get('league')} {game.get('home')} vs {game.get('away')}",
        "home": game.get("home"),
        "away": game.get("away"),
        "starts_at": game.get("starts_at"),
        "start_in_minutes": game.get("start_in_minutes") or start_in_minutes(game.get("starts_at")),
        "kst_time": game.get("kst_time") or format_kst(game.get("starts_at")),
        "type": market.get("type"),
        "pick": market.get("pick"),
        "bookmaker": market.get("bookmaker"),
        "is_pinnacle": market.get("is_pinnacle", False),
        "odds": odds,
        "open_odds": open_odds,
        "pinnacle_odds": pinnacle_odds,
        "sharp_odds": pinnacle_odds,
        "market_avg": market_avg,
        "domestic_odds": market_avg,
        "best_odds": market.get("best_odds"),
        "drop_rate": d,
        "implied_probability": market_prob,
        "market_probability": market_prob,
        "ai_probability": ai_prob,
        "ai_edge": ai_edge,
        "score": score,
        "confidence": confidence,
        "ev": ev,
        "kelly": kelly,
        "sharp_score": sharp,
        "steam_score": steam,
        "clv_score": clv,
        "rlm_score": reverse,
        "value_score": value_gap,
        "risk": risk,
        "decision": decision,
        "grade": recommendation_grade(confidence, decision),
        "bookmakers": market.get("bookmakers", []),
    }
    item["reasons"] = reasons_for_pick(market, d, ev, sharp, steam, clv, value_gap, risk, confidence, ai_edge, decision)
    item["ai_analysis"] = ai_analysis_text(item)
    return item


def flatten_picks(games):
    picks = []
    for game in games or []:
        if not valid_start_time(game.get("starts_at")):
            continue
        for market in game.get("markets", []):
            if safe_float(market.get("odds")) > 1:
                picks.append(analyze_market(game, market))
    return sorted(picks, key=lambda p: (p["decision"] == "BET", p["confidence"], p["ev"], p["sharp_score"], p["value_score"]), reverse=True)


def make_combo(name, picks, size):
    candidates = picks[:14]
    best = None
    for combo in combinations(candidates, size):
        game_names = [p["game"] for p in combo]
        if len(set(game_names)) != len(game_names):
            continue
        total_odds = math.prod([safe_float(p["odds"], 1) for p in combo])
        avg_score = sum(p["score"] for p in combo) / size
        avg_confidence = sum(p["confidence"] for p in combo) / size
        avg_ev = sum(p["ev"] for p in combo) / size
        avg_kelly = sum(p["kelly"] for p in combo) / size
        avg_edge = sum(p["ai_edge"] for p in combo) / size
        item = {
            "type": name,
            "folder_size": size,
            "total_odds": round(total_odds, 2),
            "avg_score": round(avg_score, 1),
            "avg_confidence": round(avg_confidence, 1),
            "avg_ev": round(avg_ev, 2),
            "avg_kelly": round(avg_kelly, 2),
            "avg_edge": round(avg_edge, 2),
            "picks": list(combo),
        }
        rank = (item["avg_confidence"], item["avg_edge"], item["avg_ev"], item["avg_score"])
        if best is None or rank > (best["avg_confidence"], best["avg_edge"], best["avg_ev"], best["avg_score"]):
            best = item
    return best


def build_recommendations(games):
    picks = flatten_picks(games)
    bet = [p for p in picks if p["decision"] == "BET"]
    watch = [p for p in picks if p["decision"] in ["BET", "WATCH"]]
    combos = []
    for size in [2, 3, 4, 5, 6]:
        if len(bet) >= size:
            combos.append(make_combo(f"실전형 {size}폴더", bet, size))
        if len(watch) >= size:
            combos.append(make_combo(f"관찰형 {size}폴더", watch, size))
    combos = [c for c in combos if c]
    combos = sorted(combos, key=lambda c: (c["avg_confidence"], c["avg_edge"], c["avg_ev"]), reverse=True)
    return combos[:10], picks, len(combos) == 0


def build_summary(picks, combos, no_bet, excluded_count=0):
    if not picks:
        return {
            "total_picks": 0,
            "top_score": 0,
            "top_confidence": 0,
            "avg_ev": 0,
            "avg_edge": 0,
            "recommendation_count": 0,
            "excluded_count": excluded_count,
            "no_bet": True,
            "message": "분석 가능한 정상 경기가 없습니다.",
            "time_filter": f"{MIN_START_MINUTES}~{MAX_START_MINUTES}분",
        }
    return {
        "total_picks": len(picks),
        "bet_count": len([p for p in picks if p["decision"] == "BET"]),
        "watch_count": len([p for p in picks if p["decision"] == "WATCH"]),
        "no_bet_count": len([p for p in picks if p["decision"] == "NO_BET"]),
        "excluded_count": excluded_count,
        "top_score": max(p["score"] for p in picks),
        "top_confidence": max(p["confidence"] for p in picks),
        "avg_ev": round(sum(p["ev"] for p in picks) / len(picks), 2),
        "avg_edge": round(sum(p["ai_edge"] for p in picks) / len(picks), 2),
        "recommendation_count": len(combos),
        "no_bet": no_bet,
        "message": "추천 가능" if not no_bet else "오늘은 무리한 배팅보다 관망을 추천합니다.",
        "time_filter": f"{MIN_START_MINUTES}~{MAX_START_MINUTES}분",
    }



@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "odds-ai-v20"})

@app.route("/")
def index():
    return render_template("index.html")



@app.route("/<path:path>")
def catch_all(path):
    # Render나 브라우저가 잘못된 경로로 접근해도 메인 화면을 보여줌
    return render_template("index.html")

@app.route("/api/live-games")
def live_games():
    sport = request.args.get("sport", "all")
    games, excluded, mode, notice = get_games(sport)
    return jsonify({
        "mode": mode,
        "notice": notice,
        "count": len(games),
        "excluded_count": len(excluded),
        "games": games,
        "excluded": excluded[:30],
    })


@app.route("/api/recommendations")
def recommendations():
    sport = request.args.get("sport", "all")
    games, excluded, mode, notice = get_games(sport)
    combos, picks, no_bet = build_recommendations(games)
    return jsonify({
        "mode": mode,
        "notice": notice,
        "summary": build_summary(picks, combos, no_bet, len(excluded)),
        "combos": combos,
        "recommendations": combos,
        "top_picks": picks[:10],
        "excluded": excluded[:30],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=True)
