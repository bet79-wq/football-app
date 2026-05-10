import streamlit as st
import pandas as pd
import os

# =========================================
# PAGE SETUP
# =========================================

st.set_page_config(
    page_title="Bet Angel Excel Test",
    layout="wide"
)

st.title("📈 Bet Angel Live Excel Feed Test")

st.caption(
    "This app tests whether Streamlit can read your Bet Angel Excel file."
)

# Auto refresh every 10 seconds
st.markdown(
    """
    <meta http-equiv="refresh" content="10">
    """,
    unsafe_allow_html=True
)

# =========================================
# FILE SETTINGS
# =========================================

EXCEL_FILE = "betangel_live.xlsx"

st.header("🔍 File Check")

st.write("Looking for file:")

st.code(EXCEL_FILE)

st.write("Current folder files:")

st.write(os.listdir())

# =========================================
# LOAD EXCEL FILE
# =========================================

st.header("📊 Excel Data")

if os.path.exists(EXCEL_FILE):

    st.success("✅ Excel file found")

    try:
        df = pd.read_excel(
            EXCEL_FILE,
            engine="openpyxl"
        )

        st.success("✅ Excel file loaded successfully")

        st.write(f"Rows loaded: {len(df)}")
        st.write(f"Columns found: {len(df.columns)}")

        st.subheader("Column Names")
        st.write(list(df.columns))

        st.subheader("Live Bet Angel Data")
        st.dataframe(
            df,
            use_container_width=True
        )

        # =========================================
        # SIMPLE MARKET CHECK
        # =========================================

        st.header("⚽ Simple Market Reader")

        text_columns = []

        for col in df.columns:
            if df[col].dtype == "object":
                text_columns.append(col)

        if text_columns:
            selected_text_col = st.selectbox(
                "Choose match/market column",
                text_columns
            )

            search_text = st.text_input(
                "Search match or market",
                ""
            )

            if search_text:
                filtered_df = df[
                    df[selected_text_col]
                    .astype(str)
                    .str.contains(
                        search_text,
                        case=False,
                        na=False
                    )
                ]

                st.write(
                    f"Rows matching '{search_text}': {len(filtered_df)}"
                )

                st.dataframe(
                    filtered_df,
                    use_container_width=True
                )

        # =========================================
        # ODDS COLUMN TEST
        # =========================================

        st.header("💰 Odds Column Test")

        numeric_columns = df.select_dtypes(
            include=["number"]
        ).columns.tolist()

        if numeric_columns:

            selected_odds_col = st.selectbox(
                "Choose an odds column",
                numeric_columns
            )

            min_odds = st.number_input(
                "Minimum odds to highlight",
                value=1.50,
                step=0.05
            )

            odds_df = df[
                df[selected_odds_col] >= min_odds
            ]

            st.write(
                f"Rows where {selected_odds_col} >= {min_odds}: {len(odds_df)}"
            )

            st.dataframe(
                odds_df,
                use_container_width=True
            )

        else:

            st.warning("No numeric columns found yet.")

    except Exception as e:

        st.error("❌ Excel file found but could not be loaded")

        st.write("Error message:")

        st.code(str(e))

        st.warning(
            "If Bet Angel currently has the file open, try saving it again or closing/reopening Excel."
        )

else:

    st.error("❌ Excel file not found")

    st.write(
        "Make sure betangel_live.xlsx is in the same folder as app.py."
    )
