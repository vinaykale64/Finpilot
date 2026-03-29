"""
Watchlist persistence via Google Sheets.
Stores and retrieves saved positions.
"""
import os
import json
from datetime import date, datetime
from typing import Optional
import gspread
from google.oauth2.service_account import Credentials

from .models import StockPosition, OptionPosition

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = ["saved_at", "type", "ticker", "shares_contracts", "cost_basis_premium",
           "strike", "expiry", "option_type", "entry_date", "pnl", "pnl_pct", "overall_analysis"]


def _get_sheet():
    """Connect to Google Sheet and return the first worksheet."""
    creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not creds_json or not sheet_id:
        return None
    try:
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(sheet_id).sheet1
        # Add headers if sheet is empty
        if sheet.row_count == 0 or not sheet.row_values(1):
            sheet.append_row(HEADERS)
        return sheet
    except Exception:
        return None


def save_position(position, pnl: Optional[float] = None, pnl_pct: Optional[float] = None, overall_analysis: str = "") -> bool:
    """Save a position to the watchlist. Returns True on success."""
    try:
        sheet = _get_sheet()
        if sheet is None:
            return False

        saved_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        pnl_str = f"{pnl:+.2f}" if pnl is not None else ""
        pnl_pct_str = f"{pnl_pct:+.1f}%" if pnl_pct is not None else ""

        if isinstance(position, StockPosition):
            row = [
                saved_at,
                "stock",
                position.ticker.upper(),
                position.shares,
                position.cost_basis,
                "",  # strike
                "",  # expiry
                "",  # option_type
                position.entry_date.isoformat() if position.entry_date else "",
                pnl_str,
                pnl_pct_str,
                overall_analysis,
            ]
        else:
            row = [
                saved_at,
                "option",
                position.ticker.upper(),
                position.contracts,
                position.premium,
                position.strike,
                position.expiry.isoformat(),
                position.option_type,
                "",
                pnl_str,
                pnl_pct_str,
                overall_analysis,
            ]

        sheet.append_row(row)
        return True
    except Exception:
        return False


def load_watchlist() -> list:
    """
    Load all saved positions from the sheet.
    Returns list of dicts with raw row data.
    """
    try:
        sheet = _get_sheet()
        if sheet is None:
            return []
        rows = sheet.get_all_records()
        return rows
    except Exception:
        return []


def delete_position(row_index: int) -> bool:
    """Delete a position by its 1-based row index (excluding header)."""
    try:
        sheet = _get_sheet()
        if sheet is None:
            return False
        sheet.delete_rows(row_index + 1)  # +1 for header row
        return True
    except Exception:
        return False


def row_to_position(row: dict) -> Optional[object]:
    """Convert a sheet row dict back to a StockPosition or OptionPosition."""
    try:
        pos_type = row.get("type", "")
        ticker = row.get("ticker", "").upper()

        if pos_type == "stock":
            return StockPosition(
                ticker=ticker,
                shares=float(row.get("shares_contracts", 1)),
                cost_basis=float(row.get("cost_basis_premium", 0)),
                entry_date=date.fromisoformat(row["entry_date"]) if row.get("entry_date") else None,
            )
        elif pos_type == "option":
            return OptionPosition(
                ticker=ticker,
                option_type=row.get("option_type", "call"),
                position="long",
                strike=float(row.get("strike", 0)),
                expiry=date.fromisoformat(row["expiry"]),
                premium=float(row.get("cost_basis_premium", 0)),
                contracts=int(row.get("shares_contracts", 1)),
            )
        return None
    except Exception:
        return None
