import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from backtest_engine.backtester import Backtester
from urllib.parse import urlencode
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from finstore.finstore import Finstore

st.set_page_config(page_title="Trade Analyzer", layout="wide")
st.title("📈 Backtest Trade Analyzer")

@st.cache_resource
def get_finstore(market_name, timeframe, pair=''):
    return Finstore(market_name=market_name, timeframe=timeframe, pair=pair)

# 🔄 Load Previously Backtested Portfolio
with st.expander("📂 Load Previous Backtest", expanded=True):
    with st.spinner("Loading backtests..."):
        backtests = Backtester.list_backtests()
        if not backtests:
            st.info("No saved backtests found. Run and save a backtest first.")
            st.stop()
        else:
            selected_backtest = st.selectbox("Select a backtest to view:", list(backtests.keys()))
            if selected_backtest:
                params = backtests[selected_backtest]
                st.session_state.params = params  # store for later use
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Strategy Name:** {params['strategy_name']}")
                    st.write(f"**Market Name:** {params['market_name']}")
                    st.write(f"**Timeframe:** {params['timeframe']}")
                    st.write(f"**Symbols:** {', '.join(params['symbol_list'])}")
                    st.write(f"**Trading Pair:** {params['pair']}")
                    st.write(f"**Start Date:** {params['start_date']}")
                    st.write(f"**End Date:** {params['end_date']}")
                with col2:
                    st.write(f"**Initial Cash:** ${params['init_cash']:,.2f}")
                    st.write(f"**Trading Fees:** {params['fees'] * 100:.4f}%")
                    st.write(f"**Slippage:** {params['slippage'] * 100:.4f}%")
                    st.write(f"**Allow Partial Orders:** {params['allow_partial']}")
                    st.write("**Strategy Parameters:**")
                    st.json(params["strategy_params"])


                # 📊 Performance Metrics
                
                # 📊 Performance Metrics
                st.subheader("📊 Performance Metrics")
                col1, col2, col3 = st.columns(3)
                col1.metric(label="📈 Returns", value=f"{params['performance']['returns']:.2%}")
                col2.metric(label="📈 Sharpe Ratio", value=f"{params['performance']['sharpe_ratio']:.2f}")
                col3.metric(label="📉 Max Drawdown", value=f"{params['performance']['max_drawdown']:.2%}")
                
                if st.button("🔍 Load Portfolio & Stats"):
                    with st.spinner("Loading backtest..."):
                        pf, _ = Backtester.load_backtest(selected_backtest)
                    st.session_state.pf = pf
                    st.session_state.trades_df = pf.trades.records_readable.sort_values(by="PnL", ascending=False).reset_index(drop=True)
                    st.success(f"Successfully loaded backtest: {selected_backtest}")

# Continue only if portfolio is loaded
if "pf" in st.session_state:
    pf = st.session_state.pf
    trades_df = st.session_state.trades_df

    st.subheader("📊 Portfolio Statistics")
    stats_df = pf.stats().to_frame(name="Value")
    stats_df["Value"] = stats_df["Value"].apply(lambda x: str(x) if isinstance(x, pd.Timedelta) else x)
    st.dataframe(stats_df)

    st.subheader("📈 Equity (PNL) Curve")
    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Scatter(x=pf.value.index, y=pf.value, mode='lines', name="Portfolio Value"))
    fig_pnl.update_layout(
        yaxis_title="Portfolio Value",
        title="Equity Curve",
        yaxis_type="log" if pf.value.max() > 10000 else "linear"
    )
    st.plotly_chart(fig_pnl)

    st.subheader("📈 Cumulative Returns")
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(x=pf.cumulative_returns.index, y=pf.cumulative_returns, mode='lines', name="Cumulative Returns"))
    fig_cum.update_layout(
        yaxis_title="Cumulative Returns",
        title="Cumulative Returns Curve",
        yaxis_type="log" if pf.cumulative_returns.max() > 10 else "linear"
    )
    st.plotly_chart(fig_cum)

    # 📌 Trade Signals: Use AgGrid for an interactive, sortable table.
    st.subheader("📌 Trade Signals")
    gb = GridOptionsBuilder.from_dataframe(trades_df)
    gb.configure_selection(selection_mode="single", use_checkbox=True)
    grid_options = gb.build()

    grid_response = AgGrid(
        trades_df,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.SELECTION_CHANGED,
        theme="streamlit",
        height=300
    )
    selected_rows = grid_response["selected_rows"]
    print(type(selected_rows))
    print(selected_rows)

    if selected_rows is not None and len(selected_rows) > 0:
        st.session_state.selected_trade = selected_rows.iloc[0]
    else:
        st.session_state.selected_trade = None


    # Only show the button if a row is selected.
    if st.session_state.selected_trade is not None:
        if st.button("View Chart for Selected Trade"):
            current_trade = st.session_state.selected_trade
            # Use "Column" for symbol, "Entry Index" and "Exit Index" for trade timestamps.
            trade_pair = current_trade["Column"]
            entry_timestamp = pd.Timestamp(current_trade["Entry Index"])
            exit_timestamp = pd.Timestamp(current_trade["Exit Index"])

            # Fetch OHLCV data for the traded pair using the timeframe from params.
            timeframe = st.session_state.params['timeframe']
            _, ohlcv_data = get_finstore("crypto_binance", timeframe, pair="BTC").read.symbol(trade_pair)
            ohlcv_data["timestamp"] = pd.to_datetime(ohlcv_data["timestamp"])

            # Determine buffer based on timeframe
            timeframe = params['timeframe']
            timeframe_mapping = {
                "1d": pd.Timedelta(days=5),
                "1h": pd.Timedelta(hours=12),
                "15m": pd.Timedelta(minutes=90),
                "5m": pd.Timedelta(minutes=30),
                "1m": pd.Timedelta(minutes=10)
            }
            buffer = timeframe_mapping.get(timeframe, pd.Timedelta(days=5))

            filtered_data = ohlcv_data[
                (ohlcv_data["timestamp"] >= entry_timestamp - buffer) &
                (ohlcv_data["timestamp"] <= exit_timestamp + buffer)
            ]

            fig_trade = go.Figure()

            fig_trade.add_trace(go.Candlestick(
                x=filtered_data["timestamp"],
                open=filtered_data["open"],
                high=filtered_data["high"],
                low=filtered_data["low"],
                close=filtered_data["close"],
                name="Price"
            ))

            # Determine entry and exit prices for markers
            entry_price_series = filtered_data.loc[filtered_data["timestamp"] == entry_timestamp, "close"]
            entry_price = entry_price_series.values[0] if not entry_price_series.empty else filtered_data.iloc[0]["close"]
            exit_price_series = filtered_data.loc[filtered_data["timestamp"] == exit_timestamp, "close"]
            exit_price = exit_price_series.values[0] if not exit_price_series.empty else filtered_data.iloc[-1]["close"]

            fig_trade.add_trace(go.Scatter(
                x=[entry_timestamp],
                y=[entry_price],
                mode="markers+text",
                marker=dict(symbol="arrow-up", size=15, color="green"),
                name="Buy Entry",
                text=["Buy"],
                textposition="bottom center"
            ))
            fig_trade.add_trace(go.Scatter(
                x=[exit_timestamp],
                y=[exit_price],
                mode="markers+text",
                marker=dict(symbol="arrow-down", size=15, color="red"),
                name="Sell Exit",
                text=["Sell"],
                textposition="top center"
            ))

            fig_trade.update_layout(
                title=f"Trade Analysis: {trade_pair}",
                xaxis_title="Date",
                yaxis_title="Price",
                xaxis_rangeslider_visible=False
            )

            st.subheader("📉 Trade Visualization")
            st.plotly_chart(fig_trade)
