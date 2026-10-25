"""Name/branch/address/occupation pools + deterministic pickers.

Every function draws ONLY from the passed rng (and `choose()` sorts inputs), so
builds stay byte-identical. No python `random`, no uuid, no time.
"""

from __future__ import annotations

import numpy as np

from generator.rng import choose

BRANCHES = ["Pune-Main", "Nagpur-East", "Mumbai-Andheri", "Delhi-CP", "Hyderabad-Hitech"]
CHANNELS = ["UPI", "IMPS", "NEFT", "RTGS", "CASH", "ACH"]
DEVICES = ["branch-terminal", "office-laptop", "mobile-app"]

FIRST = ["Aarav", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna", "Ishaan", "Rohan", "Kabir", "Anish",
         "Diya", "Aadhya", "Ananya", "Aarohi", "Myra", "Sara", "Ira", "Prisha", "Anvi", "Navya",
         "Rahul", "Sneha", "Vikram", "Pooja", "Karan", "Meera", "Aditya", "Kavya", "Nitin", "Ritu"]
LAST = ["Sharma", "Verma", "Patel", "Iyer", "Reddy", "Khan", "Mehta", "Joshi", "Nair", "Das",
        "Kulkarni", "Deshpande", "Agarwal", "Singh", "Choudhary", "Bose", "Pillai", "Rao", "Pawar", "Shinde"]

BIZ_ADJ = ["Shree", "Balaji", "Om", "Ganesh", "Sai", "New", "City", "Star", "Royal", "Prime"]
BIZ_NOUN = ["Traders", "Enterprises", "Trading Co", "Distributors", "Logistics", "Textiles",
            "Electronics", "Buildwell", "Infra", "Impex"]

# occupation -> (min_k, max_k) monthly declared income in ₹k
OCCUPATIONS = [
    ("Software Engineer", 60, 140), ("Accountant", 45, 70), ("Teacher", 30, 50),
    ("Shop Owner", 40, 120), ("Junior Clerk", 25, 40), ("Driver", 18, 30),
    ("Nurse", 35, 55), ("Consultant", 80, 200), ("Student", 5, 15),
    ("Retired", 20, 45), ("Trader", 50, 300), ("Delivery Partner", 15, 28),
]
OCC_WEIGHTS = [0.10, 0.09, 0.10, 0.10, 0.09, 0.08, 0.08, 0.06, 0.07, 0.07, 0.08, 0.08]

STREETS = ["MG Road", "Station Road", "Gandhi Chowk", "Nehru Marg", "Shivaji Path", "Civil Lines",
           "Sadar Bazar", "Model Colony", "Phase 2", "Old Market Road"]
AREAS = ["Pune", "Nagpur", "Mumbai", "Thane", "Amravati", "Nashik", "Aurangabad", "Wardha"]


def pick_occupation(rng: np.random.Generator) -> tuple[str, float]:
    idx = int(rng.choice(len(OCCUPATIONS), p=np.array(OCC_WEIGHTS) / sum(OCC_WEIGHTS)))
    occ, lo, hi = OCCUPATIONS[idx]
    income = round(float(rng.uniform(lo, hi)) * 1000, -2)  # nearest ₹100
    return occ, max(income, 5000.0)


def make_person_name(rng: np.random.Generator) -> str:
    return f"{choose(rng, FIRST)} {choose(rng, LAST)}"


def make_business_name(rng: np.random.Generator) -> str:
    return f"{choose(rng, BIZ_ADJ)} {choose(rng, BIZ_NOUN)}"


def make_phone(rng: np.random.Generator) -> str:
    return str(int(rng.integers(7_000_000_000, 9_999_999_999)))


def make_address(rng: np.random.Generator) -> str:
    no = int(rng.integers(1, 400))
    return f"{no}, {choose(rng, STREETS)}, {choose(rng, AREAS)}"


def pick_branch(rng: np.random.Generator) -> str:
    return str(choose(rng, BRANCHES))


def pick_device(rng: np.random.Generator) -> str:
    return str(choose(rng, DEVICES, p=[0.6, 0.3, 0.1]))


def make_internal_ip(rng: np.random.Generator) -> str:
    return f"10.20.{int(rng.integers(0, 12))}.{int(rng.integers(2, 250))}"
