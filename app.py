import os
import uuid
import base64
import math
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Price & Promo Simulator", layout="wide")

# ---------------------------------------------------------------------
# Google Sheets configuration
# ---------------------------------------------------------------------
# Your Google Sheet:streamlit run d:/PnP_Blocks/Remy/notebooks/final/PricePromoSimulator_Streamlit_GoogleSheets_Updated/app.py
# https://docs.google.com/spreadsheets/d/1eUa3UNl6WbQAgx59caB-GSYaKUSPcniqA7Evvo1BJbs/edit
#
# Required worksheet/tab names:
# - config
# - coefficients
# - aggregation_matrix
# - base_price_scenarios
# - promo_scenarios
#
# Credentials are read from Streamlit Secrets.
# Do NOT commit real credentials to GitHub.
# ---------------------------------------------------------------------

GOOGLE_SHEET_ID_DEFAULT = "1eUa3UNl6WbQAgx59caB-GSYaKUSPcniqA7Evvo1BJbs"

CONFIG_CSV = "config"
COEFFICIENTS_CSV = "coefficients"
AGG_MATRIX_CSV = "aggregation_matrix"
BASE_SCENARIOS_CSV = "base_price_scenarios"
PROMO_SCENARIOS_CSV = "promo_scenarios"

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


@st.cache_resource(show_spinner=False)
def get_google_client():
    if "gcp_service_account" not in st.secrets:
        st.error("Google credentials were not found. Check .streamlit/secrets.toml or Streamlit Cloud Secrets.")
        st.stop()

    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=GOOGLE_SCOPES,
    )
    return gspread.authorize(creds)


@st.cache_resource(show_spinner=False)
def get_google_spreadsheet():
    sheet_id = st.secrets.get("google_sheet_id", GOOGLE_SHEET_ID_DEFAULT)
    try:
        return get_google_client().open_by_key(sheet_id)
    except Exception as e:
        st.error(
            "Cannot access the Google Sheet. Check that:\n"
            "1. Google Sheets API and Google Drive API are enabled.\n"
            "2. The spreadsheet is shared with the service account email as Editor.\n"
            "3. google_sheet_id is correct.\n\n"
            f"Original error: {e}"
        )
        raise


def get_or_create_worksheet(sheet_name):
    spreadsheet = get_google_spreadsheet()
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=100)


@st.cache_data(ttl=300, show_spinner=False)
def read_sheet(sheet_name):
    """Read a Google Sheet tab with caching.

    Cache makes page switching much faster because Streamlit reruns the full app
    on every click. The cache is cleared automatically after writes.
    """
    ws = get_or_create_worksheet(sheet_name)
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame()

    headers = values[0]
    rows = values[1:]
    if not headers or all(str(h).strip() == "" for h in headers):
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=headers)
    df = df.dropna(how="all")
    df = df.loc[:, [c for c in df.columns if str(c).strip() != ""]]

    # Pandas 3 compatibility: errors="ignore" is not valid anymore.
    for col in df.columns:
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() > 0:
            df[col] = converted.where(converted.notna(), df[col])

    return df


def write_sheet(sheet_name, df):
    ws = get_or_create_worksheet(sheet_name)
    out = df.copy()

    # Google Sheets cannot store NaN/inf reliably.
    out = out.replace([float("inf"), float("-inf")], "")
    out = out.fillna("")

    values = [out.columns.tolist()] + out.astype(str).values.tolist()

    ws.clear()
    if values:
        try:
            ws.update(values, value_input_option="USER_ENTERED")
        except TypeError:
            # Fallback for older gspread versions.
            ws.update(values)

    # Important: after saving scenarios, clear cached reads so the next read is fresh.
    read_sheet.clear()

CLOVER_BLUE = "#2B8EC4"
CLOVER_DARK = "#17324D"
CLOVER_BG = "#FFFFFF"
CLOVER_SIDEBAR = "#BFDDF2"
CLOVER_SOFT = "#F2F7FC"
CLOVER_BORDER = "#DCE7F2"
YELLOW = "#FFFACC"
RED = "#D64545"

FILTER_COLS = ["Country", "Channel", "Category", "Sub Category", "Size", "Product"]
KEY_COL = "ConfigKey"
LOW_LEVEL_COL = "Is Low Level"

TEXT_COLS = [
    "Scenario ID", "Scenario", "Created At", KEY_COL, "PPG_ID",
    *FILTER_COLS,
]

BASE_EDITABLE_COLS = ["Base Price", "Cost of Goods", "EDLP Cost per Unit"]
PROMO_EDITABLE_COLS = [
    "Base Price", "Cost of Goods", "Fixed Cost", "Variable Cost per Unit",
    "Total Weeks", "TPR Weeks", "TPR Promo Support", "Feature Weeks", "Feature Promo Support",
    "Display Weeks", "Display Promo Support", "F&D Weeks", "F&D ACV",
    "Promo Price", "Discount",
]

PROMO_EXPOSURE_COLS = ["TPR Promo Support", "Feature Promo Support", "Display Promo Support", "F&D ACV"]
PROMO_WEEK_COLS = ["Total Weeks", "TPR Weeks", "Feature Weeks", "Display Weeks", "F&D Weeks"]

COEF_COLS = [
    "Base Price Elasticity", "Promo Price Elasticity", "Total Weeks Elasticity",
    "Promo Support Coef", "Feature ACV Coef", "Display ACV Coef", "F&D ACV Coef",
    "Feature Display Interaction Coef", "Discount x Promo Support Coef",
    "Week 2 Decay", "Week 3+ Decay",
]

METRIC_COLORS = {
    "Units": "#2B8EC4",
    "Dollars": "#4CA3A0",
    "Spend": "#9BBF6A",
    "Cost": "#7F8FA6",
    "Profit": "#8E7DBE",
    "ROI": "#F3A06B",
}

st.markdown(
    f"""
    <style>
    .stApp {{ background: {CLOVER_BG}; }}
    section[data-testid="stSidebar"] {{ background: {CLOVER_SIDEBAR}; }}
    section[data-testid="stSidebar"] > div {{ background: {CLOVER_SIDEBAR}; }}
    .block-container {{ padding-top: 0.6rem; max-width: 1320px; }}
    h1, h2, h3 {{ color: {CLOVER_DARK}; }}
    div[data-testid="stButton"] button {{
        height: 34px !important; padding: 2px 18px !important; font-size: 13px !important;
        border-radius: 8px !important; border: none !important; background: {CLOVER_BLUE} !important;
        color: white !important; font-weight: 600 !important;
    }}
    div[data-testid="stNumberInput"] input {{
        height: 34px !important; min-height: 34px !important; font-size: 12px !important;
        text-align: right !important; padding: 0 4px !important; border: 1px solid {CLOVER_BORDER} !important;
        background: {YELLOW} !important; color: {CLOVER_DARK} !important;
    }}
    div[data-testid="stNumberInput"] button {{ display: none !important; }}
    .blue-header {{ background: {CLOVER_BLUE}; color: white; font-weight: 700; font-size: 12px;
        padding: 6px 10px; border-radius: 6px; margin-top: 8px; margin-bottom: 12px; }}
    .section-label {{ height: 30px; font-size: 14px; font-weight: 800; color: {CLOVER_DARK};
        margin-top: 14px; margin-bottom: 6px; padding-left: 10px; border-left: 5px solid {CLOVER_BLUE};
        background: {CLOVER_SOFT}; display: flex; align-items: center; border-radius: 4px; }}
    .header-cell {{ height: 24px; font-size: 12px; font-weight: 700; color: {CLOVER_DARK};
        display: flex; align-items: center; justify-content: center; background: {CLOVER_SOFT};
        border: 1px solid {CLOVER_BORDER}; }}
    .cell {{ height: 34px; border: 1px solid {CLOVER_BORDER}; padding: 4px 6px; font-size: 12px;
        display: flex; align-items: center; overflow: hidden; white-space: nowrap; background: white; color: {CLOVER_DARK}; }}
    .metric-cell {{ justify-content: flex-start; font-weight: 600; font-size: 12px; }}
    .value-cell {{ justify-content: flex-end; }}
    .readonly-cell {{ justify-content: flex-end; background: {CLOVER_SOFT}; }}
    .change-cell {{ justify-content: flex-end; background: white; }}
    .page-title-bar {{ background: #FFFFFF; border: 2px solid {CLOVER_BLUE}; border-radius: 12px;
        padding: 16px 18px; margin: 8px 0 18px 0; color: {CLOVER_DARK}; font-size: 28px;
        line-height: 34px; font-weight: 900; box-shadow: 0 2px 6px rgba(23,50,77,.08);
        position: relative; z-index: 5; clear: both; }}
    .filter-label {{ height: 30px; font-size: 13px; font-weight: 800; color: {CLOVER_DARK};
        margin-top: 6px; margin-bottom: 4px; padding-left: 10px; border-left: 5px solid {CLOVER_BLUE};
        background: {CLOVER_SOFT}; display: flex; align-items: center; border-radius: 4px; }}
    .warn-box {{ font-size: 12px; color: #8A6200; background: #FFFBEA; border: 1px solid #F8E8A0;
        padding: 7px 10px; border-radius: 7px; margin: 6px 0 8px 0; }}
    .logo-box {{
        display: flex; align-items: center; justify-content: flex-start;
        margin: 8px 0 28px 0; padding: 6px 0;
        background: transparent; border-radius: 0;
        width: fit-content; box-shadow: none;
    }}
    .logo-mark {{ width: 31px; height: 31px; border-radius: 9px; background: {CLOVER_BLUE}; color: white;
        display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 18px; }}
    .logo-text {{ font-size: 22px; font-weight: 900; color: {CLOVER_DARK}; margin-left: 9px; letter-spacing: -0.3px; }}
    .nav-btn {{ display: block; width: 100%; padding: 10px 12px; border-radius: 10px; margin-bottom: 6px;
        text-decoration: none; font-size: 15px; font-weight: 700; color: {CLOVER_DARK}; background: transparent; line-height: 20px; }}
    .nav-btn-sel {{ background: white; color: {CLOVER_BLUE} !important; font-weight: 700;
        box-shadow: 0 1px 3px rgba(23,50,77,.08); }}
    </style>
    """,
    unsafe_allow_html=True,
)


def now_string():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id():
    return str(uuid.uuid4())


def make_filter_key(row_or_dict):
    return "|".join(str(row_or_dict[col]) for col in FILTER_COLS)


def force_float_columns(df):
    df = df.copy()
    for col in df.columns:
        if col not in TEXT_COLS:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def save_csv(df, path):
    """Backward-compatible save function.

    In the Google Sheets version, path is a worksheet/tab name.
    """
    write_sheet(path, df)


def file_signature(path):
    """Google Sheets version.

    We do not use local file timestamps anymore.
    Data is loaded into Streamlit session state and updated after each save.
    Use the sidebar Reload button to refresh from Google Sheets.
    """
    return None


def sources_signature():
    return {"backend": "google_sheets"}


def sample_low_level_rows():
    return [
        {"Country": "US", "Channel": "Liquor", "Category": "COGNAC", "Sub Category": "VSOP", "Size": "375ML", "Product": "PPG1",
         "Base Price": 42.99, "Cost of Goods": 24.50, "EDLP Cost per Unit": 0.75, "Units": 1_250_000, "Promo Price": 36.99},
        {"Country": "US", "Channel": "XAOC", "Category": "COGNAC", "Sub Category": "VSOP", "Size": "375ML", "Product": "PPG2",
         "Base Price": 39.99, "Cost of Goods": 22.25, "EDLP Cost per Unit": 0.65, "Units": 2_100_000, "Promo Price": 34.49},
        {"Country": "US", "Channel": "Liquor", "Category": "COGNAC", "Sub Category": "XO", "Size": "750ML", "Product": "PPG3",
         "Base Price": 129.99, "Cost of Goods": 74.00, "EDLP Cost per Unit": 1.50, "Units": 620_000, "Promo Price": 114.99},
    ]


def create_config_from_low_level(low_rows):
    rows = []
    low_df = pd.DataFrame(low_rows)

    for _, row in low_df.iterrows():
        r = {col: row[col] for col in FILTER_COLS}
        r[LOW_LEVEL_COL] = 1
        r[KEY_COL] = make_filter_key(r)
        rows.append(r)

    for mask in range(1 << len(FILTER_COLS)):
        group_cols = [dim for i, dim in enumerate(FILTER_COLS) if mask & (1 << i)]
        if group_cols == FILTER_COLS:
            continue

        if group_cols:
            grouped = low_df.groupby(group_cols, dropna=False)
        else:
            grouped = [((), low_df)]

        for keys, _group in grouped:
            if not isinstance(keys, tuple):
                keys = (keys,)
            r = {dim: "Total" for dim in FILTER_COLS}
            for dim, value in zip(group_cols, keys):
                r[dim] = value
            r[LOW_LEVEL_COL] = 0
            r[KEY_COL] = make_filter_key(r)
            rows.append(r)

    config = pd.DataFrame(rows).drop_duplicates(subset=[KEY_COL]).sort_values(FILTER_COLS)
    return config[[KEY_COL, *FILTER_COLS, LOW_LEVEL_COL]].reset_index(drop=True)


def create_aggregation_matrix(config):
    low = config[config[LOW_LEVEL_COL] == 1].copy()
    matrix_rows = []

    for _, agg in config.iterrows():
        agg_key = agg[KEY_COL]
        matching = low.copy()
        for col in FILTER_COLS:
            if str(agg[col]) != "Total":
                matching = matching[matching[col].astype(str) == str(agg[col])]
        for _, low_row in matching.iterrows():
            matrix_rows.append({
                "Aggregation Key": agg_key,
                "Low Level Key": low_row[KEY_COL],
            })

    return pd.DataFrame(matrix_rows).drop_duplicates()


def create_coefficients(config):
    low = config[config[LOW_LEVEL_COL] == 1].copy()
    rows = []
    defaults = [
        (-1.70, -2.50, 0.70, 0.35, 0.18, 0.12, 0.25, 0.10, 0.20, 0.70, 0.45),
        (-1.45, -2.20, 0.65, 0.32, 0.16, 0.11, 0.22, 0.09, 0.18, 0.72, 0.48),
        (-1.20, -1.95, 0.60, 0.28, 0.14, 0.10, 0.20, 0.08, 0.15, 0.68, 0.42),
    ]
    for i, (_, row) in enumerate(low.iterrows()):
        vals = defaults[i % len(defaults)]
        out = {KEY_COL: row[KEY_COL], **{c: row[c] for c in FILTER_COLS}}
        for col, val in zip(COEF_COLS, vals):
            out[col] = val
        rows.append(out)
    return pd.DataFrame(rows)


def ensure_support_column(df):
    df = df.copy()

    # Backward compatibility for older scenario/source files.
    rename_map = {
        "TPR ACV": "TPR Promo Support",
        "Promo Support %": "TPR Promo Support",
        "Feature ACV": "Feature Promo Support",
        "Display ACV": "Display Promo Support",
    }
    for old_col, new_col in rename_map.items():
        if new_col not in df.columns and old_col in df.columns:
            df[new_col] = df[old_col]

    # Drop old duplicate columns after migration.
    for old_col in rename_map:
        if old_col in df.columns and old_col != rename_map[old_col]:
            df = df.drop(columns=[old_col])

    return df




def normalize_config(config):
    config = config.copy()
    # Support both ConfigKey and older Filter Key naming.
    if KEY_COL not in config.columns:
        if "Filter Key" in config.columns:
            config[KEY_COL] = config["Filter Key"]
        else:
            config[KEY_COL] = config.apply(make_filter_key, axis=1)
    if LOW_LEVEL_COL not in config.columns:
        config[LOW_LEVEL_COL] = (config["Product"].astype(str) != "Total").astype(int)
    if "PPG_ID" not in config.columns:
        config["PPG_ID"] = config["Product"].where(config[LOW_LEVEL_COL].astype(int).eq(1), "")
    config[LOW_LEVEL_COL] = pd.to_numeric(config[LOW_LEVEL_COL], errors="coerce").fillna(0).astype(int)
    keep = [KEY_COL, *FILTER_COLS, "PPG_ID", LOW_LEVEL_COL]
    return config[keep].drop_duplicates(subset=[KEY_COL]).reset_index(drop=True)


def normalize_coefficients(coefs, config):
    coefs = ensure_support_column(coefs.copy())
    rename_map = {
        "Promo Support % Coef": "Promo Support Coef",
        "TPR Promo Support Coef": "Promo Support Coef",
        "Discount x Promo Support % Coef": "Discount x Promo Support Coef",
        "Discount x TPR Promo Support Coef": "Discount x Promo Support Coef",
        "Feature Promo Support Coef": "Feature ACV Coef",
        "Display Promo Support Coef": "Display ACV Coef",
    }
    coefs = coefs.rename(columns=rename_map)

    # Preferred structure: coefficients has PPG_ID. Join it to low-level ConfigKey from config.
    if KEY_COL not in coefs.columns:
        if "Filter Key" in coefs.columns:
            coefs[KEY_COL] = coefs["Filter Key"]
        elif "PPG_ID" in coefs.columns:
            low_map = config.loc[config[LOW_LEVEL_COL].eq(1), [KEY_COL, "PPG_ID"]].drop_duplicates()
            coefs = coefs.merge(low_map, on="PPG_ID", how="left")
        else:
            # Legacy fallback: coefficients file has full filter columns.
            coefs[KEY_COL] = coefs.apply(make_filter_key, axis=1)

    for col in COEF_COLS:
        if col not in coefs.columns:
            coefs[col] = 0.0

    return coefs[[KEY_COL, *(["PPG_ID"] if "PPG_ID" in coefs.columns else []), *COEF_COLS]].drop_duplicates(subset=[KEY_COL])


def normalize_matrix(matrix, config):
    matrix = matrix.copy()
    # Support starter template: AggregateKey + PPG_ID. Convert to ConfigKey mapping.
    if "Aggregation Key" not in matrix.columns:
        if "AggregateKey" in matrix.columns:
            matrix["Aggregation Key"] = matrix["AggregateKey"]
        else:
            raise ValueError("aggregation_matrix must contain Aggregation Key or AggregateKey.")

    if "Low Level Key" not in matrix.columns:
        if "LowLevelKey" in matrix.columns:
            matrix["Low Level Key"] = matrix["LowLevelKey"]
        elif "PPG_ID" in matrix.columns:
            low_map = config.loc[config[LOW_LEVEL_COL].eq(1), [KEY_COL, "PPG_ID"]].drop_duplicates()
            matrix = matrix.merge(low_map, on="PPG_ID", how="left")
            matrix["Low Level Key"] = matrix[KEY_COL]
        else:
            raise ValueError("aggregation_matrix must contain Low Level Key, LowLevelKey, or PPG_ID.")

    return matrix[["Aggregation Key", "Low Level Key"]].dropna().drop_duplicates().reset_index(drop=True)

def load_or_create_sources():
    config = read_sheet(CONFIG_CSV)
    if config.empty:
        config = create_config_from_low_level(sample_low_level_rows())
        save_csv(config, CONFIG_CSV)
    config = normalize_config(config)

    matrix = read_sheet(AGG_MATRIX_CSV)
    if matrix.empty:
        matrix = create_aggregation_matrix(config)
        save_csv(matrix, AGG_MATRIX_CSV)
    matrix = normalize_matrix(matrix, config)

    coefs = read_sheet(COEFFICIENTS_CSV)
    if coefs.empty:
        coefs = create_coefficients(config)
        save_csv(coefs, COEFFICIENTS_CSV)
    coefs = normalize_coefficients(coefs, config)

    return config, matrix, coefs

def add_default_promo_inputs(row):
    row = row.copy()
    row["Fixed Cost"] = row.get("Fixed Cost", 50_000)
    row["Variable Cost per Unit"] = row.get("Variable Cost per Unit", 0.25)
    row["Total Weeks"] = row.get("Total Weeks", 12.0)
    row["TPR Weeks"] = row.get("TPR Weeks", 3.5)
    row["TPR Promo Support"] = row.get("TPR Promo Support", 0.55)
    row["Feature Weeks"] = row.get("Feature Weeks", 1.5)
    row["Feature Promo Support"] = row.get("Feature Promo Support", 0.25)
    row["Display Weeks"] = row.get("Display Weeks", 2.0)
    row["Display Promo Support"] = row.get("Display Promo Support", 0.30)
    row["F&D Weeks"] = row.get("F&D Weeks", 1.0)
    row["F&D ACV"] = row.get("F&D ACV", 0.18)
    return row


def create_current_low_level_base(config, coefs):
    sample = pd.DataFrame(sample_low_level_rows())
    sample[KEY_COL] = sample.apply(make_filter_key, axis=1)
    low_keys = config.loc[config[LOW_LEVEL_COL] == 1, KEY_COL].tolist()
    rows = []
    ts = now_string()

    for key in low_keys:
        cfg = config[config[KEY_COL] == key].iloc[0]
        source = sample[sample[KEY_COL] == key]
        if source.empty:
            base_price, cogs, edlp, units = 49.99, 25.00, 0.75, 500_000
        else:
            src = source.iloc[0]
            base_price, cogs, edlp, units = src["Base Price"], src["Cost of Goods"], src["EDLP Cost per Unit"], src["Units"]
        row = {"Scenario ID": new_id(), "Scenario": "Current", "Created At": ts, KEY_COL: key,
               **{col: cfg[col] for col in FILTER_COLS}, "Base Price": base_price, "Cost of Goods": cogs,
               "EDLP Cost per Unit": edlp, "Units": units}
        row["Dollars"] = row["Units"] * row["Base Price"]
        row["Cost"] = row["Units"] * (row["Cost of Goods"] + row["EDLP Cost per Unit"])
        row["Profit"] = row["Dollars"] - row["Cost"]
        row["Margin"] = (row["Base Price"] - row["Cost of Goods"]) / row["Base Price"] if row["Base Price"] else 0
        rows.append(row)

    df = pd.DataFrame(rows).merge(coefs[[KEY_COL, *COEF_COLS]], on=KEY_COL, how="left")
    return force_float_columns(df)


def create_current_low_level_promo(config, coefs):
    sample = pd.DataFrame(sample_low_level_rows())
    sample[KEY_COL] = sample.apply(make_filter_key, axis=1)
    low_keys = config.loc[config[LOW_LEVEL_COL] == 1, KEY_COL].tolist()
    rows = []
    ts = now_string()

    for key in low_keys:
        cfg = config[config[KEY_COL] == key].iloc[0]
        source = sample[sample[KEY_COL] == key]
        if source.empty:
            base_price, cogs, units, promo_price = 49.99, 25.00, 500_000, 44.99
        else:
            src = source.iloc[0]
            base_price, cogs, units, promo_price = src["Base Price"], src["Cost of Goods"], src["Units"] * 2.2, src["Promo Price"]
        row = {"Scenario ID": new_id(), "Scenario": "Current", "Created At": ts, KEY_COL: key,
               **{col: cfg[col] for col in FILTER_COLS}, "Base Price": base_price, "Cost of Goods": cogs,
               "Units": units, "Promo Price": promo_price}
        row = add_default_promo_inputs(row)
        row["Discount"] = 1 - row["Promo Price"] / row["Base Price"] if row["Base Price"] else 0
        row["Dollars"] = row["Units"] * row["Promo Price"]
        row["Spend"] = row["Fixed Cost"] + row["Units"] * row["Variable Cost per Unit"] + row["Units"] * (row["Base Price"] - row["Promo Price"])
        row["Profit"] = row["Dollars"] - row["Units"] * row["Cost of Goods"] - row["Spend"]
        row["ROI"] = row["Profit"] / row["Spend"] if row["Spend"] else 0
        row["Margin"] = (row["Base Price"] - row["Cost of Goods"]) / row["Base Price"] if row["Base Price"] else 0
        rows.append(row)

    df = pd.DataFrame(rows).merge(coefs[[KEY_COL, *COEF_COLS]], on=KEY_COL, how="left")
    return force_float_columns(df)


def get_low_level_keys(config):
    return config.loc[config[LOW_LEVEL_COL] == 1, KEY_COL].tolist()


def join_config_flags(df, config):
    flags = config[[KEY_COL, LOW_LEVEL_COL]].drop_duplicates(KEY_COL)
    out = df.drop(columns=[LOW_LEVEL_COL], errors="ignore").merge(flags, on=KEY_COL, how="left")
    out[LOW_LEVEL_COL] = pd.to_numeric(out[LOW_LEVEL_COL], errors="coerce").fillna(0).astype(int)
    return out


def aggregate_from_low_rows(agg_key, low_rows, mode, config, matrix):
    linked_keys = matrix.loc[matrix["Aggregation Key"] == agg_key, "Low Level Key"].astype(str).tolist()
    group = low_rows[low_rows[KEY_COL].astype(str).isin(linked_keys)].copy()
    if group.empty:
        return None

    cfg = config[config[KEY_COL].astype(str) == str(agg_key)].iloc[0]
    row = group.iloc[0].copy()
    row["Scenario ID"] = f"AGG_{row['Scenario']}_{agg_key}"
    row[KEY_COL] = agg_key
    for col in FILTER_COLS:
        row[col] = cfg[col]
    row[LOW_LEVEL_COL] = int(cfg[LOW_LEVEL_COL])
    row["Created At"] = group["Created At"].max()

    unit_sum = group["Units"].sum()
    row["Units"] = unit_sum
    row["Dollars"] = group["Dollars"].sum()

    if mode == "base":
        row["Cost"] = group["Cost"].sum()
        row["Profit"] = group["Profit"].sum()
        row["Base Price"] = row["Dollars"] / unit_sum if unit_sum else 0
        row["Cost of Goods"] = (group["Cost of Goods"] * group["Units"]).sum() / unit_sum if unit_sum else 0
        row["EDLP Cost per Unit"] = (group["EDLP Cost per Unit"] * group["Units"]).sum() / unit_sum if unit_sum else 0
        row["Margin"] = (row["Base Price"] - row["Cost of Goods"]) / row["Base Price"] if row["Base Price"] else 0

    if mode == "promo":
        row["Spend"] = group["Spend"].sum()
        row["Profit"] = group["Profit"].sum()
        row["Fixed Cost"] = group["Fixed Cost"].sum()
        row["Promo Price"] = row["Dollars"] / unit_sum if unit_sum else 0
        row["Base Price"] = (group["Base Price"] * group["Units"]).sum() / unit_sum if unit_sum else 0
        row["Cost of Goods"] = (group["Cost of Goods"] * group["Units"]).sum() / unit_sum if unit_sum else 0
        row["Variable Cost per Unit"] = (group["Variable Cost per Unit"] * group["Units"]).sum() / unit_sum if unit_sum else 0
        for col in [*PROMO_WEEK_COLS, *PROMO_EXPOSURE_COLS]:
            row[col] = (group[col] * group["Units"]).sum() / unit_sum if unit_sum and col in group.columns else 0
        row["Margin"] = (row["Base Price"] - row["Cost of Goods"]) / row["Base Price"] if row["Base Price"] else 0
        row["Discount"] = 1 - row["Promo Price"] / row["Base Price"] if row["Base Price"] else 0
        row["ROI"] = row["Profit"] / row["Spend"] if row["Spend"] else 0

    # Coefficients are preserved for display/debug only. They are not used for aggregated calculations.
    for col in COEF_COLS:
        if col in group.columns:
            row[col] = (group[col] * group["Units"]).sum() / unit_sum if unit_sum else group[col].mean()

    return row


def complete_low_rows_for_scenario(df, scenario_name, config):
    df = df.copy()
    low_keys = get_low_level_keys(config)
    current_low = df[(df["Scenario"] == "Current") & (df[KEY_COL].isin(low_keys))].copy()
    scenario_low = df[(df["Scenario"] == scenario_name) & (df[KEY_COL].isin(low_keys))].copy()
    existing = set(scenario_low[KEY_COL].astype(str))

    clones = []
    for _, cur in current_low.iterrows():
        if str(cur[KEY_COL]) not in existing:
            cloned = cur.copy()
            cloned["Scenario ID"] = new_id()
            cloned["Scenario"] = scenario_name
            cloned["Created At"] = now_string()
            clones.append(cloned)

    if clones:
        df = pd.concat([df, pd.DataFrame(clones)], ignore_index=True)
    return force_float_columns(df)


def rebuild_scenario_rows(df, scenario_name, mode, config, matrix):
    df = df.copy()
    low_keys = get_low_level_keys(config)

    # Remove all existing rows for this scenario, then rebuild from completed low-level rows.
    other = df[df["Scenario"] != scenario_name].copy()
    scenario_low = df[(df["Scenario"] == scenario_name) & (df[KEY_COL].isin(low_keys))].copy()
    scenario_low = scenario_low.drop_duplicates(subset=[KEY_COL], keep="last")

    rows = []
    for _, cfg in config.iterrows():
        key = cfg[KEY_COL]
        if int(cfg[LOW_LEVEL_COL]) == 1:
            match = scenario_low[scenario_low[KEY_COL].astype(str) == str(key)]
            if not match.empty:
                row = match.iloc[-1].copy()
                row[LOW_LEVEL_COL] = 1
                rows.append(row)
        else:
            agg_row = aggregate_from_low_rows(key, scenario_low, mode, config, matrix)
            if agg_row is not None:
                rows.append(agg_row)

    rebuilt = pd.DataFrame(rows)
    out = pd.concat([other, rebuilt], ignore_index=True)
    out = out.drop_duplicates(subset=["Scenario", KEY_COL], keep="last")
    out = join_config_flags(out, config)
    return force_float_columns(out)


def rebuild_all_scenarios(df, mode, config, matrix):
    df = join_config_flags(df, config)
    scenarios = df["Scenario"].dropna().astype(str).unique().tolist()
    out = df.copy()
    for scenario in scenarios:
        out = complete_low_rows_for_scenario(out, scenario, config)
        out = rebuild_scenario_rows(out, scenario, mode, config, matrix)
    return force_float_columns(out)


def load_or_create_scenario_file(path, mode, config, matrix, coefs, rebuild_existing=True):
    df = read_sheet(path)
    if not df.empty:
        df = ensure_support_column(df)
        if KEY_COL not in df.columns:
            if "Filter Key" in df.columns:
                df[KEY_COL] = df["Filter Key"]
            else:
                df[KEY_COL] = df.apply(make_filter_key, axis=1)

        # Scenario files may store only ConfigKey/PPG_ID. Bring dimensions from config.
        dim_cols_missing = [col for col in FILTER_COLS if col not in df.columns]
        if dim_cols_missing:
            df = df.merge(config[[KEY_COL, *FILTER_COLS]], on=KEY_COL, how="left")

        missing_coef_cols = [col for col in COEF_COLS if col not in df.columns]
        if missing_coef_cols:
            df = df.merge(coefs[[KEY_COL, *missing_coef_cols]], on=KEY_COL, how="left")
        df = join_config_flags(df, config)
        df = force_float_columns(df)
        if rebuild_existing:
            return rebuild_all_scenarios(df, mode, config, matrix)
        return df

    low = create_current_low_level_base(config, coefs) if mode == "base" else create_current_low_level_promo(config, coefs)
    low = join_config_flags(low, config)
    df = rebuild_scenario_rows(low, "Current", mode, config, matrix)
    save_csv(df, path)
    return df


def recalculate_base(row, current):
    row = row.copy()
    elasticity = float(row.get("Base Price Elasticity", -1.5))
    price_index = row["Base Price"] / current["Base Price"] if current["Base Price"] else 1
    row["Units"] = current["Units"] * (price_index ** elasticity)
    row["Dollars"] = row["Units"] * row["Base Price"]
    row["Cost"] = row["Units"] * (row["Cost of Goods"] + row["EDLP Cost per Unit"])
    row["Profit"] = row["Dollars"] - row["Cost"]
    row["Margin"] = (row["Base Price"] - row["Cost of Goods"]) / row["Base Price"] if row["Base Price"] else 0
    return row


def weighted_duration(weeks, week_2_decay, week_3plus_decay):
    weeks = max(float(weeks), 0.0)
    week_1 = min(weeks, 1.0)
    week_2 = min(max(weeks - 1.0, 0.0), 1.0) * float(week_2_decay)
    week_3plus = max(weeks - 2.0, 0.0) * float(week_3plus_decay)
    return week_1 + week_2 + week_3plus


def promo_exposure(row, promo_type):
    if promo_type == "Promo Support":
        week_col, support_col = "TPR Weeks", "TPR Promo Support"
    elif promo_type == "Feature":
        week_col, support_col = "Feature Weeks", "Feature Promo Support"
    elif promo_type == "Display":
        week_col, support_col = "Display Weeks", "Display Promo Support"
    else:
        week_col, support_col = f"{promo_type} Weeks", f"{promo_type} ACV"
    return float(row[support_col]) * weighted_duration(row[week_col], row["Week 2 Decay"], row["Week 3+ Decay"])


def recalculate_promo(row, current):
    row = row.copy()
    pp_elas = float(row.get("Promo Price Elasticity", -2.0))
    wk_elas = float(row.get("Total Weeks Elasticity", 0.6))

    discount = 1 - row["Promo Price"] / row["Base Price"] if row["Base Price"] else 0
    current_discount = 1 - current["Promo Price"] / current["Base Price"] if current["Base Price"] else 0

    ppi = row["Promo Price"] / current["Promo Price"] if current["Promo Price"] else 1
    wi = row["Total Weeks"] / current["Total Weeks"] if current["Total Weeks"] else 1

    support_exp = promo_exposure(row, "Promo Support")
    feature_exp = promo_exposure(row, "Feature")
    display_exp = promo_exposure(row, "Display")
    fd_exp = promo_exposure(row, "F&D")

    cur_support_exp = promo_exposure(current, "Promo Support")
    cur_feature_exp = promo_exposure(current, "Feature")
    cur_display_exp = promo_exposure(current, "Display")
    cur_fd_exp = promo_exposure(current, "F&D")

    exposure_log_lift = (
        row["Promo Support Coef"] * (support_exp - cur_support_exp)
        + row["Feature ACV Coef"] * (feature_exp - cur_feature_exp)
        + row["Display ACV Coef"] * (display_exp - cur_display_exp)
        + row["F&D ACV Coef"] * (fd_exp - cur_fd_exp)
        + row["Feature Display Interaction Coef"] * ((feature_exp * display_exp) - (cur_feature_exp * cur_display_exp))
        + row["Discount x Promo Support Coef"] * ((discount * support_exp) - (current_discount * cur_support_exp))
    )

    exec_lift = max(0.05, min(10.0, math.exp(exposure_log_lift)))
    row["Units"] = current["Units"] * (ppi ** pp_elas) * (wi ** wk_elas) * exec_lift
    row["Dollars"] = row["Units"] * row["Promo Price"]
    row["Spend"] = row["Fixed Cost"] + row["Units"] * row["Variable Cost per Unit"] + row["Units"] * (row["Base Price"] - row["Promo Price"])
    row["Profit"] = row["Dollars"] - row["Units"] * row["Cost of Goods"] - row["Spend"]
    row["ROI"] = row["Profit"] / row["Spend"] if row["Spend"] else 0
    row["Discount"] = discount
    row["Margin"] = (row["Base Price"] - row["Cost of Goods"]) / row["Base Price"] if row["Base Price"] else 0
    return row


def apply_low_level_simulation(df, scenario_name, selected_key, edited_values, mode, config, matrix, coefs):
    df = complete_low_rows_for_scenario(df, scenario_name, config)
    low_keys = set(get_low_level_keys(config))
    if selected_key not in low_keys:
        raise ValueError("This is an aggregated level. Simulation changes can only be applied at low-level PPG.")

    current = df[(df["Scenario"] == "Current") & (df[KEY_COL] == selected_key)].iloc[0].copy()
    scenario_row = df[(df["Scenario"] == scenario_name) & (df[KEY_COL] == selected_key)].iloc[-1].copy()

    for col, value in edited_values.items():
        scenario_row[col] = float(value)

    coef_row = coefs[coefs[KEY_COL].astype(str) == str(selected_key)]
    if not coef_row.empty:
        for col in COEF_COLS:
            scenario_row[col] = coef_row.iloc[0][col]

    scenario_row["Scenario"] = scenario_name
    scenario_row["Created At"] = now_string()
    scenario_row["Scenario ID"] = scenario_row.get("Scenario ID") or new_id()
    scenario_row = recalculate_base(scenario_row, current) if mode == "base" else recalculate_promo(scenario_row, current)

    mask = (df["Scenario"] == scenario_name) & (df[KEY_COL] == selected_key)
    df = df[~mask].copy()
    df = pd.concat([df, pd.DataFrame([scenario_row])], ignore_index=True)
    df = rebuild_scenario_rows(df, scenario_name, mode, config, matrix)
    return force_float_columns(df)


def fmt_value(v, vtype="number"):
    if pd.isna(v):
        return ""
    if vtype == "currency":
        return f"${v:,.2f}"
    if vtype == "currency0":
        return f"${v:,.0f}"
    if vtype == "percent":
        return f"{v:.0%}"
    if vtype == "weeks":
        return f"{v:.1f} Wks"
    if vtype == "roi":
        return f"{v:.2f}"
    return f"{v:,.1f}"


def calc_change(cur, sim):
    if cur == 0 or pd.isna(cur):
        return 0
    return sim / cur - 1


def fmt_change(v):
    return f"{v:.0%}"


def safe_ratio(numerator, denominator, default=0.0):
    if denominator is None or pd.isna(denominator) or float(denominator) == 0:
        return default
    return float(numerator) / float(denominator)


def prepare_price_inputs_for_simulation(edited, current, simulated, mode):
    """Synchronize price inputs before simulation.

    Price rows have two editable options:
    - Simulated price value
    - Change % next to the price

    If the Change % next to Base Price is edited:
        Base Price = Current Base Price × (1 + Change %)

    If the Change % next to Promo Price is edited:
        Promo Price = Current Promo Price × (1 + Change %)

    In Promo Simulator, if the Discount row is edited:
        Promo Price = Base Price × (1 − Discount)

    Discount takes priority over Promo Price Change % if both are changed.
    """
    out = dict(edited)

    base_current = float(current.get("Base Price", 0) or 0)
    base_saved = float(simulated.get("Base Price", base_current) or 0)
    base_change_saved = safe_ratio(base_saved, base_current, 1.0) - 1.0
    base_change = out.pop("__change_pct__Base Price", base_change_saved)

    if base_change is not None and abs(float(base_change) - base_change_saved) > 1e-9 and base_current:
        out["Base Price"] = base_current * (1 + float(base_change))

    if mode == "promo":
        base_price = float(out.get("Base Price", simulated.get("Base Price", current.get("Base Price", 0))) or 0)

        promo_saved = float(simulated.get("Promo Price", current.get("Promo Price", 0)) or 0)

        # Promo Price and Discount are the only editable promo-price controls.
        # If Discount changed, it drives Promo Price.
        # Otherwise, Promo Price drives final Discount.
        saved_discount = 1.0 - safe_ratio(promo_saved, base_price, 1.0)
        edited_discount = out.get("Discount", saved_discount)
        discount_changed = abs(float(edited_discount) - saved_discount) > 1e-9

        if discount_changed and base_price:
            out["Promo Price"] = base_price * (1 - float(edited_discount))

        promo_price = float(out.get("Promo Price", promo_saved) or 0)
        out["Discount"] = 1.0 - safe_ratio(promo_price, base_price, 1.0)

    return out

def get_logo_html():
    # Use text logo instead of image file so there is no white background box.
    return '<div class="logo-mark">✣</div><div class="logo-text">Cloverpop</div>'


def render_sidebar():
    st.sidebar.markdown(
        f'<div class="logo-box">{get_logo_html()}</div>',
        unsafe_allow_html=True,
    )

    st.sidebar.markdown(
        '<div style="color:#17324D;font-size:24px;font-weight:700;margin-bottom:16px;">Pages</div>',
        unsafe_allow_html=True,
    )

    if "page_selector" not in st.session_state:
        st.session_state["page_selector"] = "Base Price Simulator"

    page = st.sidebar.radio(
        "",
        ["Base Price Simulator", "Promo Simulator", "Data Sources"],
        key="page_selector",
        label_visibility="collapsed",
    )

    return page


def render_page_title(title):
    st.markdown(f'<div class="page-title-bar">{title}</div>', unsafe_allow_html=True)


def select_filter(config, col, key):
    options = sorted(config[col].dropna().astype(str).unique().tolist())
    if "Total" in options:
        options = ["Total"] + [x for x in options if x != "Total"]
    if key in st.session_state and st.session_state[key] not in options:
        del st.session_state[key]
    st.markdown(f'<div class="filter-label">{col}</div>', unsafe_allow_html=True)
    return st.selectbox(col, options, key=key, label_visibility="collapsed")


def selected_config_key(config, filters):
    match = config.copy()
    for col, value in filters.items():
        match = match[match[col].astype(str) == str(value)]
    if match.empty:
        return None, None
    row = match.iloc[0]
    return row[KEY_COL], row


def render_selector(config, scenario_df, key_prefix):
    with st.container(border=True):
        product_key = f"{key_prefix}_product"
        last_product_key = f"{key_prefix}_last_product"

        # Product/PPG is selected first. When a low-level PPG is selected,
        # the dependent filters are automatically filled from config.
        product = select_filter(config, "Product", product_key)

        if product != "Total" and st.session_state.get(last_product_key) != product:
            ppg_match = config[
                (config["Product"].astype(str) == str(product))
                & (config[LOW_LEVEL_COL].astype(int) == 1)
            ]
            if not ppg_match.empty:
                ppg_row = ppg_match.iloc[0]
                for dep_col in ["Country", "Channel", "Category", "Sub Category", "Size"]:
                    dep_key = f"{key_prefix}_{dep_col.lower().replace(' ', '_')}"
                    value = str(ppg_row[dep_col])
                    if value in config[dep_col].dropna().astype(str).unique().tolist():
                        st.session_state[dep_key] = value
            st.session_state[last_product_key] = product

        c1, c2, c3 = st.columns(3)
        with c1:
            country = select_filter(config, "Country", f"{key_prefix}_country")
            category = select_filter(config, "Category", f"{key_prefix}_category")
        with c2:
            channel = select_filter(config, "Channel", f"{key_prefix}_channel")
            sub_category = select_filter(config, "Sub Category", f"{key_prefix}_sub_category")
        with c3:
            size = select_filter(config, "Size", f"{key_prefix}_size")

        filters = {
            "Country": country,
            "Channel": channel,
            "Category": category,
            "Sub Category": sub_category,
            "Size": size,
            "Product": product,
        }
        key, cfg_row = selected_config_key(config, filters)
        if key is None:
            st.error("This filter combination is not available in config.")
            st.stop()

        scenarios = sorted([s for s in scenario_df["Scenario"].dropna().astype(str).unique().tolist() if s != "Current"])
        scenario_options = ["Current"] + scenarios
        default_scenario = scenarios[-1] if scenarios else "Current"
        selected_label = st.selectbox(
            "Select scenario",
            options=scenario_options,
            index=scenario_options.index(default_scenario),
            key=f"{key_prefix}_scenario_select",
        )
        selected_scenario = None if selected_label == "Current" else selected_label

    return key, cfg_row, selected_scenario

def get_rows_for_display(df, selected_key, selected_scenario):
    current = df[(df["Scenario"] == "Current") & (df[KEY_COL].astype(str) == str(selected_key))]
    if current.empty:
        st.error("Current baseline row is missing for the selected filter key.")
        st.stop()
    rows = [current.iloc[0].copy()]
    if selected_scenario:
        sim = df[(df["Scenario"] == selected_scenario) & (df[KEY_COL].astype(str) == str(selected_key))]
        if not sim.empty:
            rows.append(sim.iloc[0].copy())
    return pd.DataFrame(rows)


def render_scenario_actions(df, key_prefix):
    with st.container(border=True):
        c1, c2 = st.columns([1.5, 0.8])
        with c1:
            scenario_name = st.text_input("Scenario Name", value="Simulated_v2", key=f"{key_prefix}_scenario_name")
        exists = (df["Scenario"].astype(str).str.lower() == scenario_name.strip().lower()).any()
        with c2:
            st.markdown("<div style='height:21px'></div>", unsafe_allow_html=True)
            replace = False
            if exists and scenario_name.strip().lower() != "current":
                replace = st.checkbox("Replace/update existing", value=True, key=f"{key_prefix}_replace")
        run_clicked = st.button("Run Simulation", key=f"{key_prefix}_run")

    return scenario_name, exists, replace, run_clicked


def validate_name(name, exists, replace):
    name = name.strip()
    if not name:
        st.error("Scenario name cannot be empty.")
        st.stop()
    if name.lower() == "current":
        st.error("You cannot replace Current scenario.")
        st.stop()
    if exists and not replace:
        st.error("Scenario already exists. Rename it or check Replace/update existing.")
        st.stop()
    return name


def render_input_table(groups, current_row, simulated_row, editable_cols, is_low_level, key_prefix):
    edited = {}
    st.markdown('<div class="blue-header">Inputs</div>', unsafe_allow_html=True)
    h1, h2, h3, h4 = st.columns([1.65, 0.9, 0.9, 0.6])
    h1.markdown('<div class="header-cell"></div>', unsafe_allow_html=True)
    h2.markdown('<div class="header-cell">Current</div>', unsafe_allow_html=True)
    h3.markdown('<div class="header-cell">Simulated</div>', unsafe_allow_html=True)
    h4.markdown('<div class="header-cell">Change %</div>', unsafe_allow_html=True)

    for group_name, rows in groups:
        st.markdown(f'<div class="section-label">{group_name}</div>', unsafe_allow_html=True)
        for r in rows:
            col, metric, vtype, step = r["col"], r["metric"], r.get("type", "number"), r.get("step", 0.01)
            cur = current_row.get(col, 0)
            if col == "Discount":
                cur = 1.0 - safe_ratio(current_row.get("Promo Price", 0), current_row.get("Base Price", 0), 1.0)
                saved = 1.0 - safe_ratio(simulated_row.get("Promo Price", current_row.get("Promo Price", 0)), simulated_row.get("Base Price", current_row.get("Base Price", 0)), 1.0)
            else:
                saved = simulated_row.get(col, cur)
            c1, c2, c3, c4 = st.columns([1.65, 0.9, 0.9, 0.6])
            c1.markdown(f'<div class="cell metric-cell">{metric}</div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="cell value-cell">{fmt_value(cur, vtype)}</div>', unsafe_allow_html=True)

            if is_low_level and col in editable_cols:
                key = f"{key_prefix}_{simulated_row.get('Scenario', 'new')}_{simulated_row.get(KEY_COL, '')}_{col}"
                label = f"{key_prefix}_{col}"
                current_widget_value = st.session_state.get(key, float(saved))
                if abs(float(current_widget_value) - float(saved)) > 1e-9:
                    st.markdown(
                        f'<style>input[aria-label="{label}"] {{ color: {RED} !important; font-weight: 800 !important; }}</style>',
                        unsafe_allow_html=True,
                    )
                edited[col] = c3.number_input(label=label, value=float(saved), step=float(step), label_visibility="collapsed", key=key)
                sim_for_change = edited[col]
            else:
                c3.markdown(f'<div class="cell readonly-cell">{fmt_value(saved, vtype)}</div>', unsafe_allow_html=True)
                edited[col] = saved
                sim_for_change = saved

            # For price rows, Change % is editable and can drive price recalculation.
            if is_low_level and col == "Base Price":
                change_key = f"{key_prefix}_{simulated_row.get('Scenario', 'new')}_{simulated_row.get(KEY_COL, '')}_{col}_change_pct"
                change_label = f"{key_prefix}_{col}_change_pct"
                saved_change = calc_change(cur, saved)
                edited[f"__change_pct__{col}"] = c4.number_input(
                    label=change_label,
                    value=float(saved_change),
                    step=0.01,
                    label_visibility="collapsed",
                    key=change_key,
                )
            else:
                c4.markdown(f'<div class="cell change-cell">{fmt_change(calc_change(cur, sim_for_change))}</div>', unsafe_allow_html=True)
    return edited


def show_bar_chart(df, metric, title, divide_by=1, prefix="", height=95):
    if df.empty or metric not in df.columns:
        return
    chart_df = df.copy()
    chart_df[metric] = chart_df[metric] / divide_by
    fig = px.bar(chart_df, x="Scenario", y=metric, text=metric)
    fig.update_traces(texttemplate=prefix + "%{text:,.1f}", textposition="outside", marker_color=METRIC_COLORS.get(metric, CLOVER_BLUE), cliponaxis=False)
    fig.update_layout(title=dict(text=title, x=0, y=0.98, font=dict(size=11, color=CLOVER_DARK)), height=height,
                      margin=dict(l=4, r=4, t=18, b=10), showlegend=False, xaxis_title="", yaxis_title="",
                      plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF", bargap=0.35,
                      yaxis=dict(showticklabels=False, showgrid=True, gridcolor=CLOVER_BORDER, zeroline=False))
    fig.update_xaxes(tickfont=dict(size=8, color="#789"), showline=False, showgrid=False)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def create_results_table(df, metrics):
    if df.empty or len(df) < 2:
        return pd.DataFrame()
    current = df[df["Scenario"] == "Current"].iloc[0]
    rows = []
    for _, scen in df[df["Scenario"] != "Current"].iterrows():
        for metric in metrics:
            cur = current.get(metric, 0)
            sim = scen.get(metric, 0)
            rows.append({"Scenario": scen["Scenario"], "Metric": metric, "Current": cur, "Simulated": sim,
                         "Impact": sim - cur, "Vs. Current": calc_change(cur, sim)})
    return pd.DataFrame(rows)


def render_results_table(df, currency_metrics=None, height=190):
    if df.empty:
        st.info("Create or select a simulated scenario to compare against Current.")
        return
    currency_metrics = currency_metrics or []
    out = df.copy()
    numeric_impact = out["Impact"].copy()
    numeric_vs = out["Vs. Current"].copy()

    def fmt(row, col):
        val = row[col]
        if row["Metric"] in currency_metrics:
            return f"(${abs(val):,.0f})" if val < 0 else f"${val:,.0f}"
        if row["Metric"] == "ROI":
            return f"{val:.2f}"
        return f"({abs(val):,.0f})" if val < 0 else f"{val:,.0f}"

    for col in ["Current", "Simulated", "Impact"]:
        out[col] = out.apply(lambda r: fmt(r, col), axis=1)
    out["Vs. Current"] = numeric_vs.map(lambda x: f"{x:+.1%}")

    def color_positive_negative(row):
        styles = [""] * len(row)
        impact_idx = out.columns.get_loc("Impact")
        vs_idx = out.columns.get_loc("Vs. Current")
        impact_value = numeric_impact.loc[row.name]
        vs_value = numeric_vs.loc[row.name]
        styles[impact_idx] = "color: #16803C; font-weight: 600;" if impact_value > 0 else "color: #D64545; font-weight: 600;" if impact_value < 0 else ""
        styles[vs_idx] = "color: #16803C; font-weight: 600;" if vs_value > 0 else "color: #D64545; font-weight: 600;" if vs_value < 0 else ""
        return styles

    st.dataframe(out.style.apply(color_positive_negative, axis=1), hide_index=True, width="stretch", height=height)


def render_simulator_page(mode, config, matrix, coefs):
    state_key = "base_df" if mode == "base" else "promo_df"
    path = BASE_SCENARIOS_CSV if mode == "base" else PROMO_SCENARIOS_CSV
    title = "Base Price Simulator" if mode == "base" else "Promo Simulator"
    render_page_title(title)

    df = force_float_columns(st.session_state[state_key])
    selected_key, cfg_row, selected_scenario = render_selector(config, df, mode)
    is_low_level = int(cfg_row[LOW_LEVEL_COL]) == 1

    display_df = get_rows_for_display(df, selected_key, selected_scenario)
    current = display_df[display_df["Scenario"] == "Current"].iloc[0]
    simulated = display_df[display_df["Scenario"] != "Current"].iloc[0] if len(display_df) > 1 else current.copy()
    if simulated["Scenario"] == "Current":
        simulated["Scenario"] = "New Scenario"

    if not is_low_level:
        st.markdown('<div class="warn-box">This is an aggregated level. Simulation changes can only be applied at low-level PPG.</div>', unsafe_allow_html=True)

    with st.container(border=True):
        left, right = st.columns([0.43, 0.57])

        if mode == "base":
            groups = [
                ("Price", [{"metric": "Base Price", "col": "Base Price", "type": "currency", "step": 0.01}]),
                ("Financials", [{"metric": "Cost of Goods", "col": "Cost of Goods", "type": "currency", "step": 0.01},
                                {"metric": "Margin", "col": "Margin", "type": "percent"}]),
                ("Costs", [{"metric": "EDLP Cost per Unit", "col": "EDLP Cost per Unit", "type": "currency", "step": 0.01}]),
            ]
            editable_cols = BASE_EDITABLE_COLS
            result_metrics = ["Units", "Dollars", "Cost", "Profit"]
            currency_metrics = ["Dollars", "Cost", "Profit"]
        else:
            groups = [
                ("Price", [{"metric": "Base Price", "col": "Base Price", "type": "currency", "step": 0.01}]),
                ("Financials", [{"metric": "Cost of Goods", "col": "Cost of Goods", "type": "currency", "step": 0.01},
                                {"metric": "Margin", "col": "Margin", "type": "percent"}]),
                ("Promo Costs", [{"metric": "Fixed Cost", "col": "Fixed Cost", "type": "currency0", "step": 100.0},
                                 {"metric": "Variable Cost per Unit", "col": "Variable Cost per Unit", "type": "currency", "step": 0.01}]),
                ("Promotion", [{"metric": "Total Promo Weeks", "col": "Total Weeks", "type": "weeks", "step": 0.1},
                               {"metric": "TPR Weeks", "col": "TPR Weeks", "type": "weeks", "step": 0.1},
                               {"metric": "TPR Promo Support", "col": "TPR Promo Support", "type": "percent", "step": 0.01},
                               {"metric": "Feature Weeks", "col": "Feature Weeks", "type": "weeks", "step": 0.1},
                               {"metric": "Feature Promo Support", "col": "Feature Promo Support", "type": "percent", "step": 0.01},
                               {"metric": "Display Weeks", "col": "Display Weeks", "type": "weeks", "step": 0.1},
                               {"metric": "Display Promo Support", "col": "Display Promo Support", "type": "percent", "step": 0.01},
                               {"metric": "F&D Weeks", "col": "F&D Weeks", "type": "weeks", "step": 0.1},
                               {"metric": "F&D ACV", "col": "F&D ACV", "type": "percent", "step": 0.01},
                               {"metric": "Promo Price", "col": "Promo Price", "type": "currency", "step": 0.01},
                               {"metric": "Discount", "col": "Discount", "type": "percent", "step": 0.01}]),
            ]
            editable_cols = PROMO_EDITABLE_COLS
            result_metrics = ["Units", "Dollars", "Spend", "Profit", "ROI"]
            currency_metrics = ["Dollars", "Spend", "Profit"]

        with left:
            edited = render_input_table(groups, current, simulated, editable_cols, is_low_level, f"{mode}_input")
            scenario_name, exists, replace, run_clicked = render_scenario_actions(df, mode)

        with right:
            if mode == "base":
                show_bar_chart(display_df, "Units", "Units (MM)", 1_000_000, height=165)
                show_bar_chart(display_df, "Dollars", "Dollars ($MM)", 1_000_000, "$", height=165)
                show_bar_chart(display_df, "Profit", "Profit ($MM)", 1_000_000, "$", height=165)
            else:
                show_bar_chart(display_df, "Units", "Units (MM)", 1_000_000, height=118)
                show_bar_chart(display_df, "Dollars", "Dollars ($MM)", 1_000_000, "$", height=118)
                show_bar_chart(display_df, "Spend", "Spend ($MM)", 1_000_000, "$", height=118)
                show_bar_chart(display_df, "Profit", "Profit ($MM)", 1_000_000, "$", height=118)
                show_bar_chart(display_df, "ROI", "ROI", height=118)

        if run_clicked:
            name = validate_name(scenario_name, exists, replace)
            if not is_low_level:
                st.error("This is an aggregated level. Simulation changes can only be applied at low-level PPG.")
                st.stop()
            edited_values = {col: edited[col] for col in editable_cols if col in edited}
            if "__change_pct__Base Price" in edited:
                edited_values["__change_pct__Base Price"] = edited["__change_pct__Base Price"]
            edited_values = prepare_price_inputs_for_simulation(edited_values, current, simulated, mode)
            df = apply_low_level_simulation(df, name, selected_key, edited_values, mode, config, matrix, coefs)
            st.session_state[state_key] = df
            save_csv(df, path)
            if mode == "base":
                st.session_state["base_file_signature"] = file_signature(path)
            else:
                st.session_state["promo_file_signature"] = file_signature(path)
            st.success(f"Scenario '{name}' was updated at low level and all aggregation levels were rebuilt from aggregation_matrix.")
            st.rerun()

        st.markdown('<div class="blue-header">Results</div>', unsafe_allow_html=True)
        if mode == "promo":
            st.markdown(
                '<div class="warn-box">'
                '<b>Promo Spend</b> = Fixed Cost + Units × Variable Cost per Unit + Units × (Base Price − Promo Price).<br>'
                '<b>Promo Profit</b> = Dollars − Units × Cost of Goods − Promo Spend.<br>'
                '<b>ROI</b> = Promo Profit ÷ Promo Spend.'
                '</div>',
                unsafe_allow_html=True,
            )
        render_results_table(create_results_table(display_df, result_metrics), currency_metrics, height=210)


def initialize_session():
    # Streamlit reruns this file on every page click.
    # Google Sheet reads are cached in read_sheet(), and scenario data is kept
    # in st.session_state to avoid slow reloads/rebuilds during page switching.
    config, matrix, coefs = load_or_create_sources()
    current_source_sig = sources_signature()

    if st.session_state.get("source_signature") != current_source_sig:
        st.session_state["source_signature"] = current_source_sig
        st.session_state["force_rebuild_scenarios"] = True

    base_sig = file_signature(BASE_SCENARIOS_CSV)
    promo_sig = file_signature(PROMO_SCENARIOS_CSV)

    base_needs_load = (
        "base_df" not in st.session_state
        or st.session_state.get("base_file_signature") != base_sig
        or st.session_state.get("force_rebuild_scenarios", False)
    )
    promo_needs_load = (
        "promo_df" not in st.session_state
        or st.session_state.get("promo_file_signature") != promo_sig
        or st.session_state.get("force_rebuild_scenarios", False)
    )

    if base_needs_load:
        # Rebuild only on first load, file change, or source change.
        st.session_state["base_df"] = load_or_create_scenario_file(
            BASE_SCENARIOS_CSV, "base", config, matrix, coefs, rebuild_existing=True
        )
        st.session_state["base_file_signature"] = file_signature(BASE_SCENARIOS_CSV)

    if promo_needs_load:
        # Rebuild only on first load, file change, or source change.
        st.session_state["promo_df"] = load_or_create_scenario_file(
            PROMO_SCENARIOS_CSV, "promo", config, matrix, coefs, rebuild_existing=True
        )
        st.session_state["promo_file_signature"] = file_signature(PROMO_SCENARIOS_CSV)

    st.session_state["force_rebuild_scenarios"] = False
    return config, matrix, coefs


def delete_all_scenarios_keep_current():
    """Delete all saved simulated scenarios and keep only Current baseline rows."""
    for state_key, sheet_name in [
        ("base_df", BASE_SCENARIOS_CSV),
        ("promo_df", PROMO_SCENARIOS_CSV),
    ]:
        if state_key in st.session_state:
            df = st.session_state[state_key].copy()
        else:
            df = read_sheet(sheet_name)

        if df.empty or "Scenario" not in df.columns:
            continue

        current_df = df[df["Scenario"].astype(str).str.lower() == "current"].copy()
        current_df = force_float_columns(current_df)

        st.session_state[state_key] = current_df
        save_csv(current_df, sheet_name)

    st.session_state["force_rebuild_scenarios"] = False



config, matrix, coefs = initialize_session()
page = render_sidebar()

if st.sidebar.button("Delete All Scenarios"):
    delete_all_scenarios_keep_current()
    st.success("All simulated scenarios were deleted. Current baseline rows were kept.")
    st.rerun()

if page == "Base Price Simulator":
    render_simulator_page("base", config, matrix, coefs)

elif page == "Promo Simulator":
    render_simulator_page("promo", config, matrix, coefs)

elif page == "Data Sources":
    render_page_title("Data Sources")

    source_tabs = [
        "config",
        "coefficients",
        "aggregation_matrix",
        "base_price_scenarios",
        "promo_scenarios",
    ]
    tabs = st.tabs(source_tabs)

    with tabs[0]:
        st.markdown('<div class="blue-header">config</div>', unsafe_allow_html=True)
        st.dataframe(config, hide_index=True, width="stretch", height=430)

    with tabs[1]:
        st.markdown('<div class="blue-header">coefficients</div>', unsafe_allow_html=True)
        st.dataframe(coefs, hide_index=True, width="stretch", height=430)

    with tabs[2]:
        st.markdown('<div class="blue-header">aggregation_matrix</div>', unsafe_allow_html=True)
        st.dataframe(matrix, hide_index=True, width="stretch", height=430)

    with tabs[3]:
        st.markdown('<div class="blue-header">base_price_scenarios</div>', unsafe_allow_html=True)
        st.dataframe(st.session_state["base_df"], hide_index=True, width="stretch", height=430)

    with tabs[4]:
        st.markdown('<div class="blue-header">promo_scenarios</div>', unsafe_allow_html=True)
        st.dataframe(st.session_state["promo_df"], hide_index=True, width="stretch", height=430)