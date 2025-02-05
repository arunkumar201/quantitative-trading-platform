import streamlit as st
import pandas as pd
import inspect
import datetime
from datetime import date
import pickle
import time
from finstore.finstore import Finstore
import vectorbtpro as vbt
from strategy.public.ema_strategy import get_ema_signals_wrapper
import plotly.graph_objects as go
import numpy as np

# -------------------------------------------------------------------
# Cache functions to load data from Finstore
# -------------------------------------------------------------------
@st.cache_resource
def get_finstore_crypto(timeframe='4h'):
    return Finstore(market_name='crypto_binance', timeframe=timeframe)

@st.cache_resource
def get_finstore_indian_equity(timeframe='1d'):
    return Finstore(market_name='indian_equity', timeframe=timeframe)

@st.cache_resource
def get_finstore(market_name, timeframe, pair=''):
    return Finstore(market_name=market_name, timeframe=timeframe, pair=pair)

# -------------------------------------------------------------------
# Dummy Strategy Functions for Demonstration
# -------------------------------------------------------------------
def list_strategy_modules():
    """Return available strategy modules with their parameters"""
    return {
        'EMA Crossover Strategy': get_ema_signals_wrapper,
        'RSI Strategy': dummy_rsi_strategy,
        'MACD Strategy': dummy_macd_strategy
    }


def dummy_rsi_strategy(ohlcv_data, symbol_list, rsi_period=14, oversold=30, overbought=70):
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

def dummy_macd_strategy(ohlcv_data, symbol_list, fast=12, slow=26, signal=9):
    return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# -------------------------------------------------------------------
# Asset Selection Helpers
# -------------------------------------------------------------------
def handle_crypto_selection(crypto_data):
    """Clean crypto selection with pair type filtering and search"""
    col1, col2 = st.columns([1, 3])
    
    with col1:
        pair_type = st.radio(
            "Pair Type:",
            options=["USDT", "BTC"],
            horizontal=True,
            help="Filter by trading pair type"
        )
        
    with col2:
        symbols = crypto_data.get(f"{pair_type} Pairs", [])
        search_query = st.text_input("Search crypto pairs:", key="crypto_search")
        filtered = [s for s in symbols if search_query.lower() in s.lower()]
        
        # Batch operations
        col1, col2 = st.columns(2)
        with col1:
            if st.button(f"Add all {pair_type} pairs", help="Add all filtered pairs"):
                add_symbols(filtered)
        with col2:
            if st.button(f"Clear {pair_type} selection", help="Remove all pairs of this type"):
                remove_symbols(filtered)
        
        # Symbol selection
        selected = st.multiselect(
            "Available pairs:",
            options=filtered,
            default=[s for s in filtered if s in st.session_state.selected_symbols],
            label_visibility="collapsed"
        )
        update_selection(selected, filtered)

def handle_equity_selection(indian_data, us_data):
    """Equity market selection with country grouping"""
    country = st.radio(
        "Market Region:",
        options=["India", "US"],
        horizontal=True
    )
    
    symbols = indian_data.get('NSE Equity', []) if country == "India" \
        else us_data.get('NASDAQ', []) + us_data.get('NYSE', [])
    
    search_query = st.text_input(f"Search {country} equities:", key=f"equity_search_{country}")
    filtered = [s for s in symbols if search_query.lower() in s.lower()]
    
    # Batch operations
    col1, col2 = st.columns(2)
    with col1:
        if st.button(f"Select all {country}"):
            add_symbols(filtered)
    with col2:
        if st.button(f"Clear {country}"):
            remove_symbols(filtered)
    
    # Symbol selection
    selected = st.multiselect(
        f"Select {country} equities:",
        options=filtered,
        default=[s for s in filtered if s in st.session_state.selected_symbols],
        label_visibility="collapsed"
    )
    update_selection(selected, filtered)

def handle_other_selection(commodities_data):
    """Commodities and other markets selection"""
    search_query = st.text_input("Search commodities:", key="comm_search")
    symbols = commodities_data.get('Metals', []) + commodities_data.get('Energy', [])
    filtered = [s for s in symbols if search_query.lower() in s.lower()]
    
    # Batch operations
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Select all commodities"):
            add_symbols(filtered)
    with col2:
        if st.button("Clear commodities"):
            remove_symbols(filtered)
    
    # Symbol selection
    selected = st.multiselect(
        "Select commodities:",
        options=filtered,
        default=[s for s in filtered if s in st.session_state.selected_symbols],
        label_visibility="collapsed"
    )
    update_selection(selected, filtered)

def display_selected_symbols():
    """Clean display of selected symbols"""
    selected = st.session_state.selected_symbols
    st.write(f"**Selected Assets:** {len(selected)}")
    
    if selected:
        # Show first 3 symbols + count of remaining
        display_text = ", ".join(selected[:3])
        if len(selected) > 3:
            display_text += f" (+{len(selected)-3} more)"
        st.caption(display_text)
        
        if st.button("Clear all selections", type="primary"):
            st.session_state.selected_symbols = []

def add_symbols(symbols):
    st.session_state.selected_symbols = list(set(st.session_state.selected_symbols + symbols))

def remove_symbols(symbols):
    st.session_state.selected_symbols = [s for s in st.session_state.selected_symbols if s not in symbols]

def update_selection(selected, full_list):
    """Handle multiselect updates"""
    for symbol in selected:
        if symbol not in st.session_state.selected_symbols:
            st.session_state.selected_symbols.append(symbol)
    for symbol in full_list:
        if symbol not in selected and symbol in st.session_state.selected_symbols:
            st.session_state.selected_symbols.remove(symbol)

def get_available_assets(timeframe=None):
    """Return hierarchical market structure with nested universes"""
    asset_groups = {}
    if not timeframe:
        return {'Please select timeframe first': []}

    try:
        # Get crypto pairs
        btc_pairs = get_finstore("crypto_binance", timeframe, pair="BTC").read.get_symbol_list()
        usdt_pairs = get_finstore("crypto_binance", timeframe, pair="USDT").read.get_symbol_list()
        asset_groups['Crypto'] = {
            'BTC Pairs': list(btc_pairs) if len(btc_pairs) > 0 else ['No BTC pairs'],
            'USDT Pairs': list(usdt_pairs) if len(usdt_pairs) > 0 else ['No USDT pairs']
        }
    except Exception as e:
        asset_groups['Crypto'] = {'Error': [f'Failed to load crypto data: {str(e)}']}

    try:
        nse_eq = get_finstore("indian_equity", timeframe, pair="").read.get_symbol_list()
        asset_groups['Indian Market'] = {
            'NSE Equity': list(nse_eq) if len(nse_eq) > 0 else ['No NSE equities']
        }
    except Exception as e:
        asset_groups['Indian Market'] = {'Error': [f'Failed to load Indian data: {str(e)}']}

    asset_groups.update({
        'US Market': {
            'NASDAQ': ['AAPL', 'TSLA', 'GOOG'],
            'NYSE': ['IBM', 'BA']
        },
        'Commodities': {
            'Metals': ['GOLD', 'SILVER'],
            'Energy': ['OIL', 'NATURALGAS']
        }
    })
    return asset_groups

def process_selected_assets(selections, timeframe):
    """Convert user selections to final symbol list with nested universes"""
    all_assets = get_available_assets(timeframe)
    selected_symbols = []
    for selection in selections:
        clean_selection = selection.replace(" ", "")
        if '/ (All)' in clean_selection:
            market_path = clean_selection.replace(' (All)', '').split('/')
            current_level = all_assets
            try:
                for level in market_path:
                    current_level = current_level[level.strip()]
                symbols = []
                for sub_level in current_level.values():
                    symbols.extend(sub_level)
                selected_symbols.extend(symbols)
            except KeyError:
                continue
        elif '(All)' not in clean_selection:
            selected_symbols.append(clean_selection)
    return list(set(selected_symbols))

# -------------------------------------------------------------------
# Strategy Backtester Page
# -------------------------------------------------------------------
def show_backtester_page():
    st.title("Strategy Backtester 🔧")
    
    # Initialize session state for selected symbols
    if 'selected_symbols' not in st.session_state:
        st.session_state.selected_symbols = []
    
    # 1. Timeframe Selection
    with st.expander("⏳ Timeframe Configuration", expanded=True):
        col1, col2 = st.columns([1, 3])
        with col1:
            timeframe = st.selectbox(
                "Timeframe:",
                options=["1D", "4H", "1H", "15m", "5m", "1m"],
                index=0
            )
    
    # 2. Strategy Module Selection
    with st.expander("📦 Strategy Module Selection", expanded=True):
        strategy_modules = list_strategy_modules()
        selected_module = st.selectbox("Select Strategy Module", options=list(strategy_modules.keys()))
    
    # 3. Asset Selection
    with st.expander("🌍 Asset Selection", expanded=True):
        asset_data = get_available_assets(timeframe)
        tab1, tab2, tab3 = st.tabs(["Crypto", "Equities", "Other"])
        
        with tab1:
            st.subheader("Crypto Markets")
            handle_crypto_selection(asset_data.get('Crypto', {}))
        with tab2:
            st.subheader("Stock Markets")
            handle_equity_selection(asset_data.get('Indian Market', {}), asset_data.get('US Market', {}))
        with tab3:
            st.subheader("Other Markets")
            handle_other_selection(asset_data.get('Commodities', {}))
        
        st.divider()
        display_selected_symbols()
    
    # 4. Strategy Parameters
    with st.expander("⚙️ Strategy Parameters", expanded=True):
        strategy_func = strategy_modules[selected_module]
        sig = inspect.signature(strategy_func)
        params = {}
        # Skip the first two parameters (ohlcv_data and symbol_list)
        for param in list(sig.parameters.values())[2:]:
            if param.annotation == int:
                val = st.number_input(
                    param.name,
                    value=param.default if param.default != inspect.Parameter.empty else 0,
                    step=1
                )
            elif param.annotation == float:
                val = st.number_input(
                    param.name,
                    value=param.default if param.default != inspect.Parameter.empty else 0.0,
                    step=0.1
                )
            else:
                val = st.text_input(
                    param.name,
                    value=str(param.default) if param.default != inspect.Parameter.empty else ""
                )
            params[param.name] = val
    
    # 5. Backtest Configuration
    with st.expander("📅 Backtest Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", value=date(2023, 1, 1))
        with col2:
            end_date = st.date_input("End Date", value=date(2026, 1, 1))
        
        init_cash = st.number_input("Initial Capital", value=100000)
        fees = st.number_input("Trading Fees (%)", value=0.0005)
        slippage = st.number_input("Slippage (%)", value=0.001)
        # Convert the string selection to a boolean
        allow_partial_str = st.selectbox(
            "Allow Partial ? (Usually set True for crypto):",
            options=["True", "False"],
            index=0
        )
        allow_partial = True if allow_partial_str == "True" else False

    # 6. Run Backtest
    if st.button("🚀 Run Backtest"):
        if not st.session_state.selected_symbols:
            st.error("Please select at least one asset!")
            return

        with st.spinner("Loading OHLCV data for selected symbols..."):
            # Load OHLCV data for selected symbols using Finstore
            binance_finstore = get_finstore('crypto_binance', timeframe=timeframe, pair='BTC')
            ohlcv_data = binance_finstore.read.symbol_list(st.session_state.selected_symbols)

        with st.spinner("Generating signals for selected strategy..."):
            # Generate strategy signals (replace with your actual implementation)
            entries, exits, close_data, open_data = strategy_func(
                ohlcv_data, 
                st.session_state.selected_symbols, 
                params.get('fast_ema_period', 10),
                params.get('slow_ema_period', 100)
            )
        
        with st.spinner("Running backtest..."):
            # Create the portfolio using the generated signals
            pf = vbt.Portfolio.from_signals(
                close=close_data,
                open=open_data,
                entries=entries,
                exits=exits,
                # Uncomment price='nextopen' if you want execution on next open
                # price='nextopen',
                direction='longonly',
                init_cash=init_cash,
                cash_sharing=True,
                size=0.01,  # Adjust the allocation per trade as needed
                size_type="valuepercent",
                fees=fees,
                slippage=slippage,
                allow_partial=allow_partial,
                sim_start=pd.Timestamp(start_date)
            )
            # Allow some time for the backtest to finish
            time.sleep(1)

        # Assuming 'pf' is the portfolio object generated from your backtest

        with st.spinner("Loading Backtest statistics..."):

            st.subheader("📊 Detailed Portfolio Statistics")
            stats_df = pf.stats().to_frame(name='Value')

            # Convert Timedelta values to strings
            stats_df["Value"] = stats_df["Value"].apply(lambda x: str(x) if isinstance(x, pd.Timedelta) else x)

            st.dataframe(stats_df)

            # --- Equity (PNL) Curve ---
            st.subheader("📈 Equity (PNL) Curve")
            fig_pnl = go.Figure()
            fig_pnl.add_trace(go.Scatter(
                x=pf.value.index, 
                y=pf.value,
                mode='lines',
                name="Portfolio Value"
            ))
            fig_pnl.update_layout(
                yaxis_title="Portfolio Value",
                title="Equity Curve",
                yaxis_type="log" if pf.value.max() > 10000 else "linear"  # Log scale for large values
            )
            st.plotly_chart(fig_pnl)

            # --- Cumulative Returns ---
            st.subheader("📈 Cumulative Returns")
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=pf.cumulative_returns.index, 
                y=pf.cumulative_returns,
                mode='lines',
                name="Cumulative Returns"
            ))
            fig_cum.update_layout(
                yaxis_title="Cumulative Returns",
                title="Cumulative Returns Curve",
                yaxis_type="log" if pf.cumulative_returns.max() > 10 else "linear"  # Log scale for large movements
            )
            st.plotly_chart(fig_cum)

            # Returns Overview (pf.returns is a property, not a method)
            st.subheader("📊 Returns Overview")
            returns_series = pf.returns
            returns_df = returns_series.to_frame(name="Returns")
            st.dataframe(returns_df)


            # Trade History
            st.subheader("📝 Trade History")
            st.dataframe(pf.trade_history)

            # Trade Signals (Records in a human-readable format)
            st.subheader("📌 Trade Signals")
            st.dataframe(pf.trades.records_readable)

        with st.spinner("Loading Advanced statistic plots..."):
            # Expanding Maximum Favorable Excursion (MFE)
            st.subheader("📊 Expanding MFE")
            fig_mfe = pf.trades.plot_expanding_mfe_returns()
            st.plotly_chart(fig_mfe)

            # Expanding Maximum Adverse Excursion (MAE)
            st.subheader("📊 Expanding MAE")
            fig_mae = pf.trades.plot_expanding_mae_returns()
            st.plotly_chart(fig_mae)


            # Risk-adjusted Metrics: Sharpe & Sortino Ratios
            sharpe_ratio = pf.get_sharpe_ratio()
            sortino_ratio = pf.get_sortino_ratio()
            st.metric(label="📈 Sharpe Ratio", value=f"{int(sharpe_ratio):.2f}")
            st.metric(label="📈 Sortino Ratio", value=f"{int(sortino_ratio):.2f}")

            # Benchmark Comparison (if available)
            if hasattr(pf, 'benchmark_cumulative_returns'):
                st.subheader("📊 Benchmark vs Portfolio Performance")
                st.line_chart(pf.benchmark_cumulative_returns)

# Run the page
show_backtester_page()