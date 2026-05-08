import streamlit as st
import requests
import math
import pandas as pd
import os

# 🔐 API KEY
API_KEY = os.getenv("API_KEY")

headers = {
    "x-apisports-key": API_KEY
}

# 📲 TELEGRAM SETTINGS
BOT_TOKEN = "8734598526:AAGAygBTOGvxPzEkgMru6hs5RZNxFAN76mc"
CHAT_ID = "7983580834"

# 📊 RESULTS FILE
RESULTS_FILE = "results.csv"

if not os.path.exists(RESULTS_FILE):
    df = pd.DataFrame(columns=[
        "Match",
        "Bet",
        "Odds",
        "Stake",
        "Result",
        "Profit"
    ])
    df.to_csv(RESULTS_FILE, index=False)

# 📊 POISSON FUNCTIONS
def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def over_2_5_probability(lmbda):
    prob_under = 0

    for i in range(3):
        prob_under += poisson_prob(lmbda, i)

    return 1 - prob_under

# 📲 TELEGRAM ALERTS
def send_telegram_message(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=payload)

# ⚽ APP TITLE
st.title("⚽ Advanced Football Betting System")

# 🔥 DAILY PICKS
st.header("🔥 Automatic Daily Picks")

daily_picks = []

fixtures_url = "https://v3.football.api-sports.io/fixtures?next=20"

fixtures = requests.get(
    fixtures_url,
    headers=headers
).json().get("response", [])

LEAGUE_AVG = 2.6

# 💰 ODDS FUNCTION
def get_odds(fixture_id):

    url = f"https://v3.football.api-sports.io/odds?fixture={fixture_id}"

    res = requests.get(url, headers=headers).json()

    try:
        bets = res["response"][0]["bookmakers"][0]["bets"]

        for bet in bets:

            if bet["name"] == "Goals Over/Under":

                for v in bet["values"]:

                    if v["value"] == "Over 2.5":
                        return float(v["odd"])

    except:
        return None

# 📊 DAILY SCAN
for match in fixtures:

    try:
        fixture_id = match["fixture"]["id"]

        home_team = match["teams"]["home"]["name"]
        away_team = match["teams"]["away"]["name"]

        home_id = match["teams"]["home"]["id"]
        away_id = match["teams"]["away"]["id"]

        # TEAM STATS
        home_stats = requests.get(
            f"https://v3.football.api-sports.io/teams/statistics?team={home_id}&season=2023",
            headers=headers
        ).json()["response"]

        away_stats = requests.get(
            f"https://v3.football.api-sports.io/teams/statistics?team={away_id}&season=2023",
            headers=headers
        ).json()["response"]

        # HOME/AWAY STRENGTHS
        home_attack = float(
            home_stats["goals"]["for"]["average"]["home"]
        ) / (LEAGUE_AVG / 2)

        home_defence = float(
            home_stats["goals"]["against"]["average"]["home"]
        ) / (LEAGUE_AVG / 2)

        away_attack = float(
            away_stats["goals"]["for"]["average"]["away"]
        ) / (LEAGUE_AVG / 2)

        away_defence = float(
            away_stats["goals"]["against"]["average"]["away"]
        ) / (LEAGUE_AVG / 2)

        # EXPECTED GOALS
        expected_home = (
            home_attack *
            away_defence *
            (LEAGUE_AVG / 2)
        )

        expected_away = (
            away_attack *
            home_defence *
            (LEAGUE_AVG / 2)
        )

        total_xg = expected_home + expected_away

        # 📊 OVER 2.5 PROBABILITY
        prob_over = over_2_5_probability(total_xg)

        # 💰 ODDS
        odds = get_odds(fixture_id)

        if odds:

            implied = 1 / odds
            edge = prob_over - implied

            # 🎯 FILTERS
            if (
                prob_over >= 0.55 and
                edge >= 0.05 and
                total_xg >= 2.2
            ):

                # 📲 SEND TELEGRAM ALERT
                message = f"""
🔥 VALUE BET FOUND

{home_team} vs {away_team}

Over 2.5

Probability: {prob_over*100:.1f}%
Odds: {odds}
Edge: {edge*100:.1f}%
"""

                send_telegram_message(message)

                daily_picks.append({
                    "Match": f"{home_team} vs {away_team}",
                    "Probability": f"{prob_over*100:.1f}%",
                    "Odds": odds,
                    "Edge": f"{edge*100:.1f}%",
                    "Decision": "✅ BET"
                })

    except:
        continue

# 📊 SHOW PICKS
if daily_picks:

    st.success(f"{len(daily_picks)} value bets found today")

    picks_df = pd.DataFrame(daily_picks)

    st.dataframe(picks_df)

else:
    st.warning("No qualifying bets today")

# 📅 MATCH SELECTOR
match_list = []

for m in fixtures:
    home = m["teams"]["home"]["name"]
    away = m["teams"]["away"]["name"]

    match_list.append((
        f"{home} vs {away}",
        m["fixture"]["id"]
    ))

if match_list:

    selected = st.selectbox(
        "Select Match",
        match_list
    )

    fixture_id = selected[1]

    match_data = next(
        m for m in fixtures
        if m["fixture"]["id"] == fixture_id
    )

    home_id = match_data["teams"]["home"]["id"]
    away_id = match_data["teams"]["away"]["id"]

    # 📊 TEAM STATS
    def team_stats(team_id):

        url = f"https://v3.football.api-sports.io/teams/statistics?team={team_id}&season=2023"

        return requests.get(
            url,
            headers=headers
        ).json()["response"]

    try:
        home_stats = team_stats(home_id)
        away_stats = team_stats(away_id)

        home_scored_home = float(
            home_stats["goals"]["for"]["average"]["home"]
        )

        home_conceded_home = float(
            home_stats["goals"]["against"]["average"]["home"]
        )

        away_scored_away = float(
            away_stats["goals"]["for"]["average"]["away"]
        )

        away_conceded_away = float(
            away_stats["goals"]["against"]["average"]["away"]
        )

        home_attack = home_scored_home / (LEAGUE_AVG / 2)
        home_defence = home_conceded_home / (LEAGUE_AVG / 2)

        away_attack = away_scored_away / (LEAGUE_AVG / 2)
        away_defence = away_conceded_away / (LEAGUE_AVG / 2)

        expected_home = (
            home_attack *
            away_defence *
            (LEAGUE_AVG / 2)
        )

        expected_away = (
            away_attack *
            home_defence *
            (LEAGUE_AVG / 2)
        )

        total_xg = expected_home + expected_away

        st.subheader("📊 Match Model")

        st.write(f"Home xG: {expected_home:.2f}")
        st.write(f"Away xG: {expected_away:.2f}")
        st.write(f"Total xG: {total_xg:.2f}")

        # 📊 PROBABILITIES
        prob_over = over_2_5_probability(total_xg)
        prob_under = 1 - prob_over

        st.subheader("📊 Probabilities")

        st.write(f"Over 2.5: {prob_over*100:.1f}%")
        st.write(f"Under 2.5: {prob_under*100:.1f}%")

        odds = get_odds(fixture_id)

        if odds:

            implied = 1 / odds
            edge = prob_over - implied

            st.subheader("💰 Market")

            st.write(f"Odds: {odds}")
            st.write(f"Edge: {edge*100:.1f}%")

            # 🎯 FILTERS
            min_prob = 0.55
            min_edge = 0.05
            min_xg = 2.2

            passes_filters = (
                prob_over >= min_prob and
                edge >= min_edge and
                total_xg >= min_xg
            )

            # 💰 BANKROLL
            bankroll = st.number_input(
                "Bankroll (£)",
                value=100
            )

            kelly = (
                ((prob_over * odds) - 1)
                / (odds - 1)
            )

            kelly = max(0, min(kelly, 0.1))

            stake = bankroll * kelly

            st.write(f"Recommended Stake: £{stake:.2f}")

            # 🚨 DECISION
            if passes_filters:
                st.success("✅ PLACE BET")
            else:
                st.warning("🚫 NO BET")

            # 📝 LOG RESULTS
            st.subheader("📝 Log Result")

            result = st.selectbox(
                "Result",
                ["Pending", "Win", "Loss"]
            )

            if st.button("Save Bet"):

                profit = 0

                if result == "Win":
                    profit = stake * (odds - 1)

                elif result == "Loss":
                    profit = -stake

                df = pd.read_csv(RESULTS_FILE)

                new_row = {
                    "Match": selected[0],
                    "Bet": "Over 2.5",
                    "Odds": odds,
                    "Stake": stake,
                    "Result": result,
                    "Profit": profit
                }

                df = pd.concat([
                    df,
                    pd.DataFrame([new_row])
                ], ignore_index=True)

                df.to_csv(
                    RESULTS_FILE,
                    index=False
                )

                st.success("Bet Saved!")

        else:
            st.warning("Odds unavailable")

    except:
        st.error("Error loading match")

# 📊 PERFORMANCE DASHBOARD
st.subheader("📊 Performance Dashboard")

df = pd.read_csv(RESULTS_FILE)

if not df.empty:

    total_bets = len(
        df[df["Result"] != "Pending"]
    )

    wins = len(
        df[df["Result"] == "Win"]
    )

    losses = len(
        df[df["Result"] == "Loss"]
    )

    profit = df["Profit"].sum()
    staked = df["Stake"].sum()

    roi = (
        (profit / staked) * 100
        if staked > 0 else 0
    )

    st.write(f"Total Bets: {total_bets}")
    st.write(f"Wins: {wins}")
    st.write(f"Losses: {losses}")
    st.write(f"Profit: £{profit:.2f}")
    st.write(f"ROI: {roi:.2f}%")

    st.dataframe(df)

else:
    st.write("No bets logged yet")
