
import csv
import random
import uuid
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# FinTrust synthetic transaction dataset generator
# Period: 1 July - 30 September 2026
# Total: 250 transactions
# ---------------------------------------------------------

random.seed(20261013)

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "data" / "seed" / "fintrust_transactions_250.csv"
SQL_PATH = ROOT / "sql" / "fintrust_transactions_250_seed.sql"

SA_TZ = ZoneInfo("Africa/Johannesburg")
NAMESPACE = uuid.UUID("b5f8e7d2-4c91-4a63-9d20-8f1c6a3e7b52")

ACCOUNTS = [
    ("Aiden Jacobs", "4f8c2a61-7d39-45b0-a216-9e5f3c81d704"),
    ("Amara Naidoo", "f62a8c15-3d97-4e40-b251-9a6f1c83d507"),
    ("Bongani Sithole", "3a6f9d21-5c84-47b0-a193-8e2d6f71c405"),
    ("Kagiso Molefe", "5b9e2d71-4a83-46c0-9f15-7d3a8e62b409"),
    ("Lerato Nkosi", "8a3f1d72-5c96-4e20-b841-9d7a6f32c508"),
    ("Mia van der Merwe", "e5c18a72-3d49-46b0-9f21-7a6c2d85b304"),
    ("Naledi Khumalo", "c3a71e95-6d28-4f40-b183-9a5e2d76c014"),
    ("Priya Pillay", "d72b4e19-8c53-41a6-9f20-3d7e5b81c604"),
    ("Ruan Botha", "7e4b1c82-9a35-46d0-b217-5f8c3e61a904"),
    ("Sipho Dlamini", "1d7c9a43-8e25-4b61-a390-6f2d5c81e704"),
    ("Thabo Mokoena", "2c8e51a7-9f34-46d1-b820-7a5e3c91d604"),
    ("Zanele Ndlovu", "a91d5f36-2c74-4e80-b163-7a9c5d21f408"),
]

ACCOUNT_IDS = [account_id for _, account_id in ACCOUNTS]

SALARY_RANGES = {
    "Aiden Jacobs": (18500, 24500),
    "Amara Naidoo": (22000, 29000),
    "Bongani Sithole": (14500, 19500),
    "Kagiso Molefe": (19000, 26000),
    "Lerato Nkosi": (17000, 23000),
    "Mia van der Merwe": (24000, 32000),
    "Naledi Khumalo": (15500, 21000),
    "Priya Pillay": (21000, 28500),
    "Ruan Botha": (26000, 35000),
    "Sipho Dlamini": (16000, 22000),
    "Thabo Mokoena": (18000, 25000),
    "Zanele Ndlovu": (20000, 27000),
}

ORDINARY_ACTIVITIES = [
    ("PURCHASE", 45, 180, "ZA"),
    ("PURCHASE", 120, 450, "ZA"),
    ("PURCHASE", 250, 850, "ZA"),
    ("PURCHASE", 500, 1500, "ZA"),
    ("PAYMENT", 350, 1800, "ZA"),
    ("PAYMENT", 450, 2200, "ZA"),
    ("TRANSFER", 100, 1200, "ZA"),
    ("TRANSFER", 300, 2500, "ZA"),
    ("WITHDRAWAL", 200, 1500, "ZA"),
    ("WITHDRAWAL", 300, 2500, "ZA"),
    ("DEPOSIT", 200, 2500, "ZA"),
]

CROSS_BORDER_COUNTRIES = ["GB", "US", "AE", "DE", "NL"]

COLUMNS = [
    "transaction_id",
    "account_id",
    "tx_date",
    "amount",
    "currency",
    "transaction_type",
    "source_country",
    "destination_country",
]


def make_timestamp(day, hour=None, minute=None, second=None):
    """Create a South African local timestamp."""
    if hour is None:
        hour = random.randint(7, 21)
    if minute is None:
        minute = random.randint(0, 59)
    if second is None:
        second = random.randint(0, 59)

    return datetime.combine(
        day,
        time(hour, minute, second),
        tzinfo=SA_TZ,
    )


def make_transaction(
    account_id,
    tx_date,
    amount,
    transaction_type,
    destination="ZA",
):
    transaction_number = len(transactions) + 1

    transaction_id = str(
        uuid.uuid5(NAMESPACE, f"fintrust-transaction-{transaction_number}")
    )

    return {
        "transaction_id": transaction_id,
        "account_id": account_id,
        "tx_date": tx_date.isoformat(timespec="seconds"),
        "amount": f"{Decimal(str(amount)).quantize(Decimal('0.01')):.2f}",
        "currency": "ZAR",
        "transaction_type": transaction_type,
        "source_country": "ZA",
        "destination_country": destination,
    }


transactions = []


# ---------------------------------------------------------
# 1. Recurring salary deposits: 12 customers x 3 months
# Total: 36 transactions
# ---------------------------------------------------------

salary_dates = [
    date(2026, 7, 25),
    date(2026, 8, 25),
    date(2026, 9, 25),
]

for name, account_id in ACCOUNTS:
    minimum, maximum = SALARY_RANGES[name]
    base_salary = random.randint(minimum, maximum)

    for month_index, salary_day in enumerate(salary_dates):
        variation = random.uniform(-0.015, 0.015)
        salary_amount = round(base_salary * (1 + variation), 2)

        # Salaries are deposited in the morning.
        timestamp = make_timestamp(
            salary_day,
            hour=7,
            minute=random.randint(0, 45),
            second=random.randint(0, 59),
        )

        transactions.append(
            make_transaction(
                account_id,
                timestamp,
                salary_amount,
                "DEPOSIT",
            )
        )


# ---------------------------------------------------------
# 2. Ordinary everyday banking activity
# Total: 180 transactions
# ---------------------------------------------------------

start_date = date(2026, 7, 1)
end_date = date(2026, 9, 30)
date_range_days = (end_date - start_date).days

for _ in range(180):
    account_id = random.choice(ACCOUNT_IDS)

    activity_type, minimum, maximum, destination = random.choice(
        ORDINARY_ACTIVITIES
    )

    transaction_day = start_date + timedelta(
        days=random.randint(0, date_range_days)
    )

    timestamp = make_timestamp(transaction_day)
    amount = round(random.uniform(minimum, maximum), 2)

    transactions.append(
        make_transaction(
            account_id,
            timestamp,
            amount,
            activity_type,
            destination,
        )
    )


# ---------------------------------------------------------
# 3. Deliberate high-velocity activity
# Total: 13 transactions
#
# All 13 occur within one hour on the same account.
# This creates a clear >10 transactions/hour scenario.
# ---------------------------------------------------------

velocity_account = ACCOUNT_IDS[0]
velocity_start = make_timestamp(
    date(2026, 8, 18),
    hour=14,
    minute=5,
    second=0,
)

for index in range(13):
    timestamp = velocity_start + timedelta(minutes=index * 4)

    amount = round(random.uniform(180, 1450), 2)

    transactions.append(
        make_transaction(
            velocity_account,
            timestamp,
            amount,
            random.choice(["PURCHASE", "PAYMENT", "TRANSFER"]),
        )
    )


# ---------------------------------------------------------
# 4. High-value transactions
# Total: 4 transactions
#
# All are local transactions exceeding R50,000.
# ---------------------------------------------------------

high_value_events = [
    (ACCOUNT_IDS[1], date(2026, 7, 14), 68500, "TRANSFER"),
    (ACCOUNT_IDS[4], date(2026, 8, 11), 92500, "PAYMENT"),
    (ACCOUNT_IDS[8], date(2026, 9, 9), 57500, "TRANSFER"),
    (ACCOUNT_IDS[10], date(2026, 9, 22), 118000, "PAYMENT"),
]

for account_id, transaction_day, amount, transaction_type in high_value_events:
    transactions.append(
        make_transaction(
            account_id,
            make_timestamp(transaction_day, hour=11),
            amount,
            transaction_type,
        )
    )


# ---------------------------------------------------------
# 5. Cross-border activity
# Total: 8 transactions
#
# Lower-value international transactions, separate from
# the high-value scenario.
# ---------------------------------------------------------

cross_border_events = [
    (ACCOUNT_IDS[2], date(2026, 7, 8), 899, "PURCHASE", "GB"),
    (ACCOUNT_IDS[5], date(2026, 7, 26), 1450, "PAYMENT", "US"),
    (ACCOUNT_IDS[7], date(2026, 8, 3), 2350, "PURCHASE", "DE"),
    (ACCOUNT_IDS[9], date(2026, 8, 19), 780, "PAYMENT", "GB"),
    (ACCOUNT_IDS[0], date(2026, 8, 28), 3200, "TRANSFER", "AE"),
    (ACCOUNT_IDS[3], date(2026, 9, 5), 1150, "PURCHASE", "NL"),
    (ACCOUNT_IDS[6], date(2026, 9, 17), 1890, "PAYMENT", "US"),
    (ACCOUNT_IDS[11], date(2026, 9, 27), 2650, "TRANSFER", "GB"),
]

for account_id, transaction_day, amount, transaction_type, destination in cross_border_events:
    transactions.append(
        make_transaction(
            account_id,
            make_timestamp(transaction_day, hour=13),
            amount,
            transaction_type,
            destination,
        )
    )


# ---------------------------------------------------------
# 6. Additional ordinary activity
# Total: 9 transactions
# ---------------------------------------------------------

for _ in range(9):
    account_id = random.choice(ACCOUNT_IDS)
    activity_type, minimum, maximum, destination = random.choice(
        ORDINARY_ACTIVITIES
    )

    transaction_day = start_date + timedelta(
        days=random.randint(0, date_range_days)
    )

    transactions.append(
        make_transaction(
            account_id,
            make_timestamp(transaction_day),
            round(random.uniform(minimum, maximum), 2),
            activity_type,
            destination,
        )
    )


# ---------------------------------------------------------
# 7. Validate generated dataset before writing files
# ---------------------------------------------------------

assert len(transactions) == 250, (
    f"Expected 250 transactions, generated {len(transactions)}"
)

transaction_ids = [row["transaction_id"] for row in transactions]

assert len(set(transaction_ids)) == 250, "Duplicate transaction IDs found"

assert all(row["account_id"] in ACCOUNT_IDS for row in transactions)
assert all(row["currency"] == "ZAR" for row in transactions)
assert all(Decimal(row["amount"]) > 0 for row in transactions)

assert all(
    date.fromisoformat(row["tx_date"][:10]) >= start_date
    and date.fromisoformat(row["tx_date"][:10]) <= end_date
    for row in transactions
)

assert all(
    row["transaction_type"]
    in {"PAYMENT", "TRANSFER", "WITHDRAWAL", "DEPOSIT", "PURCHASE"}
    for row in transactions
)

assert sum(
    Decimal(row["amount"]) > Decimal("50000")
    for row in transactions
) == 4

assert sum(
    row["source_country"] != row["destination_country"]
    for row in transactions
) == 8

transactions.sort(key=lambda row: row["tx_date"])


# ---------------------------------------------------------
# 8. Protect existing files
# ---------------------------------------------------------

if not CSV_PATH.parent.exists():
    raise FileNotFoundError(f"Missing output folder: {CSV_PATH.parent}")

if not SQL_PATH.parent.exists():
    raise FileNotFoundError(f"Missing output folder: {SQL_PATH.parent}")

if CSV_PATH.exists() or SQL_PATH.exists():
    raise FileExistsError(
        "One or both output files already exist. "
        "No files were overwritten. Rename or move the existing files "
        "before generating another dataset."
    )


# ---------------------------------------------------------
# 9. Write CSV
# ---------------------------------------------------------

with CSV_PATH.open("x", newline="", encoding="utf-8") as csv_file:
    writer = csv.DictWriter(csv_file, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(transactions)


# ---------------------------------------------------------
# 10. Write matching PostgreSQL seed SQL
# ---------------------------------------------------------

sql_lines = [
    "-- FinTrust synthetic transaction dataset",
    "-- 250 transactions: 1 July - 30 September 2026",
    "-- Target: AWS RDS PostgreSQL",
    "-- Alternative to CSV ingestion. Do not execute both routes.",
    "-- Direct SQL insertion does not trigger Lambda, DynamoDB or SQS.",
    "",
    "BEGIN;",
    "",
]

for row in transactions:
    values = [
        f"'{row['transaction_id']}'",
        f"'{row['account_id']}'",
        f"'{row['tx_date']}'",
        row["amount"],
        f"'{row['currency']}'",
        f"'{row['transaction_type']}'",
        f"'{row['source_country']}'",
        f"'{row['destination_country']}'",
        "NULL",
    ]

    sql_lines.append(
        "INSERT INTO transactions "
        "(transaction_id, account_id, tx_date, amount, currency, "
        "transaction_type, source_country, destination_country, risk_flag) "
        f"VALUES ({', '.join(values)});"
    )

sql_lines.extend(["", "COMMIT;", ""])

with SQL_PATH.open("x", encoding="utf-8", newline="\n") as sql_file:
    sql_file.write("\n".join(sql_lines))


# ---------------------------------------------------------
# 11. Summary
# ---------------------------------------------------------

print("\nFinTrust dataset generated successfully.")
print("-----------------------------------------")
print(f"Total transactions : {len(transactions)}")
print(f"Customers/accounts : {len(ACCOUNTS)}")
print("Period             : 2026-07-01 to 2026-09-30")
print("Currency           : ZAR")
print("High-value events  : 4")
print("Cross-border events: 8")
print("Velocity events    : 13")
print("\nGenerated files:")
print(f"CSV: {CSV_PATH}")
print(f"SQL: {SQL_PATH}")