import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "seed"
OUT.mkdir(parents=True, exist_ok=True)

rng = random.Random(20261011)
tz = timezone(timedelta(hours=2))

customers = [
    "Thabo Mokoena", "Lerato Dlamini", "Aisha Khan",
    "Daniel Smith", "Naledi Molefe", "Jason Naidoo",
    "Priya Patel", "Michael Jacobs", "Zanele Ndlovu",
    "Ryan Williams", "Fatima Ahmed", "Sipho Khumalo",
]

def make_uuid(prefix, number):
    return f"{prefix}-0000-0000-0000-{number:012d}"

account_ids = {
    n: make_uuid("10000000", n) for n in range(1, 13)
}

rows = []
used_timestamps = {n: set() for n in range(1, 13)}

velocity_numbers = {1 + (i * 12) for i in range(12)}
account5_dates = {
    5: datetime(2026, 8, 7, 9, 0, tzinfo=tz),
    17: datetime(2026, 8, 11, 21, 0, tzinfo=tz),
    29: datetime(2026, 8, 17, 9, 0, tzinfo=tz),
    41: datetime(2026, 8, 21, 21, 0, tzinfo=tz),
}

types = ["PAYMENT", "TRANSFER", "PURCHASE", "DEPOSIT", "WITHDRAWAL"]
foreign_countries = ["GB", "US", "DE", "AE", "FR", "SG"]

for n in range(1, 251):
    account_no = ((n - 1) % 12) + 1

    if n in velocity_numbers:
        tx_time = datetime(2026, 7, 15, 9, 0, tzinfo=tz) + timedelta(
            minutes=5 * (n // 12)
        )
    elif n in account5_dates:
        tx_time = account5_dates[n].replace(tzinfo=tz)
    else:
        while True:
            day = datetime(2026, 7, 1, tzinfo=tz) + timedelta(
                days=rng.randint(0, 91)
            )
            candidate = day.replace(
                hour=rng.randint(7, 21),
                minute=rng.randint(0, 59),
                second=rng.randint(0, 59),
            )
            if candidate not in used_timestamps[account_no]:
                tx_time = candidate
                break

    if tx_time in used_timestamps[account_no]:
        raise ValueError(f"Duplicate timestamp for account {account_no}: {tx_time}")
    used_timestamps[account_no].add(tx_time)

    if n in account5_dates:
        amount = rng.choice([51000, 62500, 78000, 95000])
    else:
        category = rng.random()
        if category < 0.10:
            amount = round(rng.uniform(51000, 125000), 2)
        elif category < 0.30:
            amount = round(rng.uniform(10000, 50000), 2)
        else:
            amount = round(rng.uniform(500, 9999), 2)

    source = "ZA"
    destination = "ZA"
    if rng.random() < 0.18:
        source, destination = rng.choice([
            ("ZA", "GB"), ("ZA", "US"), ("GB", "ZA"),
            ("US", "ZA"), ("DE", "ZA"), ("AE", "ZA"),
        ])

    rows.append({
        "transaction_id": make_uuid("20000000", n),
        "account_id": account_ids[account_no],
        "tx_date": tx_time.isoformat(timespec="seconds"),
        "amount": f"{amount:.2f}",
        "currency": "ZAR",
        "transaction_type": rng.choice(types),
        "source_country": source,
        "destination_country": destination,
    })

csv_path = OUT / "fintrust_master_250_transactions.csv"
with csv_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

sql_lines = [
    "-- FinTrust customer and account seed data",
    "-- 12 customers and 12 accounts. Transactions enter through raw S3.",
    "BEGIN;",
    "",
    "INSERT INTO customers (customer_id, customer_name) VALUES",
]
for i, name in enumerate(customers, start=1):
    comma = "," if i < len(customers) else ""
    sql_lines.append(
        f"('{make_uuid('00000000', i)}', '{name}'){comma}"
    )
sql_lines += [
    "ON CONFLICT DO NOTHING;",
    "",
    "INSERT INTO accounts (account_id, customer_id, account_number, account_status) VALUES",
]
for i in range(1, 13):
    status = "SUSPENDED" if i in (10, 12) else "ACTIVE"
    comma = "," if i < 12 else ""
    sql_lines.append(
        f"('{account_ids[i]}', '{make_uuid('00000000', i)}', "
        f"'4100{i:012d}', '{status}'){comma}"
    )
sql_lines += ["ON CONFLICT DO NOTHING;", "", "COMMIT;", ""]

sql_path = OUT / "seed_customers_accounts.sql"
sql_path.write_text("\n".join(sql_lines), encoding="utf-8")

print(f"Created: {csv_path}")
print(f"Created: {sql_path}")
print(f"Valid transaction rows: {len(rows)}")
print(f"Date range: {min(r['tx_date'] for r in rows)} to {max(r['tx_date'] for r in rows)}")
print(f"Accounts represented: {len(set(r['account_id'] for r in rows))}")
print(f"High-value transactions (> R50,000): {sum(float(r['amount']) > 50000 for r in rows)}")
print(f"Cross-border transactions: {sum(r['source_country'] != r['destination_country'] for r in rows)}")
