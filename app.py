from fastapi import FastAPI
from pydantic import BaseModel
import requests
import json
import pandas as pd
import re

app = FastAPI()

# Input format required by the grader
class QuestionRequest(BaseModel):
    question: str

# 1. BASE API CONFIGURATION (Copied from your unique links)
EXPORT_URL = "https://exam.sanand.workers.dev/questionData?email=24f2000362%40ds.study.iitm.ac.in&quizSign=CGw%2Br9XH7GxePtG50VRXFfCiF64ff26FLD56Hi0XZAoOoN3AyoA537R04gkcYRRwINJ6%2BAQaEN%2FVYHkUrEJFwPsoUlUJJq0TvQBaT90LZUz9vcHNabN0TZizLX5vKO8XmhT4Jp52ZjE%2FqjqGg4HNBbPwWo3v6Hyy66s8HQrOVyamAKCLjlSs4dePeZQaqfNz1ebZdlR%2BTuq7ABOwU%2BubpOLnizvsG10SawyZG670I%2B8DthmusLHNHCn0pEBYOrrr9ZXdR60NZzz3NAmdibYdAmJekM5dxphbj6DQqpQGx1kDgEciYUmOFC0D%2BzjNh17B%2Bz2SgxcOPiihtb6O0kJRBw%3D%3D&questionId=q-ledger-agent-server&path=%2Fexport"
RATES_URL = "https://exam.sanand.workers.dev/questionData?email=24f2000362%40ds.study.iitm.ac.in&quizSign=CGw%2Br9XH7GxePtG50VRXFfCiF64ff26FLD56Hi0XZAoOoN3AyoA537R04gkcYRRwINJ6%2BAQaEN%2FVYHkUrEJFwPsoUlUJJq0TvQBaT90LZUz9vcHNabN0TZizLX5vKO8XmhT4Jp52ZjE%2FqjqGg4HNBbPwWo3v6Hyy66s8HQrOVyamAKCLjlSs4dePeZQaqfNz1ebZdlR%2BTuq7ABOwU%2BubpOLnizvsG10SawyZG670I%2B8DthmusLHNHCn0pEBYOrrr9ZXdR60NZzz3NAmdibYdAmJekM5dxphbj6DQqpQGx1kDgEciYUmOFC0D%2BzjNh17B%2Bz2SgxcOPiihtb6O0kJRBw%3D%3D&questionId=q-ledger-agent-server&path=%2Frates"

def get_exchange_rates():
    """Fetches the latest live exchange rates to USD."""
    res = requests.get(RATES_URL)
    return res.json().get("usd_per_unit", {"USD": 1.0, "EUR": 1.06, "INR": 0.01228})

def fetch_and_clean_ledger():
    """Fetches the entire dataset via /export, deduplicates, and standardizes currencies."""
    # Fetch currency conversion rates
    rates = get_exchange_rates()
    
    # Download the whole ledger data stream
    response = requests.get(EXPORT_URL)
    
    # Parse Newline-Delimited JSON (NDJSON) lines into dictionary records
    records = []
    for line in response.text.strip().split("\n"):
        if line.strip():
            records.append(json.loads(line))
            
    df = pd.DataFrame(records)
    
    # Clean Dates: Convert to datetime and enforce Asia/Kolkata business timezone
    df["updated_at"] = pd.to_datetime(df["updated_at"], utc=True).dt.tz_convert("Asia/Kolkata")
    
    # Deduplicate: Keep only the row with the absolute latest updated_at per order id
    df = df.sort_values("updated_at").drop_duplicates(subset=["id"], keep="last")
    
    # Normalize Revenue: Calculate absolute values in USD per row using live rates
    def convert_to_usd(row):
        currency = row["currency"]
        multiplier = rates.get(currency, 1.0)
        return row["amount"] * multiplier

    df["amount_usd"] = df.apply(convert_to_usd, axis=1)
    return df

def parse_and_answer(question: str, df: pd.DataFrame) -> str:
    """Handles both counts and revenue calculations for paid, refunded, or void orders."""
    q = question.lower()
    
    # Month mapping helper
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
    }
    
    # 1. Extract Date Constraints
    target_month = next((m_num for m_name, m_num in months.items() if m_name in q), None)
    target_year = next((int(yr) for str_yr in re.findall(r"\b\d{4}\b", q) if (yr := int(str_yr))), None)
    
    # 2. Extract Region Constraint
    target_region = next((reg for reg in ["north", "south", "east", "west", "central"] if reg in q), None)
    
    # 3. Extract Status Constraint (paid, refunded, void)
    target_status = "paid"  # default standard
    if "refund" in q:
        target_status = "refunded"
    elif "void" in q:
        target_status = "void"

    # Apply Filters to the Dataframe
    filtered_df = df.copy()
    
    if target_status:
        filtered_df = filtered_df[filtered_df["status"] == target_status]
        
    if target_region:
        filtered_df = filtered_df[filtered_df["region"].str.lower() == target_region]
        
    if target_month and target_year:
        filtered_df = filtered_df[
            (filtered_df["updated_at"].dt.month == target_month) & 
            (filtered_df["updated_at"].dt.year == target_year)
        ]
        
    # 4. Check if the question asks to "Count" things or calculate "Revenue"
    if "count" in q or "how many" in q:
        # Returns the total number of orders matching the criteria as an integer string
        return str(len(filtered_df))
    else:
        # Returns total revenue sum formatted to two decimal points
        total_revenue = filtered_df["amount_usd"].sum()
        return f"{total_revenue:.2f}"

@app.post("/answer")
async def answer_endpoint(payload: QuestionRequest):
    try:
        # Load and execute fresh calculation pipeline per question request
        df = fetch_and_clean_ledger()
        result = parse_and_answer(payload.question, df)
        return {"answer": result}
    except Exception as e:
        return {"answer": "0.00"}

if __name__ == "__main__":
    import uvicorn
    # Local runtime deployment server configuration loop mapping
    uvicorn.run(app, host="0.0.0.0", port=8000)
