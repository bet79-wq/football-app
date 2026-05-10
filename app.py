import streamlit as st
import requests
import pandas as pd
import math
import os

API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

headers = {"x-apisports-key": API_KEY}

MIN_PROB = 0.45
MIN_EDGE = 0.00
MIN_PRESSURE = 8
MIN_MOMENTUM = 1

MIN_MINUTE = 55
MAX_MINUTE = 85

ALERTS_FILE = "alerts_sent.csv"
LIVE_STATS_FILE = "live_stats.csv"

st.set_page_config(page_title="Momentum Goal Scanner", layout="wide")
st.title("⚽ Live Momentum Goal Scanner")
st.caption("Shows all in-play games, pressure, momentum, and qualifying alerts.")

st.markdown("""<meta http-equiv="refresh" content="120">""", unsafe_allow_html=True)

if not os.path.exists(ALERTS_FILE):
    pd.DataFrame(columns=["Fixture ID"]).to_csv(ALERTS_FILE, index=False)

if not os.path.exists(LIVE_STATS_FILE):
    pd.DataFrame(columns=[
        "fixture_id", "minute", "shots", "sot", "corners", "attacks"
    ]).to_csv(LIVE_STATS_FILE, index=False)

def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def probability_over_0_5(lmbda):
    return 1 - poisson_prob(lmbda, 0)

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

def already_alerted(fixture_id):
    alerts = pd.read_csv(ALERTS_FILE)
    return not alerts[alerts["Fixture ID"] == fixture_id].empty

def save_alert(fixture_id):
    alerts = pd.read_csv(ALERTS_FILE)
    new_row = {"Fixture ID": fixture_id}
    alerts = pd.concat([alerts, pd.DataFrame([new_row])], ignore_index=True)
    alerts.to_csv(ALERTS_FILE, index=False)

def get_live_fixtures():
    url = "https://v3.football.api-sports.io/fixtures?live=all"
    try:
        return requests.get(url, headers=headers).json().get("response", [])
    except:
        return []

def get_fixture_stats(fixture_id):
    url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture_id}"
    try:
        return requests.get(url, headers=headers).json().get("response", [])
    except:
        return []

def extract_stat(stats, stat_name):
    try:
        for stat in stats:
            if stat["type"] == stat_name:
                return stat["value"] or 0
    except:
        pass
    return 0

def calculate_game_state(match):
    fixture_id = match["fixture"]["id"]

    home_team = match["teams"]["home"]["name"]
    away_team = match["teams"]["away"]["name"]

    elapsed = match["fixture"]["status"]["elapsed"]

    if elapsed is None:
        elapsed = 0

    stats = get_fixture_stats(fixture_id)

    if len(stats) < 2:
        return None

    home_live = stats[0]["statistics"]
    away_live = stats[1]["statistics"]

    home_shots = extract_stat(home_live, "Total Shots")
    away_shots = extract_stat(away_live, "Total Shots")

    home_sot = extract_stat(home_live, "Shots on Goal")
    away_sot = extract_stat(away_live, "Shots on Goal")

    home_corners = extract_stat(home_live, "Corner Kicks")
    away_corners = extract_stat(away_live, "Corner Kicks")

    home_attacks = extract_stat(home_live, "Dangerous Attacks")
    away_attacks = extract_stat(away_live, "Dangerous Attacks")

    total_shots = home_shots + away_shots
    total_sot = home_sot + away_sot
    total_corners = home_corners + away_corners
    total_attacks = home_attacks + away_attacks

    home_goals = match["goals"]["home"] or 0
    away_goals = match["goals"]["away"] or 0

    total_goals = home_goals + away_goals
    goal_difference = abs(home_goals - away_goals)

    pressure = (
        total_shots * 0.45 +
        total_sot * 1.5 +
        total_corners * 0.5 +
        total_attacks * 0.05
    )

    if total_goals == 0:
        pressure += 6
    elif total_goals == 1:
        pressure += 4
    elif total_goals == 2:
        pressure += 2

    live_stats = pd.read_csv(LIVE_STATS_FILE)

    previous = live_stats[live_stats["fixture_id"] == fixture_id]

    momentum = 0

    if len(previous) > 0:
        last = previous.iloc[-1]

        shots_momentum = total_shots - last["shots"]
        sot_momentum = total_sot - last["sot"]
        corners_momentum = total_corners - last["corners"]
        attacks_momentum = total_attacks - last["attacks"]

        momentum = (
            shots_momentum * 1.0 +
            sot_momentum * 2.0 +
            corners_momentum * 1.5 +
            attacks_momentum * 0.05
        )

    new_row = {
        "fixture_id": fixture_id,
        "minute": elapsed,
        "shots": total_shots,
        "sot": total_sot,
        "corners": total_corners,
        "attacks": total_attacks
    }

    live_stats = pd.concat([live_stats, pd.DataFrame([new_row])], ignore_index=True)
    live_stats.to_csv(LIVE_STATS_FILE, index=False)

    second_half_xg = 1.15 + (pressure / 20) + (momentum / 10)

    if elapsed > 75:
        second_half_xg *= 0.85

    if elapsed > 82:
        second_half_xg *= 0.70

    prob_goal = probability_over_0_5(second_half_xg)

    market_odds = (1 / prob_goal) * 1.03
    implied = 1 / market_odds
    edge = prob_goal - implied

    in_entry_window = MIN_MINUTE <= elapsed <= MAX_MINUTE

    game_state_ok = (
        total_goals < 5 and
        goal_difference < 3
    )

    qualifies = (
        in_entry_window and
        game_state_ok and
        prob_goal >= MIN_PROB and
        edge >= MIN_EDGE and
        pressure >= MIN_PRESSURE and
        momentum >= MIN_MOMENTUM
    )

    if not in_entry_window:
        reason = "Outside minute window"
    elif not game_state_ok:
        reason = "Bad score state"
    elif pressure < MIN_PRESSURE:
        reason = "Pressure too low"
    elif momentum < MIN_MOMENTUM:
        reason = "Momentum too low"
    elif prob_goal < MIN_PROB:
        reason = "Probability too low"
    else:
        reason = "Qualifies"

    return {
        "fixture_id": fixture_id,
        "match": f"{home_team} vs {away_team}",
        "minute": elapsed,
        "score": f"{home_goals}-{away_goals}",
        "pressure": pressure,
        "momentum": momentum,
        "shots": total_shots,
        "sot": total_sot,
        "corners": total_corners,
        "attacks": total_attacks,
        "second_half_xg": second_half_xg,
        "prob_goal": prob_goal,
        "market_odds": market_odds,
        "edge": edge,
        "qualifies": qualifies,
        "reason": reason
    }

st.header("👀 Live In-Play Watchlist")

live_matches = get_live_fixtures()

watchlist = []
alerts = []

for match in live_matches:
    try:
        model = calculate_game_state(match)

        if model is None:
            continue

        watchlist.append({
            "Match": model["match"],
            "Minute": model["minute"],
            "Score": model["score"],
            "Pressure": round(model["pressure"], 1),
            "Momentum": round(model["momentum"], 1),
            "Shots": model["shots"],
            "SOT": model["sot"],
            "Corners": model["corners"],
            "Attacks": model["attacks"],
            "2H xG": round(model["second_half_xg"], 2),
            "Goal %": f"{model['prob_goal']*100:.1f}%",
            "Reason": model["reason"]
        })

        if model["qualifies"]:
            alerts.append(model)

            if not already_alerted(model["fixture_id"]):
                message = f"""
🔥 LIVE MOMENTUM BET

{model['match']}

Minute: {model['minute']}
Score: {model['score']}

Pressure: {model['pressure']:.1f}
Momentum: {model['momentum']:.1f}

Shots: {model['shots']}
SOT: {model['sot']}
Corners: {model['corners']}

2H xG: {model['second_half_xg']:.2f}
Goal Probability: {model['prob_goal']*100:.1f}%

✅ OVER 0.5 SECOND HALF GOAL
"""
                send_telegram_message(message)
                save_alert(model["fixture_id"])

    except:
        continue

if watchlist:
    watchlist_df = pd.DataFrame(watchlist)

    st.dataframe(
        watchlist_df.sort_values(
            by=["Momentum", "Pressure"],
            ascending=False
        ),
        use_container_width=True
    )
else:
    st.warning("No live games with available stats right now.")

st.header("🔥 Qualifying Alerts")

if alerts:
    alert_rows = []

    for model in alerts:
        alert_rows.append({
            "Match": model["match"],
            "Minute": model["minute"],
            "Score": model["score"],
            "Pressure": round(model["pressure"], 1),
            "Momentum": round(model["momentum"], 1),
            "Goal %": f"{model['prob_goal']*100:.1f}%",
            "Decision": "✅ BET"
        })

    st.success(f"{len(alert_rows)} qualifying opportunities found")
    st.dataframe(pd.DataFrame(alert_rows), use_container_width=True)
else:
    st.warning("No games currently qualify, but watchlist above shows what is close.")
