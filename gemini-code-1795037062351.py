import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="Career Venture Lab | ROB-2 Robotics Studio",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# HELPER FUNCTIONS & EXACT MONEY ARITHMETIC
# ---------------------------------------------------------------------------
def d(val) -> Decimal:
    return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def fmt_usd(val) -> str:
    return f"${d(val):,.2f}"

def get_default_state() -> dict:
    return {
        "team_id": "TEAM-ROB2",
        "course": "Precalculus",
        "pathway_id": "ROB-2",
        "business_name": "Robotics Kit and Repair Studio",
        "selected_level": "Foundation",
        "teacher_approved_skills": "Rational average cost, function composition, domain & asymptotes",
        "snapshot_id": "SNAP-0001",
        "state_version": 1,
        "simulation_date": "2027-01-31",
        "base_period": "Monthly",
        "working_days": 22,
        "currency": "USD",
        "random_seed": 2027,
        "processed_run_ids": [],
        "assumptions": [
            "All figures are fictional teaching defaults from ROB-2 handbook.",
            "Components are expensed when attempted/consumed; cash outflow occurs upon restock.",
            "Non-component variable expenses ($35/unit) are paid in cash per attempted unit.",
            "Borrowing, interest, refunds, depreciation, and sales tax are disabled at baseline.",
        ],
        "sources": [
            "Career Venture Lab Student Handbook (November 2026), Pathway ROB-2 & ROB Package (pp. 26, 69, 78-82)"
        ],
        "parameters": {
            "base_price": 120.00,
            "D0": 40,
            "staff_hours": 90.0,
            "hours_per_unit": 3.0,
            "defect_rate": 0.0,
            "component_unit_cost": 30.00,
            "non_component_var_cost": 35.00,  # assembly $20 + packaging $10 + warranty $5
            "fixed_cost_monthly": 600.00,     # workspace $250 + software $100 + maint $150 + admin $100
        },
        "balances": {
            "owner_contribution": 12000.00,
            "equipment_assets": 4000.00,
            "pre_opening_expense": 0.00,
            "opening_cash": 5000.00,
            "cash": 5000.00,
            "opening_stock_units": 100,
            "stock_units": 100,
            "inventory_value": 3000.00,
            "debt": 0.00,
            "retained_earnings": 0.00,
        },
        "cost_lines": {
            "variable_per_attempted_unit": {
                "components_COGS": 30.00,
                "assembly_labor": 20.00,
                "packaging": 10.00,
                "warranty_consumables": 5.00,
            },
            "monthly_fixed": {
                "workspace": 250.00,
                "software": 100.00,
                "equipment_maintenance": 150.00,
                "admin": 100.00,
            },
        },
        "offerings": [
            {
                "offering_id": "OFF-KIT-01",
                "name": "Introductory robot kit (Primary)",
                "unit": "kit",
                "price": 120.00,
                "demand_rule": "q(p) = max(0, 80 - (1/3)*p)",
                "capacity_rule": "min(floor(staff_hours/hours_per_unit), stock_units)",
            }
        ],
        "ledger": [],
        "recommendations": [],
        "campaigns": [],
        "decisions": [],
    }

if "sim_state" not in st.session_state:
    st.session_state.sim_state = get_default_state()

state = st.session_state.sim_state

# ---------------------------------------------------------------------------
# DETERMINISTIC MONTHLY SIMULATION ENGINE (ROB PACKAGE RULES)
# ---------------------------------------------------------------------------
def run_monthly_step(
    sim_state: dict,
    run_id: str,
    sim_date: str,
    requested: int,
    restock_units: int = 0,
    ad_cost: float = 0.0,
    capacity_override: int | None = None,
    mode_label: str = "Normal",
) -> tuple[bool, str]:
    if run_id in sim_state["processed_run_ids"]:
        return False, f"Duplicate run_id '{run_id}' rejected. No new transactions created."

    if requested < 0 or restock_units < 0 or ad_cost < 0:
        return False, "Negative quantities or costs are rejected."

    p = sim_state["parameters"]
    b = sim_state["balances"]

    price = d(p["base_price"])
    comp_unit_cost = d(p["component_unit_cost"])
    non_comp_unit_cost = d(p["non_component_var_cost"])
    fixed_cost = d(p["fixed_cost_monthly"])
    ad_expense = d(ad_cost)
    defect_rate = float(p["defect_rate"])

    # Restock occurs before fulfillment
    restock_cash_outflow = d(restock_units) * comp_unit_cost
    available_stock = int(b["stock_units"]) + int(restock_units)

    if capacity_override is not None:
        capacity = int(capacity_override)
    else:
        capacity = math.floor(float(p["staff_hours"]) / float(p["hours_per_unit"]))

    attempted = min(int(requested), capacity, available_stock)
    failed = math.floor(attempted * defect_rate)
    sold = attempted - failed
    unserved_demand = max(0, int(requested) - attempted)

    revenue = price * d(sold)
    consumed_component_cost = d(attempted) * comp_unit_cost
    non_comp_var_cost = d(attempted) * non_comp_unit_cost
    total_variable_expense = consumed_component_cost + non_comp_var_cost
    total_expense = total_variable_expense + fixed_cost + ad_expense
    operating_profit = revenue - total_expense

    # Cash rule: component cash outflow occurs on restock; non-component variable paid on attempted units
    ending_cash = (
        d(b["cash"])
        + revenue
        - restock_cash_outflow
        - non_comp_var_cost
        - fixed_cost
        - ad_expense
    )

    ending_stock_units = available_stock - attempted
    ending_inventory_val = d(b["inventory_value"]) + restock_cash_outflow - consumed_component_cost
    ending_retained = d(b["retained_earnings"]) + operating_profit

    next_version = sim_state["state_version"] + 1
    tx_base = f"TX-{next_version:04d}"

    new_entries = [
        {
            "transaction_id": f"{tx_base}-SUMMARY",
            "run_id": run_id,
            "date": sim_date,
            "mode": mode_label,
            "event_type": "Monthly Summary",
            "category": "Operations & Finance",
            "requested": int(requested),
            "capacity": int(capacity),
            "attempted": int(attempted),
            "failed": int(failed),
            "sold": int(sold),
            "unserved_demand": int(unserved_demand),
            "revenue": float(revenue),
            "variable_expense": float(total_variable_expense),
            "fixed_expense": float(fixed_cost),
            "marketing_expense": float(ad_expense),
            "total_expense": float(total_expense),
            "operating_profit": float(operating_profit),
            "restock_units": int(restock_units),
            "restock_cash_outflow": float(restock_cash_outflow),
            "closing_cash": float(ending_cash),
            "closing_stock_units": int(ending_stock_units),
            "closing_inventory_value": float(ending_inventory_val),
            "state_version": next_version,
        }
    ]

    sim_state["ledger"].extend(new_entries)
    sim_state["processed_run_ids"].append(run_id)
    sim_state["balances"]["cash"] = float(ending_cash)
    sim_state["balances"]["stock_units"] = int(ending_stock_units)
    sim_state["balances"]["inventory_value"] = float(ending_inventory_val)
    sim_state["balances"]["retained_earnings"] = float(ending_retained)
    sim_state["state_version"] = next_version
    sim_state["simulation_date"] = sim_date
    sim_state["snapshot_id"] = f"SNAP-{next_version:04d}"

    return True, f"Run '{run_id}' committed (State v{next_version}). Sold {sold} kits; Profit: {fmt_usd(operating_profit)}."

# ---------------------------------------------------------------------------
# SIDEBAR: STATE MANAGEMENT, SNAPSHOT EXPORT/IMPORT & CONTROLS
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("ROB-2 Control Panel")
    st.caption("Pathway ROB-2 | Precalculus | Robotics Kit & Repair Studio")

    state["team_id"] = st.text_input("Team ID", value=state["team_id"])
    new_level = st.selectbox(
        "Challenge Level (Teacher Approved)",
        ["Foundation", "Applied", "Advanced"],
        index=["Foundation", "Applied", "Advanced"].index(state["selected_level"]),
    )
    if new_level != state["selected_level"]:
        state["selected_level"] = new_level
        st.info(f"Challenge Level switched to **{new_level}**. Task, equations, and visuals updated.")

    st.divider()
    st.subheader("State & Snapshot (JSON)")
    st.write(f"**Snapshot ID:** `{state['snapshot_id']}`")
    st.write(f"**State Version:** `v{state['state_version']}`")
    st.write(f"**Current Date:** `{state['simulation_date']}`")

    snapshot_json = json.dumps(state, indent=2)
    st.download_button(
        label="Save / Export Snapshot JSON",
        data=snapshot_json,
        file_name=f"{state['team_id']}_ROB2_v{state['state_version']}.json",
        mime="application/json",
    )

    uploaded_file = st.file_uploader("Restore Snapshot JSON", type=["json"])
    if uploaded_file is not None:
        try:
            loaded = json.load(uploaded_file)
            if loaded.get("team_id") != state["team_id"]:
                st.error(
                    f"Import Rejected: Snapshot team_id '{loaded.get('team_id')}' does not match active team '{state['team_id']}'."
                )
            elif loaded.get("pathway_id") != "ROB-2":
                st.error("Import Rejected: Snapshot pathway_id must be ROB-2.")
            elif int(loaded.get("state_version", 0)) < state["state_version"]:
                st.error(
                    f"Stale Version Rejected: Imported v{loaded.get('state_version')} is older than current v{state['state_version']}."
                )
            else:
                st.session_state.sim_state = loaded
                st.success(f"Snapshot v{loaded['state_version']} restored successfully.")
                st.rerun()
        except Exception as exc:
            st.error(f"Invalid JSON file: