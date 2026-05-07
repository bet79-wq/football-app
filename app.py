import streamlit as st
import requests
import math
import pandas as pd
import os

# 🔐 ADD YOUR API KEY HERE
API_KEY = "ef07da036042ddf4dfb8cebaa0cab6f1"

headers = {
    "x-apisports-key": API_KEY
}

# 📊 POISSON FUNCTIONS
def poisson_prob(lmbda, k):
    return (math.exp(-lmbda) * (lmbda ** k)) / math.factorial(k)

def over_2_5_probability(lmbda):
    prob_under = 0
    for i in range(3):
        prob_under += poisson_prob(lmbda, i)
    return 1 - prob_under

# 📁 RESULTS FILE SETUP
RESULTS_FILE = "results.csv"

if not os.path.exists(RESULTS_FILE):
    df = pd.DataFrame(columns=["Match", "Bet", "Odds", "Stake", "Result", "Profit"])
    df.to_csv(RESULTS_FILE, index=False)

df = pd.read_csv(RESULTS_FILE)

st.title("⚽ Advanced Football Betting System")

# 📅 GET MATCHES
fixtures_url = "https://v3.football.api-sports.io/fixtures?next=10"
fixtures = requests.get(fixtures_url, headers=headers).json().get("response", [])

match_list = []

for m in fixtures:
    home = m["teams"]["home"]["name"]
    away = m["teams"]["away"]["name"]
    match_list.append((f"{home} vs {away}", m["fixture"]["id"]))

if match_list:

    selected = st.selectbox("Select Match", match_list)
    fixture_id = selected[1]

    match_data = next(m for m in fixtures if m["fixture"]["id"] == fixture_id)

    home_id = match_data["teams"]["home"]["id"]
    away_id = match_data["teams"]["away"]["id"]

    # 📊 TEAM STATS
    def team_stats(team_id):
        url = f"https://v3.football.api-sports.io/teams/statistics?team={team_id}&season=2023"
        return requests.get(url, headers=headers).json()["response"]

    # 📊 FORM + PRESSURE
    def recent_form(team_id):
        url = f"https://v3.football.api-sports.io/fixtures?team={team_id}&last=5"
        data = requests.get(url, headers=headers).json().get("response", [])

        goals, shots, corners = [], [], []

        for match in data:
            fixture = match["fixture"]["id"]

            stats_url = f"https://v3.football.api-sports.io/fixtures/statistics?fixture={fixture}"
            stats = requests.get(stats_url, headers=headers).json().get("response", [])

            try:
                team_stats_data = stats[0]["statistics"]

                for stat in team_stats_data:
                    if stat["type"] == "Total Shots":
                        shots.append(stat["value"] or 0)
                    if stat["type"] == "Corner Kicks":
                        corners.append(stat["value"] or 0)

                goals.append(match["goals"]["for"])

            except:
                continue

        avg_goals = sum(goals)/len(goals) if goals else 1
        avg_shots = sum(shots)/len(shots) if shots else 10
        avg_corners = sum(corners)/len(corners) if corners else 5

        return avg_goals, avg_shots, avg_corners

    # 💰 ODDS
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

    try:
        home_stats = team_stats(home_id)
        away_stats = team_stats(away_id)

        LEAGUE_AVG = 2.6

        home_scored_home = float(home_stats["goals"]["for"]["average"]["home"])
        home_conceded_home = float(home_stats["goals"]["against"]["average"]["home"])

        away_scored_away = float(away_stats["goals"]["for"]["average"]["away"])
        away_conceded_away = float(away_stats["goals"]["against"]["average"]["away"])

        home_attack = home_scored_home / (LEAGUE_AVG/2)
        home_defence = home_conceded_home / (LEAGUE_AVG/2)

        away_attack = away_scored_away / (LEAGUE_AVG/2)
        away_defence = away_conceded_away / (LEAGUE_AVG/2)

        expected_home = home_attack * away_defence * (LEAGUE_AVG/2)
        expected_away = away_attack * home_defence * (LEAGUE_AVG/2)

        # 📈 FORM + PRESSURE
        home_form_goals, home_shots, home_corners = recent_form(home_id)
        away_form_goals, away_shots, away_corners = recent_form(away_id)

        home_pressure = home_shots + (home_corners * 0.5)
        away_pressure = away_shots + (away_corners * 0.5)

        expected_home += (home_form_goals * 0.2) + (home_pressure / 100)
        expected_away += (away_form_goals * 0.2) + (away_pressure / 100)

        total_xg = expected_home + expected_away

        st.subheader("📊 Model Output")
        st.write(f"Total xG: {total_xg:.2f}")

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
            bankroll = st.number_input("Bankroll (£)", value=100)

            kelly = ((prob_over * odds) - 1) / (odds - 1)
            kelly = max(0, min(kelly, 0.1))
            stake = bankroll * kelly

            st.write(f"Stake: £{stake:.2f}")

            if passes_filters:
                st.success("✅ PLACE BET")
            else:
                st.warning("🚫 NO BET")

            # 📝 LOGGING
            st.subheader("📝 Log Result")

            result = st.selectbox("Result", ["Pending", "Win", "Loss"])

            if st.button("Save Bet"):

                profit = 0
                if result == "Win":
                    profit = stake * (odds - 1)
                elif result == "Loss":
                    profit = -stake

                new_row = {
                    "Match": selected[0],
                    "Bet": "Over 2.5",
                    "Odds": odds,
                    "Stake": stake,
                    "Result": result,
                    "Profit": profit
                }

                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                df.to_csv(RESULTS_FILE, index=False)

                st.success("Saved!")

        else:
            st.warning("No odds available")

    except:
        st.error("Error loading data")

# 📊 DASHBOARD
st.subheader("📊 Performance Dashboard")

df = pd.read_csv(RESULTS_FILE)

if not df.empty:

    total = len(df[df["Result"] != "Pending"])
    wins = len(df[df["Result"] == "Win"])
    losses = len(df[df["Result"] == "Loss"])

    profit = df["Profit"].sum()
    staked = df["Stake"].sum()

    roi = (profit / staked * 100) if staked > 0 else 0

    st.write(f"Bets: {total}")
    st.write(f"Wins: {wins}")
    st.write(f"Losses: {losses}")
    st.write(f"Profit: £{profit:.2f}")
    st.write(f"ROI: {roi:.2f}%")

    st.dataframe(df)

else:
    st.write("No bets yet")