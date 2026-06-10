import json, re, time
from datetime import datetime
from typing import Optional
import pandas as pd
import requests
from app.config import settings

CATEGORIES = ["Food", "Shopping", "Travel", "Transport", "Utilities", "Cash Withdrawal", "Entertainment", "Other"]
DOMESTIC_ONLY = {"SWIGGY", "OLA", "IRCTC", "ZOMATO"}

def normalize_date(value: str) -> Optional[str]:
    if pd.isna(value):
        return None
    for dayfirst in (True, False):
        dt = pd.to_datetime(str(value), errors="coerce", dayfirst=dayfirst)
        if not pd.isna(dt):
            return dt.strftime("%Y-%m-%d")
    return None

def clean_amount(value) -> Optional[float]:
    if pd.isna(value):
        return None
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None

def rule_based_category(merchant: str) -> str:
    merchant = (merchant or "").upper()
    rules = {
        "SWIGGY": "Food", "ZOMATO": "Food", "STARBUCKS": "Food",
        "FLIPKART": "Shopping", "AMAZON": "Shopping", "MYNTRA": "Shopping",
        "IRCTC": "Travel", "UBER": "Transport", "OLA": "Transport",
        "BESCOM": "Utilities", "ATM": "Cash Withdrawal", "PVR": "Entertainment",
    }
    for key, value in rules.items():
        if key in merchant:
            return value
    return "Other"

def gemini_category(merchant: str, amount: float, currency: str, notes: str = "") -> tuple[str, str, bool]:
    if not settings.USE_LLM or not settings.GEMINI_API_KEY:
        return rule_based_category(merchant), "LLM disabled; used rule-based fallback", False
    prompt = f"""Classify this transaction into exactly one category: {', '.join(CATEGORIES)}.
Merchant: {merchant}; Amount: {amount}; Currency: {currency}; Notes: {notes}.
Return only the category name."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, timeout=20)
            response.raise_for_status()
            raw = response.text
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            for cat in CATEGORIES:
                if cat.lower() in text.lower():
                    return cat, raw, False
            return "Other", raw, False
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return rule_based_category(merchant), str(exc), True

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    df["date"] = df["date"].apply(normalize_date)
    df["amount"] = df["amount"].apply(clean_amount)
    df["currency"] = df["currency"].astype(str).str.upper().str.strip()
    df["status"] = df["status"].astype(str).str.upper().str.strip()
    df["merchant"] = df["merchant"].astype(str).str.strip()
    df["account_id"] = df["account_id"].astype(str).str.strip()
    df["category"] = df["category"].fillna("").astype(str).str.strip()
    df["notes"] = df["notes"].fillna("").astype(str).str.strip()
    df = df.drop_duplicates()
    return df

def detect_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["is_anomaly"] = False
    df["anomaly_reason"] = ""
    medians = df.groupby("account_id")["amount"].median().to_dict()
    for idx, row in df.iterrows():
        reasons = []
        median = medians.get(row["account_id"], 0) or 0
        if median > 0 and row["amount"] and row["amount"] > 3 * median:
            reasons.append(f"Amount exceeds 3x account median ({median:.2f})")
        if row["currency"] == "USD" and str(row["merchant"]).upper() in DOMESTIC_ONLY:
            reasons.append("USD transaction for domestic-only merchant")
        if "SUSPICIOUS" in str(row.get("notes", "")).upper():
            reasons.append("Notes contain SUSPICIOUS")
        if reasons:
            df.at[idx, "is_anomaly"] = True
            df.at[idx, "anomaly_reason"] = "; ".join(reasons)
    return df

def build_summary(df: pd.DataFrame) -> dict:
    successful = df[df["status"] == "SUCCESS"].copy()
    total_inr = float(successful.loc[successful["currency"] == "INR", "amount"].sum())
    total_usd = float(successful.loc[successful["currency"] == "USD", "amount"].sum())
    top_merchants = successful.groupby("merchant")["amount"].sum().sort_values(ascending=False).head(3)
    top = [{"merchant": k, "amount": float(v)} for k, v in top_merchants.items()]
    anomaly_count = int(df["is_anomaly"].sum())
    if anomaly_count >= 5:
        risk = "high"
    elif anomaly_count >= 2:
        risk = "medium"
    else:
        risk = "low"
    narrative = f"Processed {len(df)} cleaned transactions. Total successful spend is INR {total_inr:.2f} and USD {total_usd:.2f}. Found {anomaly_count} anomalies, so the overall risk level is {risk}."
    return {"total_spend_inr": total_inr, "total_spend_usd": total_usd, "top_merchants": top, "anomaly_count": anomaly_count, "narrative": narrative, "risk_level": risk}
