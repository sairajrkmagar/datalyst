"""
MAKE THE DEMO FILES for the video (generated data, safe to show anywhere).

    python make_demo_files.py

Creates, in ~/Desktop/video_data:
  1_retail_clean.csv           a normal file
  2_retail_messy_europe.csv    semicolons and Windows accents
  3_retail_very_messy.csv      every common data problem (for the Clean page)
"""
import os

import numpy as np
import pandas as pd

import analyst_data


def messy_retail(seed=11):
    """The retail data with the problems analysts meet every day."""

    df, _ = analyst_data.retail()
    df = df.copy()
    rng = np.random.default_rng(seed)
    n = len(df)

    def vary(series, share, kinds):
        out = series.astype(object).copy()
        pick = rng.choice(n, int(n * share), replace=False)
        for i in pick:
            value = out.iloc[i]
            if isinstance(value, str):
                kind = kinds[rng.integers(len(kinds))]
                out.iloc[i] = {"lower": value.lower(), "upper": value.upper(), "pad": f" {value} ", "tail": value + "  "}[kind]
        return out

    df["region"] = vary(df["region"], 0.18, ["lower", "upper", "pad", "tail"])
    df["category"] = vary(df["category"], 0.12, ["lower", "pad"])

    campaign = df["campaign"].astype(object)
    pick = rng.choice(n, 900, replace=False)
    for k, i in enumerate(pick):
        campaign.iloc[i] = ["N/A", "-", "null", "missing"][k % 4]
    df["campaign"] = campaign

    df["revenue_text"] = df["revenue"].map(lambda v: "\u20b9" + format(v, ",.2f") if v == v else "")
    df["internal_notes"] = np.nan
    coupon = pd.Series([None] * n, dtype=object)
    keep = rng.choice(n, int(n * 0.12), replace=False)
    coupon.iloc[keep] = "SAVE" + pd.Series(rng.integers(10, 99, len(keep)).astype(str)).values
    df["coupon_code"] = coupon
    return df


def make_all(folder=None):
    folder = folder or os.path.expanduser("~/Desktop/video_data")
    os.makedirs(folder, exist_ok=True)

    df, _ = analyst_data.retail()
    df.to_csv(folder + "/1_retail_clean.csv", index=False)

    europe = df.head(4000).copy()
    europe["remarks"] = ["Tr\u00e8s bien", "Caf\u00e9 ouvert", "OK"] * (len(europe) // 3) + ["OK"] * (len(europe) % 3)
    europe.to_csv(folder + "/2_retail_messy_europe.csv", index=False, sep=";", encoding="cp1252")

    messy_retail().to_csv(folder + "/3_retail_very_messy.csv", index=False)
    return sorted(os.listdir(folder))


if __name__ == "__main__":
    print("created:", make_all())
