"""Write the fictional plan catalogue to ``data/raw/plans.csv``.

Every name and price here is invented for the demo. The catalogue is static, so
the output is identical on every run.

Usage:
    python -m data_gen.plans [--out data/raw/plans.csv]
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Literal

DEFAULT_OUT = Path("data/raw/plans.csv")

Kind = Literal["plan", "addon", "fee"]
BillingPeriod = Literal["monthly", "daily", "one_time"]


@dataclass(frozen=True)
class PlanRow:
    """One row of the catalogue: a plan, an add-on or a fee."""

    plan_id: str
    kind: Kind
    name: str
    # Price in USD for one `billing_period`.
    monthly_price_usd: float
    billing_period: BillingPeriod
    # Empty means unlimited for a plan, and not applicable for add-ons and fees.
    data_gb: float | None
    talk_text: str
    hotspot_gb: float | None
    international: str
    notes: str


PLANS: tuple[PlanRow, ...] = (
    PlanRow(
        "P01", "plan", "Northline Talk", 15.00, "monthly", 0, "Unlimited talk and text", 0,
        "Not included", "Talk and text only. No mobile data.",
    ),
    PlanRow(
        "P02", "plan", "Northline Starter 1", 20.00, "monthly", 1, "Unlimited talk and text", 0,
        "Not included", "1 GB of data. Good for email and maps.",
    ),
    PlanRow(
        "P03", "plan", "Northline Everyday 5", 25.00, "monthly", 5, "Unlimited talk and text", 0,
        "Not included", "5 GB of data.",
    ),
    PlanRow(
        "P04", "plan", "Northline Plus 10", 35.00, "monthly", 10, "Unlimited talk and text", 2,
        "Calls to Canada and Mexico", "10 GB of data. 2 GB can be used as a hotspot.",
    ),
    PlanRow(
        "P05", "plan", "Northline Extra 20", 45.00, "monthly", 20, "Unlimited talk and text", 5,
        "Calls to Canada and Mexico", "20 GB of data. 5 GB can be used as a hotspot.",
    ),
    PlanRow(
        "P06", "plan", "Northline Unlimited Essentials", 50.00, "monthly", None,
        "Unlimited talk and text", 5, "Calls to Canada and Mexico",
        "Unlimited data. Speeds may slow after 35 GB in a month.",
    ),
    PlanRow(
        "P07", "plan", "Northline Unlimited Premium", 65.00, "monthly", None,
        "Unlimited talk and text", 30, "Calls and roaming in Canada and Mexico",
        "Unlimited data. Speeds may slow after 60 GB in a month.",
    ),
    PlanRow(
        "P08", "plan", "Northline Two-Line Unlimited", 80.00, "monthly", None,
        "Unlimited talk and text", 10, "Calls to Canada and Mexico",
        "Two lines sharing unlimited data. Price is for both lines together.",
    ),
    PlanRow(
        "A01", "addon", "Extra Line", 15.00, "monthly", None, "Same as the main plan", None,
        "Same as the main plan", "Adds one more line to any plan except Two-Line Unlimited.",
    ),
    PlanRow(
        "A02", "addon", "International Day Pass", 10.00, "daily", None,
        "Use your plan abroad", None, "Over 100 countries",
        "Charged only on days you use the phone outside the United States.",
    ),
    PlanRow(
        "A03", "addon", "International Calling Pack", 5.00, "monthly", None,
        "300 minutes to 60 countries", None, "Calls from the United States to 60 countries",
        "For calling other countries from home.",
    ),
    PlanRow(
        "A04", "addon", "Hotspot Boost", 10.00, "monthly", None, "", 10, "",
        "Adds 10 GB of hotspot data each month.",
    ),
    PlanRow(
        "A05", "addon", "Device Protection", 9.00, "monthly", None, "", None, "",
        "Covers loss, theft and damage. A deductible applies to each claim.",
    ),
    PlanRow(
        "A06", "addon", "Data Top-Up 5", 10.00, "one_time", 5, "", None, "",
        "Adds 5 GB of data that lasts until the end of the billing month.",
    ),
    PlanRow(
        "F01", "fee", "Activation Fee", 35.00, "one_time", None, "", None, "",
        "Charged once for each new line.",
    ),
    PlanRow(
        "F02", "fee", "Late Payment Fee", 5.00, "one_time", None, "", None, "",
        "Charged when a bill is more than 10 days past due.",
    ),
    PlanRow(
        "F03", "fee", "SIM Replacement Fee", 10.00, "one_time", None, "", None, "",
        "Charged for a replacement SIM card. eSIM replacements are free.",
    ),
    PlanRow(
        "F04", "fee", "Paper Bill Fee", 2.00, "monthly", None, "", None, "",
        "Charged for a mailed paper bill. Email bills are free.",
    ),
)  # fmt: skip


def write_plans(out_path: Path) -> int:
    """Write the catalogue as CSV and return the number of rows written."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[field.name for field in fields(PlanRow)])
        writer.writeheader()
        for row in PLANS:
            record = asdict(row)
            record["monthly_price_usd"] = f"{row.monthly_price_usd:.2f}"
            # csv writes None as an empty field, which is the "unlimited / n.a." marker.
            writer.writerow(record)
    return len(PLANS)


def main(argv: list[str] | None = None) -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    count = write_plans(args.out)
    print(f"wrote {count} rows to {args.out}")


if __name__ == "__main__":
    main()
