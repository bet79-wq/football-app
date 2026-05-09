import streamlit as st
import requests
import pandas as pd
import math
import os

# =========================================
# SETTINGS / SECRETS
# =========================================

API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

headers = {
    "x-apisports-key": API_KEY
}

LEAGUE_AVG_2H_GOALS = 1.25

MIN_PROB = 0.58
MIN_EDGE = 0.05
MIN_PRESSURE = 18

ALERTS_FILE = "alerts_sent.csv"

# =========================================
# PAGE
# =========================================

st.set_page_config(
    page_title="2H Goal Alert System",
    layout="wide"
)

st.title("⚽ Automated Second Half Goal Scanner")

st.caption(
    "Scans live football matches, detects second-half goal value and sends Telegram alerts automatically."
)

st.markdown(
    """
    <meta http-equiv="refresh" content="120">
    """,
    unsafe_allow_html=True
)

# =========================================
# ALERT FILE
# =========================================

if not os.path.exists(ALERTS_FILE):
    pd.DataFrame(columns=["Fixture ID"]).to_csv(ALERTS_FILE, index=False)

# =========================================
# FUNCTIONS
# =========================================

def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def probability_over_0_5(lmbda):
    return 1 - poisson_prob(lmbda, 0)

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=payload)

def already_alerted(fixture_id):
    alerts = pd.read_csv(ALERTS_FILE)
    existing = alerts[alerts["Fixture ID"] == fixture_id]
    return not existing.empty

def save_alert(fixture_id):
    alerts = pd.read_csv(ALERTS_FILE)

    new_row = {
        "Fixture ID": fixture_id
    }

    alerts = pd.concat(
        [alerts, pd.DataFrame([new_row])],
        ignore_index=True
    )

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

def get_team_stats(team_id):
    url = f"https://v3.football.api-sports.io/teams/statistics?team={team_id}&season=2023"

    try:
        return requests.get(url, headers=headers).json()["response"]
    except:
        return None

def extract_stat(stats, stat_name):
    try:
        for stat in stats:
            if stat["type"] == stat_name:
                return stat["value"] or 0
    except:
        pass

    return 0

# =========================================
# SECOND HALF LIVE MODEL
# =========================================

def calculate_second_half_model(match):
    fixture_id = match["fixture"]["id"]

    home_team = match["teams"]["home"]["name"]
    away_team = match["teams"]["away"]["name"]

    home_id = match["teams"]["home"]["id"]
    away_id = match["teams"]["away"]["id"]

    elapsed = match["fixture"]["status"]["elapsed"]

    if elapsed is None or elapsed < 46:
        return None

    home_stats = get_team_stats(home_id)
    away_stats = get_team_stats(away_id)

    if not home_stats or not away_stats:
        return None

    try:
        home_2h_scored = float(
            home_stats["goals"]["for"]["minute"]["76-90"]["percentage"].replace("%", "")
        ) / 100
    except:
        home_2h_scored = 0.3

    try:
        away_2h_scored = float(
            away_stats["goals"]["for"]["minute"]["76-90"]["percentage"].replace("%", "")
        ) / 100
    except:
        away_2h_scored = 0.3

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

    home_goals = match["goals"]["home"] or 0
    away_goals = match["goals"]["away"] or 0
    total_goals = home_goals + away_goals

    pressure = (
        (home_shots + away_shots) * 0.4 +
        (home_sot + away_sot) * 1.3 +
        (home_corners + away_corners) * 0.5 +
        (home_attacks + away_attacks) * 0.05
    )

    if total_goals == 0:
        pressure += 4
    elif total_goals == 1:
        pressure += 2

    second_half_xg = (
        LEAGUE_AVG_2H_GOALS +
        (pressure / 20) +
        (home_2h_scored * 0.5) +
        (away_2h_scored * 0.5)
    )

    if elapsed > 75:
        second_half_xg *= 0.8

    if elapsed > 85:
        second_half_xg *= 0.6

    prob_goal = probability_over_0_5(second_half_xg)

    market_odds = (1 / prob_goal) * 1.05
    implied = 1 / market_odds
    edge = prob_goal - implied

    return {
        "fixture_id": fixture_id,
        "match": f"{home_team} vs {away_team}",
        "minute": elapsed,
        "pressure": pressure,
        "second_half_xg": second_half_xg,
        "prob_goal": prob_goal,
        "market_odds": market_odds,
        "edge": edge
    }

# =========================================
# LIVE SCAN
# =========================================

st.header("🔥 Live Second Half Goal Opportunities")

live_matches = get_live_fixtures()
live_picks = []

for match in live_matches:
    try:
        model = calculate_second_half_model(match)

        if model is None:
            continue

        qualifies = (
            model["prob_goal"] >= MIN_PROB and
            model["edge"] >= MIN_EDGE and
            model["pressure"] >= MIN_PRESSURE
        )

        if qualifies:
            live_picks.append({
                "Match": model["match"],
                "Minute": model["minute"],
                "Pressure": round(model["pressure"], 1),
                "2H xG": round(model["second_half_xg"], 2),
                "Goal Probability": f"{model['prob_goal']*100:.1f}%",
                "Odds": round(model["market_odds"], 2),
                "Edge": f"{model['edge']*100:.1f}%",
                "Decision": "✅ BET"
            })

            if not already_alerted(model["fixture_id"]):
                message = f"""
🔥 SECOND HALF VALUE BET

{model['match']}

Minute: {model['minute']}
Pressure: {model['pressure']:.1f}
2H xG: {model['second_half_xg']:.2f}
Goal Probability: {model['prob_goal']*100:.1f}%
Odds: {model['market_odds']:.2f}
Edge: {model['edge']*100:.1f}%

✅ OVER 0.5 SECOND HALF GOAL
"""

                send_telegram_message(message)
                save_alert(model["fixture_id"])

    except:
        continue

if live_picks:
    st.success(f"{len(live_picks)} live bets found")
    st.dataframe(pd.DataFrame(live_picks))
else:
    st.warning("No second-half opportunities currently qualify")

# =========================================
# SIMPLE BACKTESTING WITH API DEBUG
# =========================================

st.header("📈 Historical Second Half Backtesting")

st.write(
    "This simplified backtest checks whether historical goal-heavy games would have produced second-half goal wins. "
    "It is not using real historical live odds yet."
)

league_id = st.number_input(
    "League ID",
    value=39
)

season = st.number_input(
    "Season",
    value=2023
)

max_matches = st.number_input(
    "Max matches",
    value=200,
    min_value=20,
    max_value=1000
)

if st.button("Run Backtest"):

    st.write("Running backtest...")

    historical_url = (
        f"https://v3.football.api-sports.io/fixtures?"
        f"league={league_id}&"
        f"season={season}&"
        f"status=FT"
    )

    raw_response = requests.get(
        historical_url,
        headers=headers
    ).json()

    st.write("API errors:", raw_response.get("errors"))
    st.write("API results count:", raw_response.get("results"))

    matches = raw_response.get("response", [])

    st.write(f"Matches returned from API: {len(matches)}")

    if len(matches) == 0:
        st.warning(
            "The API returned 0 matches. Try Season 2024 or 2025, or your API plan may not include this historical season."
        )

    total_bets = 0
    wins = 0
    losses = 0
    total_profit = 0

    rows = []

    for match in matches[:int(max_matches)]:

        try:
            home_team = match["teams"]["home"]["name"]
            away_team = match["teams"]["away"]["name"]

            home_goals = match["goals"]["home"] or 0
            away_goals = match["goals"]["away"] or 0

            total_goals = home_goals + away_goals

            qualifies = total_goals >= 2

            if qualifies:

                total_bets += 1
                stake = 1
                odds = 1.70

                if total_goals >= 3:
                    profit = stake * (odds - 1)
                    wins += 1
                else:
                    profit = -stake
                    losses += 1

                total_profit += profit

                rows.append({
                    "Match": f"{home_team} vs {away_team}",
                    "Goals": total_goals,
                    "Odds": odds,
                    "Profit": round(profit, 2)
                })

        except:
            continue

    if total_bets > 0:

        roi = (total_profit / total_bets) * 100
        strike_rate = (wins / total_bets) * 100

        st.subheader("📊 Backtest Results")

        st.write(f"Total Bets: {total_bets}")
        st.write(f"Wins: {wins}")
        st.write(f"Losses: {losses}")
        st.write(f"Strike Rate: {strike_rate:.1f}%")
        st.write(f"Profit: {total_profit:.2f} units")
        st.write(f"ROI: {roi:.2f}%")

        st.dataframe(pd.DataFrame(rows))

    else:
        st.warning("No bets found")
