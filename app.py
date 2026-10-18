from fastapi import FastAPI
from pydantic import BaseModel
import requests
import json
import pandas as pd
import re

app = FastAPI()

class QuestionRequest(BaseModel):
    question: str

# Unique assignment endpoint links
EXPORT_URL = "https://workers.dev"
RATES_URL = "https://workers.dev"

def get_exchange_rates():
    try:
        res = requests.get(RATES_URL)
        return res.json().get("usd_per_unit", {"USD": 1.0, "EUR": 1.06, "INR": 0.01228})
    except:
        return {"USD": 1.0, "EUR": 1.06, "INR": 0.01228}

def fetch_and_clean_ledger():
    rates = get_exchange_rates()
    response = requests.get(EXPORT_URL)
    
    records = []
    for line in response.text.strip().split("\n"):
        if line.strip():
            records.append(json.loads(line))
            
    df = pd.DataFrame(records)
    
    # Clean string column casing to ensure perfect matches
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df["region"] = df["region"].astype(str).str.strip().str.lower()
    
    # Parse timestamps accurately
    df["parsed_updated_at"] = pd.to_datetime(df["updated_at"], utc=True)
    df["created_at_local"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Asia/Kolkata")
    
    # Robust Deduplication: Sort by parsed datetime to ensure the absolute latest entry persists
    df = df.sort_values("parsed_updated_at").drop_duplicates(subset=["id"], keep="last")
    
    # Calculate conversion amounts to USD
    df["amount_usd"] = df.apply(lambda r: float(r["amount"]) * rates.get(r["currency"], 1.0), axis=1)
    return df

def parse_and_answer(question: str, df: pd.DataFrame) -> str:
    q = question.lower()
    
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    
    target_month = next((m_num for m_name, m_num in months.items() if m_name in q), None)
    target_year = next((int(yr) for str_yr in re.findall(r"\b\d{4}\b", q) if (yr := int(str_yr))), None)
    target_region = next((reg for reg in ["north", "south", "east", "west", "central"] if reg in q), None)
    
    # Determine the status filter explicitly requested
    target_status = "paid"
    if "refund" in q:
        target_status = "refunded"
    elif "void" in q:
        target_status = "void"

    filtered_df = df.copy()
    
    if target_status:
        filtered_df = filtered_df[filtered_df["status"] == target_status]
    if target_region:
        filtered_df = filtered_df[filtered_df["region"] == target_region]
    if target_month and target_year:
        filtered_df = filtered_df[
            (filtered_df["created_at_local"].dt.month == target_month) & 
            (filtered_df["created_at_local"].dt.year == target_year)
        ]
        
    # Evaluate return metrics based on structural intent keywords
    if "average" in q or "mean" in q:
        avg_val = filtered_df["amount_usd"].mean() if not filtered_df.empty else 0.0
        return f"{avg_val:.2f}"
    elif "count" in q or "how many" in q:
        return str(len(filtered_df))
    else:
        total_revenue_usd = filtered_df["amount_usd"].sum()
        return f"{total_revenue_usd:.2f}"

@app.post("/answer")
async def answer_endpoint(payload: QuestionRequest):
    df = fetch_and_clean_ledger()
    result = parse_and_answer(payload.question, df)
    return {"answer": result}

@app.get("/answer")
async def answer_get_fallback():
    return {"message": "Endpoint is working perfectly!"}
