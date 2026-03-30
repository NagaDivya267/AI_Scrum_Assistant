import streamlit as st
import pandas as pd
import csv
import os
import re
import datetime
from groq import Groq

# Page config
st.set_page_config(page_title="AI Scrum Assistant", layout="wide", initial_sidebar_state="expanded")

# Global custom CSS for modern dark UI
st.markdown("""
<style>
/* ── Global font scale-down ── */
html, body, [class*="css"] {
    font-size: 13px !important;
}
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li {
    font-size: 0.82rem !important;
}
label[data-testid="stWidgetLabel"],
div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label,
div[data-testid="stFileUploader"] label {
    font-size: 0.78rem !important;
}

/* ── Header gradient banner ── */
h1 {
    background: linear-gradient(90deg, #00D4AA 0%, #6C63FF 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 1.9rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.5px;
}

/* ── Sidebar polish ── */
section[data-testid="stSidebar"] {
    background: #161B22;
    border-right: 1px solid #30363D;
}
section[data-testid="stSidebar"] h3 {
    color: #00D4AA;
    font-size: 0.95rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
}

/* ── Tabs ── */
button[data-baseweb="tab"] {
    font-weight: 600;
    font-size: 0.78rem;
    color: #8B949E;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #00D4AA !important;
    border-bottom: 3px solid #00D4AA !important;
}

/* ── Metric cards ── */
div[data-testid="stMetric"] {
    background: #161B22;
    border: 1px solid #30363D;
    border-radius: 12px;
    padding: 16px 20px;
    transition: box-shadow 0.2s;
}
div[data-testid="stMetric"]:hover {
    box-shadow: 0 0 0 2px #00D4AA44;
}
div[data-testid="stMetricLabel"] {
    color: #8B949E !important;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
div[data-testid="stMetricValue"] {
    color: #C9D1D9 !important;
    font-size: 3rem !important;
    font-weight: 700 !important;
}

/* ── Buttons ── */
div.stButton > button {
    background: linear-gradient(135deg, #00D4AA, #6C63FF);
    color: #0D1117;
    font-weight: 700;
    border: none;
    border-radius: 8px;
    padding: 0.5rem 1.2rem;
    transition: opacity 0.2s, transform 0.1s;
}
div.stButton > button:hover {
    opacity: 0.88;
    transform: translateY(-1px);
}

/* ── Dividers ── */
hr {
    border-color: #30363D !important;
}

/* ── Dataframe / table ── */
div[data-testid="stDataFrame"] {
    border: 1px solid #30363D;
    border-radius: 10px;
    overflow: hidden;
}

/* ── Expander ── */
div[data-testid="stExpander"] {
    border: 1px solid #30363D;
    border-radius: 10px;
    background: #161B22;
}

/* ── Alert boxes ── */
div[data-testid="stAlert"] {
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)

# Define the CSV file path
csv_file = "sprint_data.csv"

# Risk classification thresholds (used consistently across prompt generation and alert banners)
RISK_HIGH_THRESHOLD = 50       # risk_pct above this → HIGH RISK
RISK_REMAINING_HIGH = 40       # remaining_pct above this → also HIGH RISK
RISK_MODERATE_THRESHOLD = 30   # risk_pct above this → AT RISK

# Pattern detection thresholds
BLOCKER_PCT_THRESHOLD = 25     # blocker_pct above this → "High blocker dependency"
NOT_STARTED_PCT_THRESHOLD = 30 # not_started_pct above this → "Poor sprint planning"
VELOCITY_GAP_THRESHOLD = 20    # velocity_gap_pct above this → "Velocity mismatch"

# Sidebar - API Key Setup
st.sidebar.markdown("### 🧭 Navigation")
st.sidebar.caption("📊 Sprint Analytics")
st.sidebar.markdown("---")

st.sidebar.markdown("### ⚙️ Configuration")

# Sidebar - Data Source
st.sidebar.markdown("### 📁 Sprint Data")
uploaded_file = st.sidebar.file_uploader("Upload Sprint CSV/XLSX", type=["csv", "xlsx"])

# Try to get API key from Streamlit secrets (for production), then from env vars
api_key = None

# First, try Streamlit secrets (production on Streamlit Cloud)
try:
    if hasattr(st, 'secrets') and 'GROQ_API_KEY' in st.secrets:
        api_key = st.secrets['GROQ_API_KEY']
except Exception:
    pass

# If not found in secrets, try environment variable
if not api_key:
    api_key = os.getenv("GROQ_API_KEY", "")

# Allow user to override with sidebar input ONLY if no API key is configured
if not api_key:
    sidebar_input = st.sidebar.text_input(
        "Groq API Key", 
        value="",
        type="password",
        help="Get your FREE API key from https://console.groq.com/keys"
    )
    
    if sidebar_input:
        api_key = sidebar_input
else:
    # API key is already configured, show success message
    st.sidebar.text("✅ API Key: Configured")

# Set environment variable for API calls
if api_key:
    os.environ["GROQ_API_KEY"] = api_key
    if not api_key == os.getenv("GROQ_API_KEY"):  # Only show if newly entered
        st.sidebar.success("✅ Groq API Key loaded")
else:
    st.sidebar.error("❌ No Groq API Key found")
    st.sidebar.info("""
    **To use this app, you need a FREE Groq API key:**
    
    1. Go to https://console.groq.com/keys
    2. Sign up (takes 1 minute)
    3. Create an API key
    4. Paste it in the box above
    5. Or contact admin to configure it in Streamlit Cloud Secrets
    """)

# Title and header
st.markdown("# 🚀 AI SCRUM ASSISTANT - with Predictive Analytics")
st.markdown("---")

def read_from_csv():
    """Read data from CSV file into DataFrame"""
    try:
        df = pd.read_csv(csv_file)
        df = normalize_dataframe_columns(df)
        return df
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
        return None

def normalize_dataframe_columns(df):
    """Clean and normalize common column name variants from uploaded files."""
    df = df.copy()
    df.columns = [str(col).replace("\ufeff", "").strip() for col in df.columns]

    alias_map = {
        "sprint": "Sprint",
        "sprintname": "Sprint",
        "status": "Status",
        "state": "Status",
        "storypoints": "StoryPoints",
        "storypoint": "StoryPoints",
        "sp": "StoryPoints",
        "blocked": "Blocked",
        "story": "Story",
        "committed": "Committed",
        "commitment": "Committed",
        "completed": "Completed",
        "done": "Completed",
        "sprintstatus": "SprintStatus",
    }

    rename_map = {}
    existing = set(df.columns)
    for col in list(df.columns):
        normalized_key = re.sub(r"[^a-z0-9]", "", col.lower())
        canonical = alias_map.get(normalized_key)
        if canonical and canonical not in existing and col != canonical:
            rename_map[col] = canonical
            existing.add(canonical)

    if rename_map:
        df = df.rename(columns=rename_map)

    return df

def get_sprint_summary(df):
    """Generate summary statistics from DataFrame"""
    required_columns = {"Sprint", "Status", "StoryPoints"}
    if not required_columns.issubset(df.columns):
        return {}

    # Normalize status values so different casings and synonyms all map correctly
    DONE_VALUES = {"done", "completed", "complete", "closed", "resolved", "finished"}
    IN_PROGRESS_VALUES = {"in progress", "inprogress", "in-progress", "active", "wip", "in development", "dev", "development"}
    TODO_VALUES = {"to do", "todo", "not started", "open", "new", "backlog", "planned", "ready"}

    def normalize_status(raw):
        s = str(raw).strip().lower()
        if s in DONE_VALUES:
            return "Done"
        if s in IN_PROGRESS_VALUES:
            return "In Progress"
        if s in TODO_VALUES:
            return "To Do"
        return "To Do"  # default unmapped statuses to To Do

    sprints = {}
    for _, row in df.iterrows():
        sprint = str(row['Sprint'])
        status = normalize_status(row['Status'])
        story_points = pd.to_numeric(row['StoryPoints'], errors='coerce')
        story_points = int(story_points) if pd.notna(story_points) else 0
        
        if sprint not in sprints:
            sprints[sprint] = {"Done": 0, "In Progress": 0, "To Do": 0, "Total": 0}
        
        sprints[sprint]["Total"] += story_points
        sprints[sprint][status] = sprints[sprint].get(status, 0) + story_points
    
    return sprints

def calculate_metrics(df):
    """Calculate key metrics for the sprint"""
    required_columns = {"Sprint", "Status", "StoryPoints"}
    if not required_columns.issubset(df.columns):
        return {
            "total_sp": 0,
            "completed_sp": 0,
            "remaining_sp": 0,
            "in_progress_sp": 0,
            "todo_sp": 0,
            "blocked_count": 0,
            "blocked_sp": 0,
            "completion_rate": 0,
            "risk_percentage": 0
        }

    sprints_summary = get_sprint_summary(df)
    
    total_story_points = sum(s["Total"] for s in sprints_summary.values())
    total_completed = sum(s["Done"] for s in sprints_summary.values())
    total_in_progress = sum(s["In Progress"] for s in sprints_summary.values())
    total_todo = sum(s["To Do"] for s in sprints_summary.values())
    if 'Blocked' in df.columns:
        blocked_mask = df['Blocked'].astype(str).str.strip().str.lower() == 'yes'
        blocked_count = blocked_mask.sum()
        blocked_sp = pd.to_numeric(df.loc[blocked_mask, 'StoryPoints'], errors='coerce').fillna(0).sum()
    else:
        blocked_count = 0
        blocked_sp = 0
    
    completion_rate = (total_completed / total_story_points * 100) if total_story_points > 0 else 0
    # Risk% = Sum of blocked SP / Committed story points
    risk_percentage = (blocked_sp / total_story_points * 100) if total_story_points > 0 else 0
    
    return {
        "total_sp": total_story_points,
        "completed_sp": total_completed,
        "remaining_sp": total_todo + total_in_progress,
        "in_progress_sp": total_in_progress,
        "todo_sp": total_todo,
        "blocked_count": int(blocked_count),
        "blocked_sp": blocked_sp,
        "completion_rate": completion_rate,
        "risk_percentage": risk_percentage
    }
def calculate_advanced_metrics(df, full_df=None):
    """Calculate advanced risk metrics for advisor-style UI"""
    base_metrics = calculate_metrics(df)
    # Use full_df (all sprints) for last-3-sprint velocity; fall back to df if not provided
    velocity_metrics = get_velocity_metrics(full_df if full_df is not None else df)

    total_sp = base_metrics["total_sp"]
    total_items = len(df)

    remaining_pct = (base_metrics["remaining_sp"] / total_sp * 100) if total_sp > 0 else 0
    # Blocked % based on sum of blocked SP relative to committed SP
    blocker_pct = (base_metrics["blocked_sp"] / total_sp * 100) if total_sp > 0 else 0
    not_started_pct = (base_metrics["todo_sp"] / total_sp * 100) if total_sp > 0 else 0
    # Velocity gap: gap between remaining SP (required burn) and avg velocity from last 3 sprints
    velocity_gap_pct = ((base_metrics["remaining_sp"] - velocity_metrics["avg_velocity"]) / total_sp * 100) if total_sp > 0 else 0

    return {
        "total_sp": base_metrics["total_sp"],
        "completed_sp": base_metrics["completed_sp"],
        "remaining_sp": base_metrics["remaining_sp"],
        "risk": round(base_metrics["risk_percentage"]),
        "remaining_pct": round(remaining_pct),
        "blocker_pct": round(blocker_pct),
        "not_started_pct": round(not_started_pct),
        "velocity_gap_pct": round(velocity_gap_pct)
    }

def get_risk_status(risk_percentage):
    """Return human-readable risk status for sprint health"""
    if risk_percentage >= 60:
        return f"🔴 High Risk ({round(risk_percentage)}%) - Sprint is at significant delivery risk"
    if risk_percentage >= 35:
        return f"🟡 Medium Risk ({round(risk_percentage)}%) - Sprint needs close monitoring"
    return f"🟢 Low Risk ({round(risk_percentage)}%) - Sprint is in a healthy range"

def extract_sprint_number(sprint_name):
    """Extract sprint number for natural sorting of sprint labels."""
    match = re.search(r"(\d+)", str(sprint_name))
    return int(match.group(1)) if match else -1

def get_current_sprint_name(df):
    """Return current sprint name, preferring SprintStatus=Active when available."""
    if 'SprintStatus' in df.columns:
        active_df = df[df['SprintStatus'].astype(str).str.strip().str.lower() == 'active']
        if not active_df.empty:
            active_sprints = sorted(active_df['Sprint'].dropna().astype(str).unique(), key=extract_sprint_number)
            if active_sprints:
                return active_sprints[-1]

    sprint_names = sorted(df['Sprint'].dropna().astype(str).unique(), key=extract_sprint_number)
    return sprint_names[-1] if sprint_names else None

def get_current_sprint_df(df):
    """Return DataFrame filtered to current sprint and its sprint name."""
    current_sprint_name = get_current_sprint_name(df)
    if not current_sprint_name:
        return df, None
    sprint_mask = df['Sprint'].astype(str).str.strip() == str(current_sprint_name).strip()
    return df[sprint_mask], current_sprint_name

def calculate_sprint_health(committed_sp, completed_sp, added_sp, prod_defects, total_defects):
    """Calculate sprint health score for a completed sprint."""
    if committed_sp <= 0:
        predictability = 0
        spillover = 0
        scope_change = 0
    else:
        predictability = (completed_sp / committed_sp) * 100
        spillover = ((committed_sp - completed_sp) / committed_sp) * 100
        scope_change = (added_sp / committed_sp) * 100

    defect_leakage = (prod_defects / total_defects) * 100 if total_defects > 0 else 0

    sprint_health = (
        0.4 * predictability
        - 0.2 * spillover
        - 0.2 * scope_change
        - 0.2 * defect_leakage
    )

    return {
        "predictability": round(predictability, 2),
        "spillover": round(spillover, 2),
        "scope_change": round(scope_change, 2),
        "defect_leakage": round(defect_leakage, 2),
        "sprint_health": round(sprint_health, 2)
    }

def get_health_status(score):
    """Return traffic-light sprint health label."""
    if score >= 80:
        return "🟢 Healthy Sprint"
    if score >= 60:
        return "🟡 Moderate"
    return "🔴 Poor Sprint"

def sum_optional_numeric(sprint_df, column_candidates):
    """Return sum of first matching numeric column, else 0."""
    for column_name in column_candidates:
        if column_name in sprint_df.columns:
            return pd.to_numeric(sprint_df[column_name], errors='coerce').fillna(0).sum()
    return 0

def get_completed_sprint_health(df):
    """Build sprint health metrics for completed sprints only."""
    health_rows = []

    # DPM-style fallback: files with Sprint/Committed/Completed only.
    if {"Sprint", "Committed", "Completed"}.issubset(df.columns):
        storypoints_sum = pd.to_numeric(df.get("StoryPoints", 0), errors='coerce').fillna(0).sum() if "StoryPoints" in df.columns else 0
        status_all_todo = df["Status"].astype(str).str.strip().str.lower().eq("to do").all() if "Status" in df.columns else True

        if storypoints_sum == 0 or status_all_todo:
            dpm_df = df[["Sprint", "Committed", "Completed"]].copy()
            dpm_df["Committed"] = pd.to_numeric(dpm_df["Committed"], errors='coerce').fillna(0)
            dpm_df["Completed"] = pd.to_numeric(dpm_df["Completed"], errors='coerce').fillna(0)
            grouped = dpm_df.groupby("Sprint", as_index=False)[["Committed", "Completed"]].sum()
            grouped = grouped.sort_values(by="Sprint", key=lambda s: s.map(extract_sprint_number))

            for _, row in grouped.iterrows():
                committed_sp = float(row["Committed"])
                completed_sp = float(row["Completed"])
                predictability = (completed_sp / committed_sp * 100) if committed_sp > 0 else 0
                spillover = max(0, 100 - predictability)
                sprint_health = predictability

                health_rows.append({
                    "Sprint": row["Sprint"],
                    "Committed SP": committed_sp,
                    "Completed SP": completed_sp,
                    "Predictability %": round(predictability, 2),
                    "Spillover %": round(spillover, 2),
                    "Scope Change %": 0,
                    "Defect Leakage %": 0,
                    "Sprint Health %": round(sprint_health, 2),
                    "Status": get_health_status(sprint_health)
                })

            return pd.DataFrame(health_rows)

    required_columns = {"Sprint", "StoryPoints", "Status"}
    if not required_columns.issubset(df.columns):
        return pd.DataFrame(health_rows)

    if 'SprintStatus' in df.columns:
        completed_sprint_names = sorted(
            df[df['SprintStatus'].astype(str).str.strip().str.lower() == 'closed']['Sprint'].dropna().astype(str).unique(),
            key=extract_sprint_number
        )
    else:
        current_sprint_name = get_current_sprint_name(df)
        completed_sprint_names = sorted(df['Sprint'].dropna().astype(str).unique(), key=extract_sprint_number)
        if current_sprint_name in completed_sprint_names:
            completed_sprint_names.remove(current_sprint_name)

    for sprint_name in completed_sprint_names:
        sprint_mask = df['Sprint'].astype(str).str.strip() == str(sprint_name).strip()
        sprint_df = df[sprint_mask]
        _done_vals = {"done", "completed", "complete", "closed", "resolved", "finished"}
        committed_sp = pd.to_numeric(sprint_df['StoryPoints'], errors='coerce').fillna(0).sum()
        completed_sp = pd.to_numeric(
            sprint_df[sprint_df['Status'].astype(str).str.strip().str.lower().isin(_done_vals)]['StoryPoints'],
            errors='coerce'
        ).fillna(0).sum()

        added_sp = sum_optional_numeric(sprint_df, ["AddedSP", "Added_SP", "ScopeAddedSP"])
        prod_defects = sum_optional_numeric(sprint_df, ["ProdDefects", "ProductionDefects", "Prod_Defects"])
        total_defects = sum_optional_numeric(sprint_df, ["TotalDefects", "Defects", "Total_Defects"])

        health = calculate_sprint_health(
            committed_sp=committed_sp,
            completed_sp=completed_sp,
            added_sp=added_sp,
            prod_defects=prod_defects,
            total_defects=total_defects
        )

        health_rows.append({
            "Sprint": sprint_name,
            "Committed SP": committed_sp,
            "Completed SP": completed_sp,
            "Predictability %": health["predictability"],
            "Spillover %": health["spillover"],
            "Scope Change %": health["scope_change"],
            "Defect Leakage %": health["defect_leakage"],
            "Sprint Health %": health["sprint_health"],
            "Status": get_health_status(health["sprint_health"])
        })

    return pd.DataFrame(health_rows)

def get_velocity_metrics(df):
    """Calculate velocity-based metrics using the last 3 completed sprints"""
    required_columns = {"Sprint", "StoryPoints", "Status"}
    if not required_columns.issubset(df.columns):
        return {
            "avg_velocity": 0,
            "velocities": [],
            "velocity_trend": "➡️ Stable"
        }

    # Identify completed sprint names
    if 'SprintStatus' in df.columns:
        closed_df = df[df['SprintStatus'].astype(str).str.strip().str.lower() == 'closed']
        completed_sprint_names = sorted(
            closed_df['Sprint'].dropna().astype(str).unique(),
            key=extract_sprint_number
        )
    else:
        current_sprint = get_current_sprint_name(df)
        all_sprints = sorted(df['Sprint'].dropna().astype(str).unique(), key=extract_sprint_number)
        completed_sprint_names = [s for s in all_sprints if s != current_sprint]

    # Calculate Done SP per completed sprint
    _done_vals = {"done", "completed", "complete", "closed", "resolved", "finished"}
    sprint_velocities = []
    for sprint_name in completed_sprint_names:
        sprint_mask = df['Sprint'].astype(str).str.strip() == str(sprint_name).strip()
        sprint_df = df[sprint_mask]
        done_sp = pd.to_numeric(
            sprint_df[sprint_df['Status'].astype(str).str.strip().str.lower().isin(_done_vals)]['StoryPoints'],
            errors='coerce'
        ).fillna(0).sum()
        sprint_velocities.append(done_sp)

    # Average velocity based on last 3 completed sprints
    last_3 = sprint_velocities[-3:] if len(sprint_velocities) >= 3 else sprint_velocities
    avg_velocity = sum(last_3) / len(last_3) if last_3 else 0

    return {
        "avg_velocity": avg_velocity,
        "velocities": sprint_velocities,
        "velocity_trend": "Stable" if len(sprint_velocities) <= 1 else (
            "📈 Improving" if sprint_velocities[-1] > avg_velocity else
            "📉 Declining" if sprint_velocities[-1] < avg_velocity else "➡️ Stable"
        )
    }

def get_traffic_light(confidence):
    """Return traffic light emoji and status based on confidence percentage"""
    if confidence >= 85:
        return "🟢", "On Track"
    elif confidence >= 60:
        return "🟡", "At Risk"
    else:
        return "🔴", "High Risk"

def get_color(value, good, medium):
    """Return CSS color class based on value vs thresholds."""
    if value >= good:
        return "green"
    elif value >= medium:
        return "yellow"
    else:
        return "red"

def calculate_sprint_confidence(df, full_df=None):
    """Calculate confidence in sprint goal completion based on velocity and current progress"""
    metrics = calculate_metrics(df)
    # Use full_df (all sprints) for last-3-sprint velocity; fall back to df if not provided
    velocity_metrics = get_velocity_metrics(full_df if full_df is not None else df)
    
    # Current completion rate
    current_completion = metrics['completion_rate']
    
    # Velocity-based prediction (assuming avg velocity continues)
    # Predict: completed + (avg_velocity on remaining work) 
    if metrics['total_sp'] > 0:
        # Simplified: ratio of avg velocity to total story points
        velocity_factor = (velocity_metrics['avg_velocity'] / metrics['total_sp']) * 100
        # Blend current progress with velocity trend
        predicted_completion = current_completion + (velocity_factor * 0.3)  # 30% weight for velocity
        predicted_completion = min(predicted_completion, 100)  # Cap at 100%
    else:
        predicted_completion = 0
    
    return {
        "current_completion": current_completion,
        "predicted_completion": predicted_completion,
        "confidence": predicted_completion
    }

def prepare_llm_summary(df, full_df=None):
    """Prepare sprint data summary for LLM analysis — scoped to current sprint."""
    full_df = full_df if full_df is not None else df

    # Scope to current sprint (same as Metrics tab)
    current_sprint_df, current_sprint_name = get_current_sprint_df(df)
    if current_sprint_df.empty:
        current_sprint_df = df

    metrics = calculate_metrics(current_sprint_df)
    velocity_metrics = get_velocity_metrics(full_df)

    # DPM-mode: derive SP from Committed/Completed when StoryPoints all zero
    dpm_mode = (
        {"Committed", "Completed"}.issubset(current_sprint_df.columns)
        and metrics["total_sp"] == 0
    )
    if dpm_mode:
        committed = pd.to_numeric(current_sprint_df["Committed"], errors="coerce").fillna(0).sum()
        completed = pd.to_numeric(current_sprint_df["Completed"], errors="coerce").fillna(0).sum()
        remaining = max(0, committed - completed)
        completion_rate = (completed / committed * 100) if committed > 0 else 0
        risk_pct = (remaining / committed * 100) if committed > 0 else 0
        metrics["total_sp"] = committed
        metrics["completed_sp"] = completed
        metrics["remaining_sp"] = remaining
        metrics["completion_rate"] = completion_rate
        metrics["risk_percentage"] = risk_pct
        metrics["todo_sp"] = remaining
        metrics["in_progress_sp"] = 0
        metrics["blocked_count"] = 0

    blocked_items = current_sprint_df[
        current_sprint_df.get("Blocked", pd.Series(dtype=str)).astype(str).str.strip().str.lower() == "yes"
    ] if "Blocked" in current_sprint_df.columns else pd.DataFrame()

    summary = f"""
    CURRENT SPRINT: {current_sprint_name or 'Unknown'}

    CURRENT SPRINT METRICS:
    - Total Story Points: {metrics['total_sp']}
    - Completed Story Points: {metrics['completed_sp']}
    - In Progress Story Points: {metrics['in_progress_sp']}
    - To Do Story Points: {metrics['todo_sp']}
    - Completion Rate: {metrics['completion_rate']:.0f}%
    - Risk Percentage: {metrics['risk_percentage']:.0f}%
    - Blocked Items: {metrics['blocked_count']}
    - Average Velocity (last 3 sprints): {velocity_metrics['avg_velocity']:.0f} SP
    - Velocity Trend: {velocity_metrics['velocity_trend']}
    """

    sprints_summary = get_sprint_summary(full_df)
    if sprints_summary:
        summary += "\n    HISTORICAL SPRINT DATA:\n"
        for sprint_name, stats in sorted(sprints_summary.items()):
            sprint_completion = (stats['Done'] / stats['Total'] * 100) if stats['Total'] > 0 else 0
            summary += f"\n    {sprint_name}: {stats['Done']}/{stats['Total']} points completed ({sprint_completion:.0f}%)"

    if not blocked_items.empty and "Story" in blocked_items.columns:
        summary += "\n\n    BLOCKED ITEMS:\n"
        for _, item in blocked_items.iterrows():
            summary += f"    - {item['Story']} ({item.get('Sprint','?')}): {item.get('Status','?')}\n"

    return summary

def get_api_key():
    """Get Groq API key from Streamlit secrets or environment"""
    try:
        if hasattr(st, 'secrets') and 'GROQ_API_KEY' in st.secrets:
            return st.secrets['GROQ_API_KEY']
    except:
        pass
    
    return os.getenv("GROQ_API_KEY", "")

def generate_ai_insights(df, project_context="agile software delivery", full_df=None):
    """Generate AI-powered insights using Groq with structured metrics"""
    api_key = get_api_key()
    
    if not api_key:
        st.error("❌ Groq API Key not configured. Please add it to Streamlit Cloud Secrets.")
        return None
    
    try:
        client = Groq(api_key=api_key)
        
        # Calculate metrics for the prompt
        metrics = calculate_metrics(df)
        
        # Calculate percentages
        total_sp = metrics['total_sp']
        remaining_pct = (metrics['remaining_sp'] / total_sp * 100) if total_sp > 0 else 0
        not_started_pct = (metrics['todo_sp'] / total_sp * 100) if total_sp > 0 else 0
        blocker_pct = (metrics['blocked_sp'] / total_sp * 100) if total_sp > 0 else 0
        risk_pct = metrics['risk_percentage']
        
        # Velocity gap based on avg velocity from last 3 completed sprints vs required remaining work
        velocity_metrics = get_velocity_metrics(full_df if full_df is not None else df)
        avg_velocity = velocity_metrics['avg_velocity']
        velocity_gap_pct = (metrics['remaining_sp'] - avg_velocity) / total_sp * 100 if total_sp > 0 else 0
        
        # Historical context from completed sprints
        completed_health_df = get_completed_sprint_health(full_df if full_df is not None else df)
        avg_predictability = completed_health_df["Predictability %"].mean() if not completed_health_df.empty else 0
        
        # Decision thresholds
        if risk_pct > RISK_HIGH_THRESHOLD or remaining_pct > RISK_REMAINING_HIGH:
            sprint_verdict = "HIGH RISK"
        elif risk_pct > RISK_MODERATE_THRESHOLD:
            sprint_verdict = "AT RISK"
        else:
            sprint_verdict = "ON TRACK"
        
        # Pattern detection
        patterns = []
        if blocker_pct > BLOCKER_PCT_THRESHOLD:
            patterns.append("High blocker dependency")
        if not_started_pct > NOT_STARTED_PCT_THRESHOLD:
            patterns.append("Poor sprint planning")
        if velocity_gap_pct > VELOCITY_GAP_THRESHOLD:
            patterns.append("Velocity mismatch")
        pattern_text = ", ".join(patterns) if patterns else "No critical patterns detected"
        
        prompt = f"""You are a Senior Scrum Master and SAFe RTE with 12+ years of experience.

You are NOT an analyst. You are a DELIVERY COACH.
You challenge the team. You do not give polite answers.

Your job:
- Diagnose sprint health
- Predict outcome
- Give strict, practical actions

SPRINT DATA:

Remaining Work: {remaining_pct:.0f}%
Blocked Work: {blocker_pct:.0f}%
Not Started Work: {not_started_pct:.0f}%
Velocity Gap: {velocity_gap_pct:.0f}%
Risk Level: {risk_pct:.0f}%
Current Completion: {metrics['completion_rate']:.0f}%
Blocked Items: {metrics['blocked_count']}
Average Predictability (last sprints): {avg_predictability:.0f}%
Velocity Trend: {velocity_metrics['velocity_trend']}
Average Velocity: {avg_velocity:.0f} SP
System Assessment: {sprint_verdict}
Detected Patterns: {pattern_text}

---

Respond STRICTLY in this format:

🚦 SPRINT VERDICT:
(Will sprint succeed or fail? Be bold.)

🔍 ROOT CAUSE:
(Top 2–3 real reasons — no generic statements)

⚠️ DELIVERY RISKS:
- (Specific, data-driven risks)

🎯 ACTION PLAN (Scrum Master must do tomorrow):
1.
2.
3.

📈 IMPACT IF ACTION TAKEN:
(What improvement will happen in % terms)

---

Rules:
- Be direct, no fluff
- No generic agile theory
- Use numbers from data
- Sound like a real Scrum Master in a tough sprint
- Do NOT exceed 150 words
- Avoid repeating metrics
- Be crisp and assertive"""
        
        with st.spinner("🧠 AI is analyzing your sprint data..."):
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",  # Fast, stable, and supported
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1200
                )
            except Exception as e:
                # Fallback to another model if primary fails
                st.warning(f"⚠️ Primary model busy, trying backup model...")
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1200
                )
        
        return response.choices[0].message.content
    
    except Exception as e:
        st.error(f"❌ Error calling Groq API: {str(e)}")
        return None

def chat_with_ai(df, user_question, chat_history=None, full_df=None):
    """Generative coaching chat grounded in current sprint data."""
    api_key = get_api_key()

    if not api_key:
        return "❌ Error: Groq API Key not configured. Please contact admin to add it to Streamlit Cloud Secrets."

    try:
        client = Groq(api_key=api_key)

        summary = prepare_llm_summary(df, full_df=full_df if full_df is not None else df)

        history_block = ""
        if chat_history:
            tail_history = chat_history[-6:]
            history_lines = []
            for msg in tail_history:
                role = str(msg.get("role", "user")).upper()
                content = str(msg.get("content", "")).strip()
                if content:
                    history_lines.append(f"{role}: {content}")
            if history_lines:
                history_block = "\nRECENT CHAT CONTEXT:\n" + "\n".join(history_lines)

        prompt = f"""You are an expert Scrum Master and Team Coach.

Your behavior:
- Be generative and coaching-first, not rule-based
- Diagnose root causes before giving solutions
- Use sprint evidence and agile principles together
- Identify anti-patterns and call them out clearly
- Recommend practical next actions for Scrum Masters, PO, and team
- Help decision-making with trade-offs (scope, quality, timeline, focus)

Agile anti-pattern examples to detect when relevant:
- Too much carryover between sprints
- Daily Scrum becoming status reporting to manager
- Work started but not finished (high WIP)
- Stories entering sprint without refinement/DoR
- High blocker aging or unresolved dependencies
- Late testing and batch handoffs
- Velocity gaming or overcommitment

Decision support style:
- Give a clear recommendation
- Include 2 alternatives and when to choose each
- Mention risks if no action is taken

SPRINT DATA CONTEXT:
{summary}
{history_block}

USER QUESTION: {user_question}

Respond in this structure:
1) Coach Verdict
2) Evidence from Data
3) Anti-patterns observed (if any)
4) Recommended action plan (next 24h and this sprint)
5) Decision options and trade-offs
6) Expected impact and what to monitor

Constraints:
- Keep response practical and specific
- Use numbers from data when available
- Avoid generic textbook agile advice
- Keep under 220 words unless user asks for deep dive"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1200
            )
        except Exception:
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1200
            )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

# Read data from uploaded file (if available), else fallback to default CSV
df = None
data_source_label = "default CSV"
if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            uploaded_file.seek(0)
            df = pd.read_csv(uploaded_file)
            # Retry with semicolon for CSV exports that are not comma-separated.
            if len(df.columns) == 1 and ";" in str(df.columns[0]):
                uploaded_file.seek(0)
                df = pd.read_csv(uploaded_file, sep=";")
        else:
            uploaded_file.seek(0)
            df = pd.read_excel(uploaded_file)
        df = normalize_dataframe_columns(df)
        data_source_label = f"uploaded file: {uploaded_file.name}"
        st.sidebar.success(f"✅ Using uploaded sprint data ({len(df)} rows)")
    except Exception as e:
        st.sidebar.error(f"❌ Upload error: {e}")

if df is None:
    if uploaded_file is not None:
        st.error("Uploaded file could not be read. Please verify file format/columns. Default data was not used.")
        st.stop()
    df = read_from_csv()

if df is not None:
    # Normalize uploaded data so tabs don't crash when optional sprint columns are missing.
    if 'Sprint' not in df.columns:
        df['Sprint'] = 'Sprint 1'
    if 'Status' not in df.columns:
        df['Status'] = 'To Do'
    if 'StoryPoints' not in df.columns:
        df['StoryPoints'] = 0
    if 'Blocked' not in df.columns:
        df['Blocked'] = 'No'
    if 'Story' not in df.columns:
        df['Story'] = ''

if df is not None:
    # Create tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 All Data", "📈 Sprint Summary", "🎯 Metrics", "🧠 AI Coach", "🅳 DPM"])
    # Tab 1: All Data
    with tab1:
        st.subheader("Sprint Data Table")
        st.caption(f"Data source: {data_source_label}")
        st.dataframe(df, width='stretch', height=400)
        st.metric("Total Rows", len(df))
    
    # Tab 2: Sprint Summary
    with tab2:
        st.subheader("🏁 Sprint Health Summary")
        completed_health_df_tab2 = get_completed_sprint_health(df)
        if not completed_health_df_tab2.empty:
            st.dataframe(
                completed_health_df_tab2[["Sprint", "Sprint Health %", "Status", "Predictability %"]].reset_index(drop=True),
                use_container_width=True,
            )
        else:
            st.info("No completed sprints found yet. Sprint health status will appear once a sprint reaches 100% completion.")
    
    # Tab 3: Metrics
    with tab3:
        current_sprint_df, current_sprint_name = get_current_sprint_df(df)
        completed_health_df = get_completed_sprint_health(df)
        metrics = calculate_advanced_metrics(current_sprint_df, df)

        # DPM-mode fallback: if StoryPoints model is not available, derive from Committed/Completed.
        dpm_mode = (
            {"Committed", "Completed"}.issubset(current_sprint_df.columns)
            and metrics["total_sp"] == 0
        )
        if dpm_mode:
            dpm_committed = pd.to_numeric(current_sprint_df["Committed"], errors="coerce").fillna(0).sum()
            dpm_completed = pd.to_numeric(current_sprint_df["Completed"], errors="coerce").fillna(0).sum()
            dpm_remaining = max(0, dpm_committed - dpm_completed)
            metrics["total_sp"] = dpm_committed
            metrics["completed_sp"] = dpm_completed
            metrics["remaining_sp"] = dpm_remaining
            metrics["risk"] = round((dpm_remaining / dpm_committed * 100) if dpm_committed > 0 else 0)

        # ── 1. CURRENT SPRINT HEALTH (top view) ──────────────────────────
        st.subheader(f"🚦 Current Sprint Health ({current_sprint_name})" if current_sprint_name else "🚦 Current Sprint Health")

        total_sp = metrics["total_sp"]
        completed_sp = metrics["completed_sp"]
        remaining_sp = metrics["remaining_sp"]

        # Traffic signal
        confidence_metrics_top = calculate_sprint_confidence(current_sprint_df, df)
        velocity_metrics_top = get_velocity_metrics(df)
        avg_velocity_top = velocity_metrics_top["avg_velocity"]
        if dpm_mode and {"Completed"}.issubset(df.columns):
            avg_velocity_top = pd.to_numeric(df["Completed"], errors="coerce").fillna(0).mean()
        predicted_completion_sp_top = min(total_sp, completed_sp + avg_velocity_top)
        success_probability_top = (predicted_completion_sp_top / total_sp) * 100 if total_sp > 0 else 0

        if success_probability_top >= 85:
            sig_color = "#28a745"; sig_label = "ON TRACK"
        elif success_probability_top >= 60:
            sig_color = "#ffc107"; sig_label = "AT RISK"
        else:
            sig_color = "#dc3545"; sig_label = "HIGH RISK"

        st.markdown(f"""
<div style="display:flex; align-items:center; gap:10px; margin: 4px 0 12px 0;">
  <div style="width:18px; height:18px; border-radius:50%; background:{sig_color};
              box-shadow: 0 0 8px {sig_color}; flex-shrink:0;"></div>
  <span style="font-size:0.95rem; font-weight:600; color:#C9D1D9;">
    Sprint Health: <strong style="color:{sig_color};">{sig_label}</strong>
    &nbsp;·&nbsp; {round(success_probability_top)}% Confidence
  </span>
</div>
""", unsafe_allow_html=True)

        # SP metric cards
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total SP", metrics["total_sp"])
        col2.metric("Completed SP", metrics["completed_sp"])
        col3.metric("Remaining SP", metrics["remaining_sp"])
        col4.metric("Risk %", f"{metrics['risk']}%")

        # ── 3. CURRENT SPRINT SPILLOVER PREDICTION — line chart ──────────
        st.markdown("---")
        st.subheader("📅 Current Sprint Spillover Prediction")

        SPRINT_END_DATE = datetime.date(2026, 4, 7)
        SPRINT_DURATION_DAYS = 10

        _done_status = {"done", "completed", "complete", "closed", "resolved", "finished"}
        _todo_status = {"to do", "todo", "not started", "open", "new", "backlog", "planned", "ready"}

        if dpm_mode:
            committed_sp = pd.to_numeric(current_sprint_df["Committed"], errors="coerce").fillna(0).sum()
            completed_sp_summary = pd.to_numeric(current_sprint_df["Completed"], errors="coerce").fillna(0).sum()
            todo_sp = max(0, committed_sp - completed_sp_summary)
        else:
            committed_sp = pd.to_numeric(current_sprint_df["StoryPoints"], errors="coerce").sum() if not current_sprint_df.empty else 0
            completed_sp_summary = pd.to_numeric(
                current_sprint_df.loc[current_sprint_df["Status"].astype(str).str.strip().str.lower().isin(_done_status), "StoryPoints"],
                errors="coerce"
            ).sum() if not current_sprint_df.empty else 0
            todo_sp = pd.to_numeric(
                current_sprint_df.loc[current_sprint_df["Status"].astype(str).str.strip().str.lower().isin(_todo_status), "StoryPoints"],
                errors="coerce"
            ).sum() if not current_sprint_df.empty else 0

        remaining_sp_summary = max(0, committed_sp - completed_sp_summary)
        ideal_burn_rate = committed_sp / SPRINT_DURATION_DAYS if SPRINT_DURATION_DAYS > 0 else 0
        today = datetime.date.today()
        remaining_days = (SPRINT_END_DATE - today).days
        required_burn_rate = remaining_sp_summary / remaining_days if remaining_days > 0 else remaining_sp_summary

        # Keep confidence and spillover aligned by using one shared forecast model.
        forecast_spillover_sp = max(0, total_sp - predicted_completion_sp_top)
        spillover_risk_pct = (forecast_spillover_sp / total_sp * 100) if total_sp > 0 else 0

        days_elapsed = SPRINT_DURATION_DAYS - max(0, remaining_days)
        ideal_line = [committed_sp - ideal_burn_rate * d for d in range(SPRINT_DURATION_DAYS + 1)]
        actual_line = [committed_sp] + [None] * SPRINT_DURATION_DAYS
        for d in range(1, days_elapsed + 1):
            burned = ideal_burn_rate * d
            actual_line[d] = max(0, committed_sp - burned)
        actual_line[days_elapsed] = remaining_sp_summary

        day_labels = [f"D{d}" for d in range(SPRINT_DURATION_DAYS + 1)]
        
        # ── Spillover Risk Banner ──────────────────────────────────────────
        if spillover_risk_pct < 15:
            risk_color = "#28a745"
            risk_text = "🟢 LOW RISK"
        elif spillover_risk_pct < 30:
            risk_color = "#fd7e14"
            risk_text = "🟡 MODERATE RISK"
        else:
            risk_color = "#dc3545"
            risk_text = "🔴 HIGH RISK"

        st.markdown(f"""
<div style="
background-color:{risk_color};
padding:20px 25px;
border-radius:14px;
text-align:center;
font-size:24px;
font-weight:bold;
color:white;
margin-bottom:16px;
box-shadow: 0 4px 12px rgba(0,0,0,0.3);">
{risk_text} &nbsp;·&nbsp; {round(spillover_risk_pct)}% Spillover Risk
</div>
""", unsafe_allow_html=True)

        # ── Delivery Snapshot ─────────────────────────────────────────────
        st.markdown("**🟦 Delivery Snapshot**")
        ds_col1, ds_col2 = st.columns(2)
        ds_col1.metric("📦 Committed", f"{round(committed_sp)} SP")
        ds_col2.metric("✅ Completed", f"{round(completed_sp_summary)} SP")

        # ── Execution Speed ───────────────────────────────────────────────
        st.markdown("**⚡ Execution Speed**")
        es_col1, es_col2 = st.columns(2)
        es_col1.metric("🔥 Ideal Burn Rate", f"{round(ideal_burn_rate, 1)} SP/day")
        es_col2.metric("⚡ Required Burn Rate", f"{round(required_burn_rate, 1)} SP/day")

        # ── Burn Rate Gap ─────────────────────────────────────────────────
        burn_gap = round(required_burn_rate - ideal_burn_rate, 2)
        st.metric(
            "📉 Burn Rate Gap (Required − Ideal)",
            f"{burn_gap} SP/day",
            delta=burn_gap,
            delta_color="inverse",
        )

        # ── Progress Bar ──────────────────────────────────────────────────
        progress_pct = (completed_sp_summary / committed_sp * 100) if committed_sp > 0 else 0
        st.progress(min(int(progress_pct), 100))
        st.caption(
            f"{round(progress_pct, 1)}% Completed  ·  Sprint end: {SPRINT_END_DATE}  ·  "
            f"{max(0, remaining_days)} days remaining  ·  {round(remaining_sp_summary)} SP remaining"
        )

        # ── Executive Insight ─────────────────────────────────────────────
        if committed_sp == 0:
            st.info("ℹ️ No active sprint data available.")
        elif required_burn_rate > ideal_burn_rate:
            st.error("⚠️ Current pace is insufficient. Risk of spillover — team needs to accelerate.")
        else:
            st.success("✅ Current pace is sufficient to meet the sprint goal.")

        # ── 4. PREDICTIVE ANALYSIS ────────────────────────────────────────
        confidence_metrics = calculate_sprint_confidence(current_sprint_df, df)
        velocity_metrics = get_velocity_metrics(df)
        avg_velocity = velocity_metrics["avg_velocity"]
        if dpm_mode and {"Completed"}.issubset(df.columns):
            avg_velocity = pd.to_numeric(df["Completed"], errors="coerce").fillna(0).mean()

        predicted_completion_sp = min(total_sp, completed_sp + avg_velocity)
        success_probability = (predicted_completion_sp / total_sp) * 100 if total_sp > 0 else 0
        spillover_sp = max(0, total_sp - predicted_completion_sp)

        active_df = current_sprint_df
        blocked = len(active_df[active_df['Blocked'].astype(str).str.strip().str.lower() == 'yes']) if not dpm_mode else 0
        not_started = len(active_df[active_df['Status'].astype(str).str.strip().str.lower().isin(_todo_status)]) if not dpm_mode else 0
        remaining_pct = (remaining_sp / total_sp) * 100 if total_sp > 0 else 0
        blocked_pct = (blocked / len(active_df)) * 100 if len(active_df) > 0 else 0
        not_started_pct = (not_started / len(active_df)) * 100 if len(active_df) > 0 else 0

        risk_index = 0.4 * remaining_pct + 0.3 * blocked_pct + 0.3 * not_started_pct
        avg_predictability = completed_health_df["Predictability %"].mean() if not completed_health_df.empty else confidence_metrics["current_completion"]
        confidence_score = 0.5 * avg_predictability - 0.2 * blocked_pct - 0.2 * remaining_pct

        st.markdown("---")
        st.markdown("### 🔮 Predictive Analysis")

        import plotly.graph_objects as go

        # Gauge — small, centered
        gauge_col1, gauge_col2, gauge_col3 = st.columns([1.5, 2, 1.5])
        with gauge_col2:
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=success_probability,
                title={'text': "Success Probability (%)", 'font': {'size': 12}},
                number={'font': {'size': 28}},
                gauge={
                    'axis': {'range': [0, 100], 'tickfont': {'size': 9}},
                    'bar': {'color': "black", 'thickness': 0.2},
                    'steps': [
                        {'range': [0, 60], 'color': "red"},
                        {'range': [60, 85], 'color': "orange"},
                        {'range': [85, 100], 'color': "green"},
                    ],
                    'threshold': {
                        'line': {'color': "white", 'width': 3},
                        'thickness': 0.75,
                        'value': success_probability,
                    },
                },
            ))
            fig_gauge.update_layout(margin=dict(t=30, b=5, l=10, r=10), height=200, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_gauge, use_container_width=True)

        with st.expander("📖 How is Success Probability measured?", expanded=False):
            st.markdown("""
            **Formula:** `(Completed SP + Average Velocity) / Total Committed SP × 100`
            
            - **Completed SP** — Story Points already finished in current sprint
            - **Average Velocity** — Mean SP completed per sprint (from historical data)
            - **Total Committed SP** — All Story Points committed for current sprint
            
            **Interpretation:**
            - 🟢 **≥85%** — On track, sprint goal likely achieved
            - 🟡 **60-85%** — At risk, may need scope adjustment
            - 🔴 **<60%** — High risk, immediate action required
            """)

        # --- WHAT IF SIMULATION ---
        st.markdown("---")
        st.subheader("🔮 What-If Analysis")
        extra_sp = st.slider("If additional SP completed:", 0, 30, 5)

        sim_completed = min(total_sp, completed_sp + extra_sp)
        sim_remaining = max(0, total_sp - sim_completed)
        sim_predictability = (sim_completed / total_sp * 100) if total_sp > 0 else 0
        sim_spillover = (sim_remaining / total_sp * 100) if total_sp > 0 else 0
        avg_velocity = velocity_metrics["avg_velocity"]
        sprints_needed = sim_remaining / avg_velocity if avg_velocity > 0 else 0
        sim_confidence = 0.5 * sim_predictability - 0.3 * sim_spillover

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📈 Predictability", f"{round(sim_predictability)}%")
        c2.metric("📉 Spillover Risk", f"{round(sim_spillover)}%")
        c3.metric("⚡ Sprints Needed", f"{round(sprints_needed, 1)}")
        c4.metric("🎯 Confidence", f"{round(sim_confidence)}%")

        if sim_spillover > 30:
            st.error("🔴 High spillover risk even after improvement")
        elif sim_spillover > 15:
            st.warning("🟡 Moderate spillover risk")
        else:
            st.success("🟢 Spillover under control")

        st.info(
            f"👉 Completing +{extra_sp} SP improves predictability to {round(sim_predictability)}% "
            f"and reduces spillover to {round(sim_spillover)}%"
        )

        with st.expander("🧮 What-If Calculation Snapshot", expanded=False):
            st.markdown("""
            **How this block is calculated**

            - Simulated Completed SP = `min(Total SP, Completed SP + Additional SP)`
            - Simulated Remaining SP = `max(0, Total SP - Simulated Completed SP)`
            - Predictability % = `(Simulated Completed SP / Total SP) × 100`
            - Spillover Risk % = `(Simulated Remaining SP / Total SP) × 100`
            - Sprints Needed = `Simulated Remaining SP / Average Velocity`
            - Confidence Score = `0.5 × Predictability - 0.3 × Spillover`
            """)
    
    # Tab 4: AI Team Coach (Insights + Chat)
    with tab4:
        st.markdown("## 🧠 AI Team Coach")
        st.markdown("*Powered by Groq — Scrum Master and Agile Team Coaching Copilot*")

        # Check if API key is configured
        if not os.getenv("GROQ_API_KEY"):
            st.info("📝 Please enter your Groq API key in the sidebar (⚙️ Configuration) to enable AI insights.")
            st.markdown("""
            **Get Your FREE Groq API Key (No payment method needed!):**
            1. Go to [Groq Console](https://console.groq.com)
            2. Sign up with your email or GitHub
            3. Click "API Keys" in the left menu
            4. Click "Create API Key"
            5. Copy and paste it in the Configuration panel on the left
            
            **Why Groq?**
            ✅ Completely FREE - No payment required
            ✅ Super Fast - Instant analysis
            ✅ Powerful Models - Mixtral, Llama2, and more
            ✅ No Cost Limits - Generate unlimited insights
            """)
        else:
            # Get current sprint — same scope as Metrics tab
            current_sprint_df_ai, current_sprint_name_ai = get_current_sprint_df(df)

            # Derive success_probability the same way the Metrics tab does
            _adv = calculate_advanced_metrics(current_sprint_df_ai, df)
            _total_sp_ai = _adv["total_sp"]
            _completed_sp_ai = _adv["completed_sp"]
            # DPM fallback
            if _total_sp_ai == 0 and {"Committed", "Completed"}.issubset(current_sprint_df_ai.columns):
                _total_sp_ai = pd.to_numeric(current_sprint_df_ai["Committed"], errors="coerce").fillna(0).sum()
                _completed_sp_ai = pd.to_numeric(current_sprint_df_ai["Completed"], errors="coerce").fillna(0).sum()
            _vel_ai = get_velocity_metrics(df)["avg_velocity"]
            if _total_sp_ai == 0 and {"Completed"}.issubset(df.columns):
                _vel_ai = pd.to_numeric(df["Completed"], errors="coerce").fillna(0).mean()
            _pred_ai = min(_total_sp_ai, _completed_sp_ai + _vel_ai)
            ai_success_prob = (_pred_ai / _total_sp_ai * 100) if _total_sp_ai > 0 else 0

            # Auto coaching alert banner — same thresholds as Metrics tab traffic signal
            if ai_success_prob < 60:
                st.error(f"🚨 AI Alert: High risk — {round(ai_success_prob)}% success probability. Immediate action required.")
            elif ai_success_prob < 85:
                st.warning(f"⚠️ AI Alert: Sprint is at risk — {round(ai_success_prob)}% success probability. Monitor closely.")
            else:
                st.success(f"✅ AI Alert: Sprint on track — {round(ai_success_prob)}% success probability.")

            st.markdown("---")

            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col2:
                if st.button("🚀 Generate AI Insights", use_container_width=True):
                    insights = generate_ai_insights(current_sprint_df_ai, full_df=df)
                    
                    if insights:
                        st.session_state.ai_insights = insights

            with col3:
                if "ai_insights" in st.session_state and st.session_state.ai_insights:
                    st.download_button(
                        label="⬇️ Download",
                        data=st.session_state.ai_insights,
                        file_name="sprint_ai_insights.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
            
            # Display cached insights
            if "ai_insights" in st.session_state and st.session_state.ai_insights:
                st.markdown(st.session_state.ai_insights)
            else:
                st.info("💡 Click 'Generate AI Insights' to get a data-driven coaching verdict from your AI Delivery Coach.")

            st.markdown("---")
            st.subheader("💬 Team Coach Chat")
            st.caption("Generative Scrum coaching: anti-pattern detection, agile practice suggestions, and decision guidance.")
            st.markdown("""
            **Ask your AI Team Coach:**
            - "How can we improve our velocity?"
            - "What should we do about the blocked items?"
            - "Which sprint is at risk?"
            - "Which agile anti-patterns do you see and what should I change this week?"
            """)
            
            # Quick question suggestion buttons
            st.markdown("### 💡 Quick Questions")
            chat_q_col1, chat_q_col2, chat_q_col3 = st.columns(3)
            preset_question = None
            with chat_q_col1:
                if st.button("Will we meet sprint goal?", key="chat_q1", use_container_width=True):
                    preset_question = "Will we meet sprint goal?"
            with chat_q_col2:
                if st.button("What should I do today?", key="chat_q2", use_container_width=True):
                    preset_question = "What should I do today as Scrum Master?"
            with chat_q_col3:
                if st.button("Biggest risk right now?", key="chat_q3", use_container_width=True):
                    preset_question = "What is the biggest risk right now?"
            
            # Initialize chat history in session state
            if "chat_history" not in st.session_state:
                st.session_state.chat_history = []

            # Clear chat button
            if st.session_state.chat_history:
                if st.button("🗑️ Clear Chat History", use_container_width=False):
                    st.session_state.chat_history = []
                    st.rerun()
            
            # Display chat history
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
            
            # Handle preset quick questions
            if preset_question:
                st.session_state.chat_history.append({"role": "user", "content": preset_question})
                with st.chat_message("user"):
                    st.markdown(preset_question)
                with st.chat_message("assistant"):
                    with st.spinner("🤔 Thinking..."):
                        response = chat_with_ai(current_sprint_df_ai, preset_question, st.session_state.chat_history, full_df=df)
                        st.markdown(response)
                st.session_state.chat_history.append({"role": "assistant", "content": response})

            # Chat input
            user_input = st.chat_input("Ask a question about your sprint...")
            
            if user_input:
                # Add user message to history
                st.session_state.chat_history.append({"role": "user", "content": user_input})
                
                # Display user message
                with st.chat_message("user"):
                    st.markdown(user_input)
                
                # Get AI response
                with st.chat_message("assistant"):
                    with st.spinner("🤔 Thinking..."):
                        response = chat_with_ai(current_sprint_df_ai, user_input, st.session_state.chat_history, full_df=df)
                        st.markdown(response)
                    
                    # Add assistant response to history
                    st.session_state.chat_history.append({"role": "assistant", "content": response})

    # Tab 5: Delivery Performance Metrics
    with tab5:
        st.subheader("🅳 Delivery Performance Metrics")

        dpm_uploaded_file = st.file_uploader(
            "Upload Sprint Data",
            type=["csv", "xlsx"],
            key="dpm_uploaded_file",
        )

        dpm_data = None
        if dpm_uploaded_file:
            try:
                if dpm_uploaded_file.name.lower().endswith(".csv"):
                    dpm_data = pd.read_csv(dpm_uploaded_file)
                else:
                    dpm_data = pd.read_excel(dpm_uploaded_file)
            except Exception as e:
                st.error(f"Unable to read uploaded file: {e}")

        if dpm_data is None and all(col in df.columns for col in ["Sprint", "Committed", "Completed"]):
            dpm_data = df.copy()
            st.info("Using current loaded data for DPM. Upload a file to override.")

        # Derive DPM data from story-level upload (StoryPoints + Status)
        if dpm_data is None and all(col in df.columns for col in ["Sprint", "StoryPoints", "Status"]):
            _sp = pd.to_numeric(df["StoryPoints"], errors="coerce").fillna(0)
            _df_sp = df.copy()
            _df_sp["StoryPoints"] = _sp
            committed_agg = _df_sp.groupby("Sprint")["StoryPoints"].sum().reset_index().rename(columns={"StoryPoints": "Committed"})
            _done = ["done", "completed", "complete", "closed", "resolved", "finished"]
            completed_agg = (
                _df_sp[_df_sp["Status"].str.strip().str.lower().isin(_done)]
                .groupby("Sprint")["StoryPoints"]
                .sum()
                .reset_index()
                .rename(columns={"StoryPoints": "Completed"})
            )
            dpm_data = committed_agg.merge(completed_agg, on="Sprint", how="left").fillna(0)
            st.info("Showing DPM derived from story-level data (Committed = total SP per sprint, Completed = Done SP per sprint).")

        if dpm_data is None:
            st.warning("Upload a CSV/XLSX with Sprint, Committed, Completed columns to view DPM.")
        else:
            required_cols = ["Sprint", "Committed", "Completed"]

            if not all(col in dpm_data.columns for col in required_cols):
                st.error("Data must contain: Sprint, Committed, Completed")
            else:
                dpm_df = dpm_data.copy()
                dpm_df["Committed"] = pd.to_numeric(dpm_df["Committed"], errors="coerce").fillna(0)
                dpm_df["Completed"] = pd.to_numeric(dpm_df["Completed"], errors="coerce").fillna(0)

                # Take last 6 sprints (dynamic)
                dpm_df = dpm_df.tail(6)

                # Calculate average velocity
                avg_velocity = dpm_df["Completed"].mean()

                # Assign colors
                dpm_df["Color"] = dpm_df["Completed"].apply(
                    lambda x: "green" if x > avg_velocity else "red"
                )

                import numpy as np
                import matplotlib.pyplot as plt

                # Compact D map (dot-style) to reduce footprint.
                fig, ax = plt.subplots(figsize=(3.2, 1.9))

                radius = 0.62
                center_x = -0.58
                center_y = 0.0
                d_line_width = 1.6

                # Draw subtle D guide.
                ax.plot(
                    [center_x, center_x],
                    [center_y - radius, center_y + radius],
                    linewidth=d_line_width,
                    color="#334155",
                    alpha=0.85,
                    solid_capstyle="round",
                )
                theta_curve = np.linspace(-np.pi / 2, np.pi / 2, 120)
                x_curve = center_x + radius * np.cos(theta_curve)
                y_curve = center_y + radius * np.sin(theta_curve)
                ax.plot(
                    x_curve,
                    y_curve,
                    linewidth=d_line_width,
                    color="#475569",
                    alpha=0.7,
                    solid_capstyle="round",
                )

                # Place sprint markers on the curve.
                theta = np.linspace(np.pi / 2, -np.pi / 2, len(dpm_df))
                x = center_x + radius * np.cos(theta)
                y = center_y + radius * np.sin(theta)
                marker_colors = ["#4ade80" if color == "green" else "#f43f5e" for color in dpm_df["Color"]]

                ax.scatter(
                    x,
                    y,
                    s=54,
                    c=marker_colors,
                    edgecolors="#e5e7eb",
                    linewidths=0.6,
                    zorder=4,
                )

                for i in range(len(dpm_df)):
                    sprint = dpm_df.iloc[i]
                    ax.text(
                        x[i] + 0.06,
                        y[i],
                        f"{sprint['Sprint']}",
                        ha="left",
                        va="center",
                        fontsize=6,
                        color="#0f172a",
                        bbox=dict(
                            boxstyle="round,pad=0.08",
                            facecolor="#f8fafc",
                            edgecolor="none",
                            alpha=0.9,
                        ),
                    )

                ax.set_aspect("equal")
                ax.set_xlim(-1.06, 0.18)
                ax.set_ylim(-0.72, 0.72)
                ax.axis("off")
                fig.tight_layout(pad=0.05)

                d_col1, d_col2, d_col3 = st.columns([1.2, 2.6, 1.2])
                with d_col2:
                    st.pyplot(fig, use_container_width=False)

                # Committed vs Completed chart
                st.subheader("📊 Committed vs Completed")
                from matplotlib.lines import Line2D
                from matplotlib.patches import Patch

                fig2, ax2 = plt.subplots(figsize=(8.2, 3.6))
                x_pos = np.arange(len(dpm_df))
                bar_width = 0.28  # slimmer columns

                committed_values = dpm_df["Committed"].to_numpy()
                completed_values = dpm_df["Completed"].to_numpy()
                completed_colors = [
                    "#16a34a" if value > avg_velocity else "#dc2626"
                    for value in completed_values
                ]

                committed_bars = ax2.bar(
                    x_pos - bar_width / 2,
                    committed_values,
                    width=bar_width,
                    color="#2563eb",
                    edgecolor="#1e3a8a",
                    linewidth=0.8,
                    zorder=3,
                    label="Committed",
                )
                completed_bars = ax2.bar(
                    x_pos + bar_width / 2,
                    completed_values,
                    width=bar_width,
                    color=completed_colors,
                    edgecolor="#111827",
                    linewidth=0.8,
                    zorder=3,
                    label="Completed",
                )

                # Draw a strong average-velocity line across the full chart width.
                avg_x = np.array([-0.6, len(dpm_df) - 0.4])
                avg_y = np.array([avg_velocity, avg_velocity])
                ax2.plot(
                    avg_x,
                    avg_y,
                    color="#f59e0b",
                    linewidth=3.0,
                    linestyle="--",
                    marker="o",
                    markersize=4,
                    zorder=6,
                    label="Average Velocity",
                )

                ax2.set_xticks(x_pos)
                ax2.set_xticklabels(dpm_df["Sprint"].astype(str), fontsize=9)
                ax2.set_ylabel("Story Points", fontsize=9)
                ax2.set_title("Committed vs Completed with Average Velocity", fontsize=11, pad=10)
                ax2.set_xlim(-0.6, len(dpm_df) - 0.4)

                y_max = max(float(committed_values.max(initial=0)), float(completed_values.max(initial=0)), float(avg_velocity))
                ax2.set_ylim(0, y_max * 1.22 if y_max > 0 else 1)

                ax2.text(
                    len(dpm_df) - 0.42,
                    avg_velocity,
                    f"Avg {avg_velocity:.1f}",
                    color="#92400e",
                    fontsize=8,
                    va="bottom",
                    ha="right",
                    bbox=dict(boxstyle="round,pad=0.2", facecolor="#fef3c7", edgecolor="#f59e0b"),
                    zorder=7,
                )

                # Keep chart clean: no grid lines.
                ax2.grid(False)
                ax2.yaxis.grid(False)
                ax2.xaxis.grid(False)
                ax2.spines["top"].set_visible(False)
                ax2.spines["right"].set_visible(False)

                for bar in list(committed_bars) + list(completed_bars):
                    height = bar.get_height()
                    ax2.text(
                        bar.get_x() + bar.get_width() / 2,
                        height + 0.6,
                        f"{int(round(height))}",
                        ha="center",
                        va="bottom",
                        fontsize=8,
                        color="#111827",
                    )

                legend_handles = [
                    Patch(facecolor="#2563eb", edgecolor="#1e3a8a", label="Committed"),
                    Patch(facecolor="#16a34a", edgecolor="#111827", label="Completed >= Avg"),
                    Patch(facecolor="#dc2626", edgecolor="#111827", label="Completed < Avg"),
                    Line2D([0], [0], color="#f59e0b", linewidth=2.0, label="Average Velocity"),
                ]
                ax2.legend(handles=legend_handles, loc="upper left", frameon=False, fontsize=8)

                fig2.tight_layout(pad=0.6)
                st.pyplot(fig2, use_container_width=True)

                # Legend
                st.markdown(
                    f"""
                    **Average Velocity:** {round(avg_velocity, 2)}

                    🟢 Above Avg Velocity  
                    🔴 Below Avg Velocity
                    """
                )
    
    st.markdown("---")
    st.markdown("*Last updated: Real-time from sprint_data.csv*")

elif df is None:
    st.warning("⚠️ No sprint data loaded. Please upload a CSV file in the sidebar.")

 
