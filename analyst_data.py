"""
SIX REALISTIC BUSINESS DATASETS for the analyst question catalogue.

They are made by code (always the same, seeded), with the patterns real data
has: growth and seasonality, repeat customers, churn, defaults, late
deliveries, returns, blanks, repeated rows. The questions in
test_analyst_catalog.py are answered from these tables with plain pandas.

    retail     orders of an online + store retailer (customers buy repeatedly)
    hr         employees, pay, performance and attrition
    saas       software subscriptions: plans, MRR, churn, NPS
    marketing  ad campaigns: spend, clicks, conversions, revenue
    ops        shipments: carriers, modes, delays, damage
    lending    loans: amounts, credit scores, defaults

Each dataset comes with its own column-naming style (snake_case, Title Case,
camelCase ...) because real files do not agree on that either.
"""

import numpy as np
import pandas as pd


def styled(name, style):
    words = name.split("_")
    if style == "snake":
        return name
    if style == "camel":
        return words[0] + "".join(w.capitalize() for w in words[1:])
    if style == "pascal":
        return "".join(w.capitalize() for w in words)
    if style == "title":
        return " ".join(("ID" if w == "id" else w.capitalize()) for w in words)
    return name.upper()


def finish(df, style, rng):
    """Shuffle the rows, rename the columns in the dataset's style.
    Returns (dataframe, {logical name: real column name})."""

    df = df.sample(frac=1, random_state=int(rng.integers(0, 10**6))).reset_index(drop=True)
    cols = {c: styled(c, style) for c in df.columns}

    return df.rename(columns=cols), cols


def months_between(start, end):
    return pd.date_range(start, end, freq="D")


# ------------------------------------------------------------
# 1. RETAIL
# ------------------------------------------------------------

def retail(seed=11, n=12000):

    rng = np.random.default_rng(seed)
    days = months_between("2023-01-01", "2025-06-30")
    idx = np.arange(len(days))
    weight = (
        (1 + idx / len(days) * 0.9)
        * np.where(days.month.isin([11, 12]), 1.8, 1.0)
        * np.where(days.dayofweek >= 5, 1.3, 1.0)
    )
    dates = days[rng.choice(len(days), n, p=weight / weight.sum())].to_numpy()
    dates[0], dates[1] = days[0].to_datetime64(), days[-1].to_datetime64()

    n_customers = 3200
    activity = rng.lognormal(0, 1.0, n_customers)
    customer = rng.choice(n_customers, n, p=activity / activity.sum())
    segment_of = rng.choice(["Consumer", "Corporate", "Home Office"], n_customers, p=[0.55, 0.30, 0.15])
    region_of = rng.choice(["North", "South", "East", "West"], n_customers, p=[0.3, 0.25, 0.2, 0.25])
    cities = {"North": ["Delhi", "Jaipur"], "South": ["Chennai", "Bengaluru"],
              "East": ["Kolkata", "Patna"], "West": ["Mumbai", "Pune"]}

    categories = {
        "Electronics": (350, 0.78, 0.11), "Home & Kitchen": (90, 0.62, 0.06),
        "Fashion": (60, 0.55, 0.20), "Beauty": (30, 0.45, 0.05),
        "Sports": (80, 0.60, 0.07), "Toys": (25, 0.58, 0.04),
        "Grocery": (12, 0.85, 0.02), "Books": (18, 0.70, 0.03),
    }
    names = list(categories)
    category = rng.choice(names, n, p=[0.18, 0.20, 0.20, 0.10, 0.10, 0.08, 0.09, 0.05])

    product_base = {c: rng.lognormal(np.log(categories[c][0]), 0.5, 40) for c in names}
    product = np.array([rng.integers(0, 40) for _ in range(n)])
    price = np.array([product_base[c][p] for c, p in zip(category, product)]) * rng.uniform(0.97, 1.03, n)
    quantity = rng.choice([1, 2, 3, 4, 5, 6], n, p=[0.45, 0.25, 0.14, 0.08, 0.05, 0.03])
    discount = rng.choice([0, 0.05, 0.10, 0.20, 0.30], n, p=[0.55, 0.12, 0.15, 0.12, 0.06])
    revenue = (quantity * price * (1 - discount)).round(2)
    cost_ratio = np.array([categories[c][1] for c in category]) * rng.uniform(0.9, 1.1, n)
    cost = (quantity * price * cost_ratio).round(2)
    returned = np.where(rng.random(n) < np.array([categories[c][2] for c in category]), "Yes", "No")

    region = region_of[customer]
    delivery = np.clip(rng.gamma(4, 1.0, n) + np.array([{"North": 1, "South": 0, "East": 2, "West": 0}[r] for r in region]), 1, 30).round()
    delivery = delivery.astype(float)
    delivery[rng.random(n) < 0.02] = np.nan
    rating = rng.choice([1, 2, 3, 4, 5], n, p=[0.05, 0.08, 0.17, 0.35, 0.35]).astype(float)
    rating[rng.random(n) < 0.35] = np.nan
    campaign = rng.choice(["Diwali Sale", "Black Friday", "Summer Promo", "New Year", "Clearance"], n)
    campaign = np.where(rng.random(n) < 0.55, None, campaign)

    df = pd.DataFrame({
        "order_id": [f"ORD-{i:06d}" for i in range(n)],
        "order_date": pd.to_datetime(dates).strftime("%Y-%m-%d"),
        "customer_id": [f"CUST-{c:04d}" for c in customer],
        "customer_segment": segment_of[customer],
        "region": region,
        "city": [rng.choice(cities[r]) for r in region],
        "channel": rng.choice(["Online", "Store", "Marketplace", "Phone"], n, p=[0.5, 0.25, 0.2, 0.05]),
        "category": category,
        "product_id": [f"P-{c[:3].upper()}-{p:02d}" for c, p in zip(category, product)],
        "quantity": quantity,
        "unit_price": price.round(2),
        "discount_pct": (discount * 100).round(0),
        "revenue": revenue,
        "cost": cost,
        "profit": (revenue - cost).round(2),
        "payment_method": rng.choice(["Credit Card", "Debit Card", "UPI", "Cash on Delivery", "Wallet"], n, p=[0.3, 0.2, 0.3, 0.15, 0.05]),
        "returned": returned,
        "delivery_days": delivery,
        "rating": rating,
        "campaign": campaign,
    })

    df = pd.concat([df, df.sample(n // 100, random_state=seed)], ignore_index=True)    # repeated rows

    return finish(df, "snake", rng)


# ------------------------------------------------------------
# 2. HR
# ------------------------------------------------------------

def hr(seed=12, n=3000):

    rng = np.random.default_rng(seed)
    snapshot = pd.Timestamp("2025-09-30")

    department = rng.choice(["Sales", "Engineering", "Support", "Finance", "HR", "Marketing", "Operations"], n, p=[0.25, 0.22, 0.18, 0.08, 0.05, 0.10, 0.12])
    level = rng.choice(["Junior", "Mid", "Senior", "Lead", "Manager", "Director"], n, p=[0.30, 0.30, 0.20, 0.08, 0.09, 0.03])
    base = {"Junior": 35000, "Mid": 55000, "Senior": 80000, "Lead": 100000, "Manager": 120000, "Director": 170000}
    factor = {"Engineering": 1.25, "Finance": 1.1, "Sales": 1.0, "Marketing": 1.0, "Operations": 0.95, "HR": 0.95, "Support": 0.85}
    salary = np.array([base[l] * factor[d] for l, d in zip(level, department)]) * rng.uniform(0.85, 1.2, n)

    hire = pd.to_datetime("2012-01-01") + pd.to_timedelta(rng.integers(0, (snapshot - pd.Timestamp("2012-01-01")).days - 30, n), unit="D")
    overtime = np.clip(rng.gamma(2, 6, n), 0, 80).round()
    risk = 0.10 + 0.08 * (level == "Junior") + 0.06 * (department == "Support") + 0.004 * overtime + rng.normal(0, 0.03, n)
    left = rng.random(n) < np.clip(risk, 0.02, 0.6)
    spell = pd.to_timedelta((rng.gamma(2.2, 500, n)).astype(int) + 60, unit="D")
    term = pd.Series(np.where(left, (hire + spell).to_numpy(), np.datetime64("NaT")))
    term = term.where(term <= snapshot)
    left = term.notna().to_numpy()
    tenure = ((term.fillna(snapshot) - hire).dt.days / 365.25).round(2)

    df = pd.DataFrame({
        "employee_id": [f"EMP{i:05d}" for i in range(n)],
        "department": department,
        "job_level": level,
        "gender": rng.choice(["Male", "Female", "Other"], n, p=[0.52, 0.46, 0.02]),
        "age": np.clip(22 + tenure + rng.normal(8, 5, n) + 0.8 * pd.Series(level).map({"Junior": 0, "Mid": 3, "Senior": 7, "Lead": 10, "Manager": 12, "Director": 18}), 21, 64).round().astype(int),
        "location": rng.choice(["Mumbai", "Bengaluru", "Delhi", "Hyderabad", "Pune", "Remote"], n),
        "hire_date": hire.strftime("%d-%m-%Y"),
        "termination_date": term.dt.strftime("%d-%m-%Y"),
        "attrition": np.where(left, "Yes", "No"),
        "monthly_salary": salary.round(0),
        "bonus_pct": rng.choice([0, 5, 10, 15, 20], n, p=[0.2, 0.25, 0.3, 0.15, 0.1]),
        "performance_score": rng.choice([1, 2, 3, 4, 5], n, p=[0.04, 0.12, 0.44, 0.30, 0.10]),
        "engagement_score": np.clip(rng.normal(68, 15, n) - 6 * left, 5, 100).round(),
        "training_hours": rng.gamma(3, 8, n).round(1),
        "overtime_hours": overtime,
        "absent_days": rng.poisson(6, n),
        "remote_work": rng.choice(["Yes", "No"], n, p=[0.35, 0.65]),
        "tenure_years": tenure,
    })

    return finish(df, "title", rng)


# ------------------------------------------------------------
# 3. SAAS
# ------------------------------------------------------------

def saas(seed=13, n=4000):

    rng = np.random.default_rng(seed)
    snapshot = pd.Timestamp("2025-09-30")

    plan = rng.choice(["Free", "Basic", "Pro", "Enterprise"], n, p=[0.35, 0.30, 0.25, 0.10])
    price = {"Free": 0, "Basic": 29, "Pro": 99, "Enterprise": 499}
    seats = np.where(plan == "Enterprise", rng.integers(20, 200, n), rng.integers(1, 12, n))
    mrr = np.array([price[p] for p in plan]) * np.where(plan == "Enterprise", seats / 20, 1) * rng.uniform(0.9, 1.3, n)
    mrr = np.where(plan == "Free", 0, mrr).round(2)

    days = pd.date_range("2022-01-01", "2025-08-31")
    weight = 1 + np.arange(len(days)) / len(days) * 1.5
    signup = days[rng.choice(len(days), n, p=weight / weight.sum())]

    churn_p = pd.Series(plan).map({"Free": 0.40, "Basic": 0.25, "Pro": 0.15, "Enterprise": 0.08}).to_numpy()
    wants_churn = rng.random(n) < churn_p
    churn_day = signup + pd.to_timedelta(rng.integers(30, 700, n), unit="D")
    churned = wants_churn & (churn_day <= snapshot)
    churn_date = pd.Series(churn_day).where(churned)

    nps = rng.integers(0, 11, n).astype(float)
    nps = np.where(churned, np.clip(nps - 2, 0, 10), nps)
    nps[rng.random(n) < 0.5] = np.nan

    df = pd.DataFrame({
        "customer_id": [f"SUB-{i:05d}" for i in range(n)],
        "signup_date": signup.strftime("%Y-%m-%d"),
        "plan": plan,
        "billing_cycle": rng.choice(["Monthly", "Annual"], n, p=[0.7, 0.3]),
        "mrr": mrr,
        "seats": seats,
        "country": rng.choice(["India", "USA", "UK", "Germany", "Singapore", "Australia", "UAE"], n, p=[0.3, 0.25, 0.12, 0.1, 0.08, 0.08, 0.07]),
        "industry": rng.choice(["Retail", "Finance", "Healthcare", "Education", "Technology", "Manufacturing"], n),
        "acquisition_channel": rng.choice(["Organic", "Paid Search", "Referral", "Outbound", "Partner"], n, p=[0.35, 0.25, 0.15, 0.15, 0.10]),
        "usage_hours": np.where(churned, rng.gamma(1.5, 6, n), rng.gamma(3, 10, n)).round(1),
        "support_tickets": rng.poisson(np.where(churned, 4, 2), n),
        "nps_score": nps,
        "churned": np.where(churned, "Yes", "No"),
        "churn_date": churn_date.dt.strftime("%Y-%m-%d"),
    })

    return finish(df, "snake", rng)


# ------------------------------------------------------------
# 4. MARKETING
# ------------------------------------------------------------

def marketing(seed=14, n=6000):

    rng = np.random.default_rng(seed)
    campaigns = {
        "Spring Search": "Search", "Brand Search": "Search", "Retarget Social": "Social",
        "Influencer Push": "Social", "Newsletter": "Email", "Win-back Email": "Email",
        "Banner Blitz": "Display", "Video Launch": "Video", "Shopping Ads": "Search",
        "Story Ads": "Social", "Partner Display": "Display", "Webinar Invite": "Email",
    }
    names = list(campaigns)
    campaign = rng.choice(names, n)
    channel = np.array([campaigns[c] for c in campaign])
    ctr = {"Search": 0.045, "Social": 0.018, "Email": 0.028, "Display": 0.006, "Video": 0.012}
    cvr = {"Search": 0.06, "Social": 0.025, "Email": 0.05, "Display": 0.012, "Video": 0.02}
    cpc = {"Search": 1.4, "Social": 0.9, "Email": 0.15, "Display": 0.5, "Video": 0.7}

    days = pd.date_range("2024-01-01", "2025-06-30")
    day = days[rng.integers(0, len(days), n)].to_numpy()
    day[0], day[1] = days[0].to_datetime64(), days[-1].to_datetime64()

    impressions = rng.lognormal(10.5, 0.6, n).astype(int)
    clicks = rng.binomial(impressions, [ctr[c] for c in channel])
    conversions = rng.binomial(clicks, [cvr[c] for c in channel])
    spend = (clicks * np.array([cpc[c] for c in channel]) * rng.uniform(0.8, 1.2, n)).round(2)
    revenue = (conversions * rng.uniform(40, 220, n)).round(2)

    df = pd.DataFrame({
        "date": pd.to_datetime(day).strftime("%Y-%m-%d"),
        "campaign": campaign,
        "channel": channel,
        "region": rng.choice(["North America", "Europe", "Asia", "Latin America"], n, p=[0.35, 0.25, 0.3, 0.1]),
        "impressions": impressions,
        "clicks": clicks,
        "conversions": conversions,
        "spend": spend,
        "revenue": revenue,
    })

    return finish(df, "camel", rng)


# ------------------------------------------------------------
# 5. OPS (logistics)
# ------------------------------------------------------------

def ops(seed=15, n=5000):

    rng = np.random.default_rng(seed)
    cities = ["Mumbai", "Delhi", "Chennai", "Kolkata", "Bengaluru", "Hyderabad", "Pune", "Ahmedabad"]
    mode = rng.choice(["Road", "Rail", "Air", "Sea"], n, p=[0.55, 0.15, 0.2, 0.10])
    speed = {"Road": 450, "Rail": 350, "Air": 1800, "Sea": 250}
    rate = {"Road": 1.2, "Rail": 0.8, "Air": 6.0, "Sea": 0.6}
    origin = rng.choice(cities, n)
    destination = np.array([rng.choice([c for c in cities if c != o]) for o in origin])
    distance = rng.integers(150, 2500, n)
    weight = rng.lognormal(5, 1.0, n).round(1)

    days = pd.date_range("2024-01-01", "2025-06-30")
    ship = days[rng.integers(0, len(days), n)].to_numpy()
    ship[0], ship[1] = days[0].to_datetime64(), days[-1].to_datetime64()

    promised = np.maximum(1, np.ceil(distance / np.array([speed[m] for m in mode]) * 24 / 24 + 1)).astype(int)
    late = rng.gamma(1.5, 1.2, n) * (rng.random(n) < 0.35)
    delay = np.round(late - rng.choice([0, 0, 1], n)).astype(int)
    delay = np.maximum(delay, -1)
    delivery = pd.to_datetime(ship) + pd.to_timedelta(promised + delay, unit="D")

    df = pd.DataFrame({
        "shipment_id": [f"SHP-{i:06d}" for i in range(n)],
        "ship_date": pd.to_datetime(ship).strftime("%Y-%m-%d"),
        "delivery_date": delivery.strftime("%Y-%m-%d"),
        "origin": origin,
        "destination": destination,
        "carrier": rng.choice(["BlueDart", "Delhivery", "DTDC", "FedEx", "Gati"], n, p=[0.25, 0.3, 0.15, 0.2, 0.1]),
        "mode": mode,
        "priority": rng.choice(["Standard", "Express", "Economy"], n, p=[0.6, 0.25, 0.15]),
        "weight_kg": weight,
        "distance_km": distance,
        "cost": (distance * np.array([rate[m] for m in mode]) * np.power(weight, 0.3) * rng.uniform(0.9, 1.15, n)).round(2),
        "promised_days": promised,
        "delay_days": delay,
        "on_time": np.where(delay <= 0, "Yes", "No"),
        "damaged": np.where(rng.random(n) < 0.03, "Yes", "No"),
    })

    return finish(df, "snake", rng)


# ------------------------------------------------------------
# 6. LENDING
# ------------------------------------------------------------

def lending(seed=16, n=5000):

    rng = np.random.default_rng(seed)
    purpose = rng.choice(["Home", "Auto", "Education", "Business", "Personal"], n, p=[0.25, 0.2, 0.15, 0.15, 0.25])
    scale = {"Home": 300000, "Auto": 80000, "Education": 50000, "Business": 150000, "Personal": 20000}
    amount = np.array([rng.lognormal(np.log(scale[p]), 0.5) for p in purpose]).round(-2)
    score = np.clip(rng.normal(660, 85, n), 300, 850).round().astype(int)
    interest = np.clip(24 - (score - 300) / 550 * 16 + rng.normal(0, 1.2, n), 5, 28).round(2)
    income = rng.lognormal(np.log(60000), 0.5, n).round(-2)
    dti = np.clip(amount / np.maximum(income, 1) * rng.uniform(0.05, 0.25, n), 0.01, 1.2).round(3)

    risk = 1 / (1 + np.exp((score - 560) / 55)) + 0.15 * (dti > 0.3) + 0.03 * (purpose == "Business")
    outcome = rng.random(n)
    status = np.where(outcome < np.clip(risk * 0.7, 0.01, 0.8), "Default", np.where(rng.random(n) < 0.45, "Paid", "Active"))

    days = pd.date_range("2021-01-01", "2025-06-30")
    origination = days[rng.integers(0, len(days), n)].to_numpy()
    origination[0], origination[1] = days[0].to_datetime64(), days[-1].to_datetime64()

    df = pd.DataFrame({
        "loan_id": [f"LN-{i:06d}" for i in range(n)],
        "origination_date": pd.to_datetime(origination).strftime("%m/%d/%Y"),
        "purpose": purpose,
        "region": rng.choice(["North", "South", "East", "West"], n),
        "loan_amount": amount,
        "term_months": rng.choice([12, 24, 36, 60, 120], n, p=[0.1, 0.2, 0.3, 0.25, 0.15]),
        "interest_rate": interest,
        "credit_score": score,
        "annual_income": income,
        "debt_to_income": dti,
        "employment_years": np.clip(rng.gamma(2, 3, n), 0, 40).round(1),
        "status": status,
    })

    return finish(df, "pascal", rng)


BUILDERS = {
    "retail": retail, "hr": hr, "saas": saas,
    "marketing": marketing, "ops": ops, "lending": lending,
}


def make_all():
    """{name: (dataframe, {logical column: real column name})}"""
    return {name: build() for name, build in BUILDERS.items()}


if __name__ == "__main__":
    for name, (df, cols) in make_all().items():
        print(f"{name:10s} {len(df):6,d} rows x {len(df.columns):2d} columns   e.g. {list(df.columns)[:4]}")