"""logic.py - core engineering rules: thresholds, availability, risk score, alerts.
NOTE: thresholds are educational prototype values, not real manufacturer or mine safety limits."""
import pandas as pd

TEMP_WARN, TEMP_CRIT = 80, 100          # degrees C
VIB_WARN, VIB_CRIT = 5, 8               # mm/s
PPE_MIN, FATIGUE_MAX = 90, 7            # % and 1-10 scale
LOW_AVAIL, HIGH_DOWNTIME = 95, 60       # % and hours
RANK = {"Normal": 0, "Warning": 1, "Critical": 2}


def classify_temperature(t):
    return "Critical" if t > TEMP_CRIT else "Warning" if t >= TEMP_WARN else "Normal"


def classify_vibration(v):
    return "Critical" if v > VIB_CRIT else "Warning" if v >= VIB_WARN else "Normal"


def worst(*levels):
    """Return the most severe of several Normal/Warning/Critical levels."""
    return max(levels, key=RANK.get)


def calculate_availability(operating, downtime):
    """Availability = Operating / (Operating + Downtime) x 100."""
    total = operating + downtime
    return round(operating / total * 100, 1) if total > 0 else 0.0


def equipment_message(temp, vib):
    """Status message in the wording required by the brief."""
    t, v = classify_temperature(temp), classify_vibration(vib)
    if worst(t, v) == "Critical":
        what = "temperature" if t == "Critical" else "vibration"
        return f"CRITICAL: Equipment {what} exceeds predefined threshold. Inspection required."
    if worst(t, v) == "Warning":
        what = " and ".join(n for n, s in (("temperature", t), ("vibration", v)) if s == "Warning")
        return f"WARNING: Equipment {what} approaching predefined threshold."
    return "NORMAL: Equipment operating within defined monitoring limits."


def risk_score(likelihood, consequence):
    return int(likelihood) * int(consequence)


def risk_class(score):
    return "Low" if score <= 4 else "Medium" if score <= 9 else "High" if score <= 16 else "Critical"


def risk_warning(score):
    c = risk_class(score)
    return f"WARNING: {c.upper()} risk identified (score {score}). Management action required." if c in ("High", "Critical") else None


def worker_warnings(w):
    """List unsafe conditions for one worker row."""
    out = []
    if w["PPE_Compliance_Percent"] < PPE_MIN: out.append(f"Low PPE compliance ({w['PPE_Compliance_Percent']}%)")
    if w["Fatigue_Level"] >= FATIGUE_MAX: out.append(f"High fatigue level ({w['Fatigue_Level']}/10)")
    if w["Safety_Training_Status"] == "Expired": out.append("Safety training expired")
    if w["Risk_Level"] in ("High", "Critical"): out.append(f"{w['Risk_Level']} risk worker")
    return out


def equipment_alerts(e):
    """Build alert dictionaries (Figure 1 format) for one equipment row."""
    out = []
    def add(level, param, value, status, action):
        out.append({"Level": level, "Equipment_ID": e["Equipment_ID"], "Parameter": param,
                    "Value": value, "Status": status, "Action": action})
    t, v = classify_temperature(e["Temperature_C"]), classify_vibration(e["Vibration_mm_s"])
    insp = "Inspect equipment and initiate appropriate maintenance/safety procedures."
    if t != "Normal": add(t.upper(), "Temperature", f"{e['Temperature_C']} C", f"{'Above Critical' if t == 'Critical' else 'Above Warning'} Threshold", insp)
    if v != "Normal": add(v.upper(), "Vibration", f"{e['Vibration_mm_s']} mm/s", f"{'Above Critical' if v == 'Critical' else 'Above Warning'} Threshold", insp)
    if e["Overdue"]: add("WARNING", "Maintenance", f"{e['Days_Overdue']} days overdue", "Overdue", "Complete overdue maintenance.")
    if e["Availability_Percent"] < LOW_AVAIL: add("WARNING", "Availability", f"{e['Availability_Percent']}%", "Below 95%", "Review reliability and downtime causes.")
    if e["Downtime_Hours"] > HIGH_DOWNTIME: add("WARNING", "Downtime", f"{e['Downtime_Hours']} h", "Excessive downtime", "Investigate downtime and plan repairs.")
    for part in ("Brake", "Tyre", "Engine"):
        if e[f"{part}_Status"] != "Good": add("WARNING", part, e[f"{part}_Status"], "Needs attention", f"Inspect {part.lower()} condition.")
    return out


def format_alert(a):
    """Render an alert as the text box shown in Figure 1 of the brief."""
    bar = "=" * 53
    return (f"{bar}\nMINING MONITORING ALERT\n{bar}\n[{a['Level']}]\nEquipment ID: {a['Equipment_ID']}\n"
            f"Parameter: {a['Parameter']}\nValue: {a['Value']}\nStatus: {a['Status']}\n"
            f"Recommended Action:\n {a['Action']}\n{bar}")


def all_alerts(equipment):
    rows = [a for _, e in equipment.iterrows() for a in equipment_alerts(e)]
    cols = ["Level", "Equipment_ID", "Parameter", "Value", "Status", "Action"]
    df = pd.DataFrame(rows, columns=cols)
    df["_o"] = df["Level"].map({"CRITICAL": 0, "WARNING": 1})
    return df.sort_values(["_o", "Equipment_ID"]).drop(columns="_o").reset_index(drop=True)


def worker_alerts(workers):
    rows = [{"Worker_ID": w["Worker_ID"], "Department": w["Department"], "Warning": m}
            for _, w in workers.iterrows() for m in worker_warnings(w)]
    return pd.DataFrame(rows, columns=["Worker_ID", "Department", "Warning"])


def risk_table(risks):
    r = risks.copy()
    r["Risk_Score"] = r["Likelihood"] * r["Consequence"]
    r["Classification"] = r["Risk_Score"].map(risk_class)
    return r.sort_values("Risk_Score", ascending=False)


def kpis(d):
    eq, w, inc = d["equipment"], d["workers"], d["incidents"]
    return {
        "Total workers": len(w), "Total incidents": len(inc),
        "Near misses": int((inc["Injury_Status"] == "Near Miss").sum()),
        "High-risk workers": int(w["Risk_Level"].isin(["High", "Critical"]).sum()),
        "PPE compliance %": round((w["PPE_Compliant"] == "Yes").mean() * 100, 1),
        "Total equipment": len(eq),
        "Equipment available": int((eq["Availability_Percent"] >= LOW_AVAIL).sum()),
        "Under maintenance": int(eq["Under_Maintenance"].sum()),
        "Avg availability %": round(eq["Availability_Percent"].mean(), 1),
        "Critical equipment": int((eq["Overall_Status"] == "Critical").sum()),
        "Overdue maintenance": int(eq["Overdue"].sum()),
        "Open incidents": int((inc["Incident_Status"] != "Closed").sum()),
    }
