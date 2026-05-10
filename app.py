import streamlit as st
import requests
import pandas as pd
import math
import os

# =========================================
# SETTINGS
# =========================================

API_KEY = os.getenv("API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

headers = {
    "x-apisports-key": API_KEY
}

# =========================================
# LIVE FILTERS
# =========================================

MIN_PROB = 0.50
MIN_EDGE = 0.00
MIN_PRESSURE = 10
MIN_MOMENTUM = 3

MIN_MINUTE = 55
MAX_MINUTE = 85

ALERTS_FILE = "alerts_sent.csv"
LIVE_STATS_FILE = "live_stats.csv"

# =========================================
# PAGE
# =========================================

st.set_page_config(
    page_title="Momentum Goal Scanner",
    layout="wide"
)

st.title("⚽ Live Momentum Goal Scanner")

st.caption(
    "Second-half momentum betting system with Telegram alerts and CSV backtesting."
)

# =========================================
# AUTO REFRESH
# =========================================

st.markdown(
    """
    <meta http-equiv="refresh" content="120">
    """,
    unsafe_allow_html=True
)

# =========================================
# FILE SETUP
# =========================================

if not os.path.exists(ALERTS_FILE):

    pd.DataFrame(columns=[
        "Fixture ID"
    ]).to_csv(ALERTS_FILE, index=False)

if not os.path.exists(LIVE_STATS_FILE):

    pd.DataFrame(columns=[
        "fixture_id",
        "minute",
        "shots",
        "sot",
        "corners",
        "attacks"
    ]).to_csv(LIVE_STATS_FILE, index=False)

# =========================================
# FUNCTIONS
# =========================================

def poisson_prob(lmbda, k):

    return (
        math.exp(-lmbda) *
        (lmbda ** k)
    ) / math.factorial(k)

def probability_over_0_5(lmbda):

    return 1 - poisson_prob(lmbda, 0)

# =========================================
# TELEGRAM
# =========================================

def send_telegram_message(message):

    if not BOT_TOKEN or not CHAT_ID:
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=payload)

# =========================================
# ALERT TRACKING
# =========================================

def already_alerted(fixture_id):

    alerts = pd.read_csv(ALERTS_FILE)

    existing = alerts[
        alerts["Fixture ID"] == fixture_id
    ]

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

# =========================================
# API FUNCTIONS
# =========================================

def get_live_fixtures():

    url = (
        "https://v3.football.api-sports.io/"
        "fixtures?live=all"
    )

    try:

        return requests.get(
            url,
            headers=headers
        ).json().get("response", [])

    except:

        return []

def get_fixture_stats(fixture_id):

    url = (
        f"https://v3.football.api-sports.io/"
        f"fixtures/statistics?"
        f"fixture={fixture_id}"
    )

    try:

        return requests.get(
            url,
            headers=headers
        ).json().get("response", [])

    except:

        return []

def get_team_stats(team_id):

    url = (
        f"https://v3.football.api-sports.io/"
        f"teams/statistics?"
        f"team={team_id}&season=2023"
    )

    try:

        return requests.get(
            url,
            headers=headers
        ).json()["response"]

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
# LIVE MODEL
# =========================================

def calculate_second_half_model(match):

    fixture_id = match["fixture"]["id"]

    home_team = match["teams"]["home"]["name"]
    away_team = match["teams"]["away"]["name"]

    home_id = match["teams"]["home"]["id"]
    away_id = match["teams"]["away"]["id"]

    elapsed = match["fixture"]["status"]["elapsed"]

    if elapsed is None:
        return None

    # =========================================
    # ENTRY WINDOW
    # =========================================

    if elapsed < MIN_MINUTE:
        return None

    if elapsed > MAX_MINUTE:
        return None

    # =========================================
    # TEAM STATS
    # =========================================

    home_stats = get_team_stats(home_id)
    away_stats = get_team_stats(away_id)

    if not home_stats or not away_stats:
        return None

    # =========================================
    # LIVE MATCH STATS
    # =========================================

    stats = get_fixture_stats(fixture_id)

    if len(stats) < 2:
        return None

    home_live = stats[0]["statistics"]
    away_live = stats[1]["statistics"]

    home_shots = extract_stat(
        home_live,
        "Total Shots"
    )

    away_shots = extract_stat(
        away_live,
        "Total Shots"
    )

    home_sot = extract_stat(
        home_live,
        "Shots on Goal"
    )

    away_sot = extract_stat(
        away_live,
        "Shots on Goal"
    )

    home_corners = extract_stat(
        home_live,
        "Corner Kicks"
    )

    away_corners = extract_stat(
        away_live,
        "Corner Kicks"
    )

    home_attacks = extract_stat(
        home_live,
        "Dangerous Attacks"
    )

    away_attacks = extract_stat(
        away_live,
        "Dangerous Attacks"
    )

    total_shots = (
        home_shots +
        away_shots
    )

    total_sot = (
        home_sot +
        away_sot
    )

    total_corners = (
        home_corners +
        away_corners
    )

    total_attacks = (
        home_attacks +
        away_attacks
    )

    # =========================================
    # SCORE STATE
    # =========================================

    home_goals = match["goals"]["home"] or 0
    away_goals = match["goals"]["away"] or 0

    total_goals = (
        home_goals +
        away_goals
    )

    goal_difference = abs(
        home_goals - away_goals
    )

    # =========================================
    # FILTERS
    # =========================================

    if total_goals >= 5:
        return None

    if goal_difference >= 3:
        return None

    # =========================================
    # PRESSURE MODEL
    # =========================================

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

    # =========================================
    # MOMENTUM ENGINE
    # =========================================

    live_stats = pd.read_csv(
        LIVE_STATS_FILE
    )

    previous = live_stats[
        live_stats["fixture_id"] == fixture_id
    ]

    momentum = 0

    if len(previous) > 0:

        last = previous.iloc[-1]

        shots_momentum = (
            total_shots -
            last["shots"]
        )

        sot_momentum = (
            total_sot -
            last["sot"]
        )

        corners_momentum = (
            total_corners -
            last["corners"]
        )

        attacks_momentum = (
            total_attacks -
            last["attacks"]
        )

        momentum = (
            shots_momentum * 1.0 +
            sot_momentum * 2.0 +
            corners_momentum * 1.5 +
            attacks_momentum * 0.05
        )

    # =========================================
    # SAVE CURRENT SNAPSHOT
    # =========================================

    new_row = {
        "fixture_id": fixture_id,
        "minute": elapsed,
        "shots": total_shots,
        "sot": total_sot,
        "corners": total_corners,
        "attacks": total_attacks
    }

    live_stats = pd.concat(
        [live_stats, pd.DataFrame([new_row])],
        ignore_index=True
    )

    live_stats.to_csv(
        LIVE_STATS_FILE,
        index=False
    )

    # =========================================
    # TEAM ATTACK STRENGTH
    # =========================================

    try:

        home_late_goals = float(
            home_stats["goals"]["for"]["minute"]["76-90"]["percentage"]
            .replace("%", "")
        ) / 100

    except:

        home_late_goals = 0.3

    try:

        away_late_goals = float(
            away_stats["goals"]["for"]["minute"]["76-90"]["percentage"]
            .replace("%", "")
        ) / 100

    except:

        away_late_goals = 0.3

    # =========================================
    # SECOND HALF XG
    # =========================================

    second_half_xg = (
        1.15 +
        (pressure / 20) +
        (momentum / 10) +
        (home_late_goals * 0.5) +
        (away_late_goals * 0.5)
    )

    # Time decay

    if elapsed > 75:
        second_half_xg *= 0.85

    if elapsed > 82:
        second_half_xg *= 0.70

    # =========================================
    # PROBABILITY
    # =========================================

    prob_goal = probability_over_0_5(
        second_half_xg
    )

    market_odds = (
        1 / prob_goal
    ) * 1.03

    implied = 1 / market_odds

    edge = prob_goal - implied

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
        "second_half_xg": second_half_xg,
        "prob_goal": prob_goal,
        "market_odds": market_odds,
        "edge": edge
    }

# =========================================
# LIVE PICKS
# =========================================

st.header("🔥 Live Momentum Opportunities")

live_matches = get_live_fixtures()

live_picks = []

for match in live_matches:

    try:

        model = calculate_second_half_model(match)

        if model is None:
            continue

        # DEBUG OUTPUT

        st.write(
            f"{model['match']} | "
            f"Min {model['minute']} | "
            f"Pressure {model['pressure']:.1f} | "
            f"Momentum {model['momentum']:.1f} | "
            f"Prob {model['prob_goal']:.2f}"
        )

        qualifies = (
            model["prob_goal"] >= MIN_PROB and
            model["edge"] >= MIN_EDGE and
            model["pressure"] >= MIN_PRESSURE and
            model["momentum"] >= MIN_MOMENTUM
        )

        if qualifies:

            live_picks.append({
                "Match": model["match"],
                "Minute": model["minute"],
                "Score": model["score"],
                "Pressure": round(model["pressure"], 1),
                "Momentum": round(model["momentum"], 1),
                "Shots": model["shots"],
                "SOT": model["sot"],
                "Corners": model["corners"],
                "2H xG": round(model["second_half_xg"], 2),
                "Goal Probability": f"{model['prob_goal']*100:.1f}%",
                "Odds": round(model["market_odds"], 2),
                "Decision": "✅ BET"
            })

            # =========================================
            # TELEGRAM ALERT
            # =========================================

            if not already_alerted(
                model["fixture_id"]
            ):

                message = f"""
🔥 LIVE MOMENTUM BET

{model['match']}

Minute:
{model['minute']}

Score:
{model['score']}

Pressure:
{model['pressure']:.1f}

Momentum:
{model['momentum']:.1f}

Shots:
{model['shots']}

Shots On Target:
{model['sot']}

Corners:
{model['corners']}

2H xG:
{model['second_half_xg']:.2f}

Goal Probability:
{model['prob_goal']*100:.1f}%

Odds:
{model['market_odds']:.2f}

✅ OVER 0.5 SECOND HALF GOAL
"""

                send_telegram_message(
                    message
                )

                save_alert(
                    model["fixture_id"]
                )

    except:
        continue

# =========================================
# DISPLAY PICKS
# =========================================

if live_picks:

    st.success(
        f"{len(live_picks)} live opportunities found"
    )

    st.dataframe(
        pd.DataFrame(live_picks)
    )

else:

    st.warning(
        "No momentum opportunities currently qualify."
    )

# =========================================
# CSV BACKTESTING
# =========================================

st.header("📈 CSV Historical Backtesting")

csv_files = [
    file for file in os.listdir()
    if file.endswith(".csv") and file != ALERTS_FILE
]

if csv_files:

    selected_csv = st.selectbox(
        "Choose CSV file",
        csv_files
    )

    df = pd.read_csv(selected_csv)

    st.write(
        f"Loaded file: {selected_csv}"
    )

    st.write(
        f"Rows loaded: {len(df)}"
    )

    odds_option = st.selectbox(
        "Odds column",
        [
            "Auto",
            "B365>2.5",
            "Avg>2.5",
            "Max>2.5"
        ]
    )

    min_odds = st.number_input(
        "Minimum odds",
        value=1.60,
        step=0.05
    )

    max_odds = st.number_input(
        "Maximum odds",
        value=3.00,
        step=0.05
    )

    stake = st.number_input(
        "Stake",
        value=1.0,
        step=0.5
    )

    if st.button("Run CSV Backtest"):

        total_bets = 0
        wins = 0
        losses = 0
        total_profit = 0

        rows = []

        for _, row in df.iterrows():

            try:

                home_goals = int(
                    row["FTHG"]
                )

                away_goals = int(
                    row["FTAG"]
                )

                total_goals = (
                    home_goals +
                    away_goals
                )

                if (
                    odds_option != "Auto" and
                    odds_option in df.columns
                ):

                    odds = float(
                        row[odds_option]
                    )

                elif "B365>2.5" in df.columns:

                    odds = float(
                        row["B365>2.5"]
                    )

                elif "Avg>2.5" in df.columns:

                    odds = float(
                        row["Avg>2.5"]
                    )

                else:

                    odds = 1.70

                if pd.isna(odds):
                    continue

                if odds < min_odds:
                    continue

                if odds > max_odds:
                    continue

                if total_goals < 2:
                    continue

                total_bets += 1

                if total_goals > 2.5:

                    profit = (
                        stake *
                        (odds - 1)
                    )

                    wins += 1

                    result = "Win"

                else:

                    profit = -stake

                    losses += 1

                    result = "Loss"

                total_profit += profit

                rows.append({
                    "Date": row.get("Date", ""),
                    "Home": row.get("HomeTeam", ""),
                    "Away": row.get("AwayTeam", ""),
                    "Goals": total_goals,
                    "Odds": odds,
                    "Result": result,
                    "Profit": round(profit, 2)
                })

            except:
                continue

        if total_bets > 0:

            roi = (
                total_profit /
                (total_bets * stake)
            ) * 100

            strike_rate = (
                wins /
                total_bets
            ) * 100

            st.subheader(
                "📊 Backtest Results"
            )

            st.write(
                f"Total Bets: {total_bets}"
            )

            st.write(
                f"Wins: {wins}"
            )

            st.write(
                f"Losses: {losses}"
            )

            st.write(
                f"Strike Rate: {strike_rate:.1f}%"
            )

            st.write(
                f"Profit: {total_profit:.2f} units"
            )

            st.write(
                f"ROI: {roi:.2f}%"
            )

            results_df = pd.DataFrame(rows)

            st.dataframe(results_df)

            st.subheader(
                "📉 Profit Curve"
            )

            results_df[
                "Cumulative Profit"
            ] = results_df[
                "Profit"
            ].cumsum()

            st.line_chart(
                results_df[
                    "Cumulative Profit"
                ]
            )

        else:

            st.warning(
                "No bets found in this CSV."
            )

else:

    st.warning(
        "No CSV files found in the repo."
    )
