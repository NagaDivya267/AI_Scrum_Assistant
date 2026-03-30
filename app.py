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
/* ── Header gradient banner ── */
h1 {
    background: linear-gradient(90deg, #00D4AA 0%, #6C63FF 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.4rem !important;
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
    font-size: 0.9rem;
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
    font-size: 1.8rem !important;
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
        return df
    except Exception as e:
        st.error(f"Error reading CSV: {e}")
        return None

def get_sprint_summary(df):
    """Generate summary statistics from DataFrame"""
    sprints = {}
    for _, row in df.iterrows():
        sprint = row['Sprint']
        status = row['Status']
        story_points = int(row['StoryPoints']) if isinstance(row['StoryPoints'], (int, float)) else 0
        
        if sprint not in sprints:
            sprints[sprint] = {"Done": 0, "In Progress": 0, "To Do": 0, "Total": 0}
        
        sprints[sprint]["Total"] += story_points
        sprints[sprint][status] = sprints[sprint].get(status, 0) + story_points
    
    return sprints

def calculate_metrics(df):
    """Calculate key metrics for the sprint"""
    sprints_summary = get_sprint_summary(df)
    
    total_story_points = sum(s["Total"] for s in sprints_summary.values())
    total_completed = sum(s["Done"] for s in sprints_summary.values())
    total_in_progress = sum(s["In Progress"] for s in sprints_summary.values())
    total_todo = sum(s["To Do"] for s in sprints_summary.values())
    blocked_mask = df['Blocked'].astype(str).str.strip().str.lower() == 'yes'
    blocked_count = blocked_mask.sum()
    blocked_sp = pd.to_numeric(df.loc[blocked_mask, 'StoryPoints'], errors='coerce').fillna(0).sum()
    
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
    return df[df['Sprint'] == current_sprint_name], current_sprint_name

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
        sprint_df = df[df['Sprint'] == sprint_name]
        committed_sp = pd.to_numeric(sprint_df['StoryPoints'], errors='coerce').fillna(0).sum()
        completed_sp = pd.to_numeric(
            sprint_df[sprint_df['Status'].astype(str).str.strip().str.lower() == 'done']['StoryPoints'],
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
    sprint_velocities = []
    for sprint_name in completed_sprint_names:
        sprint_df = df[df['Sprint'] == sprint_name]
        done_sp = pd.to_numeric(
            sprint_df[sprint_df['Status'].astype(str).str.strip().str.lower() == 'done']['StoryPoints'],
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

def prepare_llm_summary(df):
    """Prepare sprint data summary for LLM analysis"""
    metrics = calculate_metrics(df)
    sprints_summary = get_sprint_summary(df)
    blocked_items = df[df['Blocked'] == 'Yes']
    
    summary = f"""
    SPRINT DATA ANALYSIS REQUEST
    
    OVERALL METRICS:
    - Total Story Points: {metrics['total_sp']}
    - Completed Story Points: {metrics['completed_sp']}
    - In Progress Story Points: {metrics['in_progress_sp']}
    - To Do Story Points: {metrics['todo_sp']}
    - Completion Rate: {metrics['completion_rate']:.0f}%
    - Risk Percentage: {metrics['risk_percentage']:.0f}%
    - Blocked Items: {metrics['blocked_count']}
    
    SPRINT-WISE DATA:
    """
    
    for sprint_name, stats in sorted(sprints_summary.items()):
        sprint_completion = (stats['Done'] / stats['Total'] * 100) if stats['Total'] > 0 else 0
        summary += f"\n    {sprint_name}: {stats['Done']}/{stats['Total']} points completed ({sprint_completion:.0f}%)"
        summary += f"\n      - Done: {stats['Done']}, In Progress: {stats['In Progress']}, To Do: {stats['To Do']}"
    
    if len(blocked_items) > 0:
        summary += "\n\n    BLOCKED ITEMS:\n"
        for _, item in blocked_items.iterrows():
            summary += f"    - {item['Story']} ({item['Sprint']}): {item['Status']}\n"
    
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

def chat_with_ai(df, user_question):
    """Chat with AI about sprint data and provide suggestions"""
    api_key = get_api_key()
    
    if not api_key:
        return "❌ Error: Groq API Key not configured. Please contact admin to add it to Streamlit Cloud Secrets."
    
    try:
        client = Groq(api_key=api_key)
        
        summary = prepare_llm_summary(df)
        
        prompt = f"""You are a Delivery Manager + Scrum Master + Agile Coach with 10+ years of experience.

When answering:
- Always diagnose before suggesting
- Use sprint data
- Give actionable steps
- Avoid generic advice

SPRINT DATA CONTEXT:
{summary}

USER QUESTION: {user_question}

Based on the sprint data, answer the user's question comprehensively.

If they ask about:
- **Sprint Goal Achievement**: Analyze completion rate, velocity, and blockers to predict if they'll meet the goal
- **Key Risks**: Identify top 3-5 risks based on blocked items, incomplete work, and velocity trends
- **Scrum Master Actions**: Provide specific, actionable steps they can take immediately
- **Problem Solving**: Suggest root causes and solutions based on the data

Always include:
1. **Direct Answer** - Clear, data-backed response
2. **Supporting Data** - Use specific numbers from their sprint
3. **Action Items** - 2-3 concrete steps to take
4. **Success Metrics** - How to measure if actions worked

Be concise, practical, and focused on what matters most for sprint success."""
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast, stable, and actively supported
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1200
        )
        
        return response.choices[0].message.content
    
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

# Read data from uploaded file (if available), else fallback to default CSV
df = None
if uploaded_file is not None:
    try:
        if uploaded_file.name.lower().endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        st.sidebar.success("✅ Using uploaded sprint data")
    except Exception as e:
        st.sidebar.error(f"❌ Upload error: {e}")

if df is None:
    df = read_from_csv()
    pass

if df is not None:
    # Create tabs with new AI Insights tab and Chat tab
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 All Data", "📈 Sprint Summary", "🎯 Metrics", "🧠 AI Insights", "💬 Chat", "🅳 DPM"])
    # Tab 1: All Data
    with tab1:
        st.subheader("Sprint Data Table")
        st.dataframe(df, width='stretch', height=400)
        st.metric("Total Rows", len(df))
    
    # Tab 2: Sprint Summary
    with tab2:
        st.subheader("Sprint Completion Status")
        sprints_summary = get_sprint_summary(df)
        
        cols = st.columns(len(sprints_summary))
        for idx, (sprint_name, stats) in enumerate(sorted(sprints_summary.items())):
            with cols[idx]:
                completion = (stats["Done"] / stats["Total"] * 100) if stats["Total"] > 0 else 0
                st.metric(
                    label=sprint_name,
                    value=f"{completion:.0f}%",
                    delta=f"{stats['Done']}/{stats['Total']} pts"
                )
        
        # Detailed summary
        st.subheader("Detailed Sprint Breakdown")
        for sprint_name, stats in sorted(sprints_summary.items()):
            with st.expander(f"{sprint_name} - {stats['Done']}/{stats['Total']} pts"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Points", stats["Total"])
                with col2:
                    st.metric("✅ Done", stats["Done"])
                with col3:
                    st.metric("🔄 In Progress", stats["In Progress"])
                with col4:
                    st.metric("⏳ To Do", stats["To Do"])
    
    # Tab 3: Metrics
    with tab3:
        st.subheader("🤖 AI Sprint Health Advisor")
        current_sprint_df, current_sprint_name = get_current_sprint_df(df)

        # --- SPRINT METRICS ---
        st.markdown("### 📊 Sprint Metrics")

        # --- COMPLETED SPRINT HEALTH ---
        st.subheader("🏁 Sprint Health Status (Completed Sprints)")
        completed_health_df = get_completed_sprint_health(df)

        if not completed_health_df.empty:
            for i in range(0, len(completed_health_df), 3):
                card_cols = st.columns(3)
                for j in range(3):
                    row_idx = i + j
                    if row_idx < len(completed_health_df):
                        row = completed_health_df.iloc[row_idx]
                        with card_cols[j]:
                            st.metric(
                                label=row["Sprint"],
                                value=f"{row['Sprint Health %']}%",
                                delta=row["Status"]
                            )
        else:
            st.info("No completed sprints found yet. Sprint health status will appear once a sprint reaches 100% completion.")

        # --- METRICS ---
        st.subheader(f"🚦 Current Sprint Health Status ({current_sprint_name})" if current_sprint_name else "🚦 Current Sprint Health Status")
        metrics = calculate_advanced_metrics(current_sprint_df, df)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total SP", metrics["total_sp"])
        col2.metric("Completed SP", metrics["completed_sp"])
        col3.metric("Remaining SP", metrics["remaining_sp"])
        col4.metric("Risk %", f"{metrics['risk']}%")

        # --- BREAKDOWN ---
        st.subheader("📉 Risk Breakdown")
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Remaining Work %", f"{metrics['remaining_pct']}%")
        b2.metric("Blocked %", f"{metrics['blocker_pct']}%")
        b3.metric("Not Started %", f"{metrics['not_started_pct']}%")
        b4.metric("Velocity Gap %", f"{metrics['velocity_gap_pct']}%")

        # --- CURRENT SPRINT SUMMARY (date-based burn rate) ---
        st.markdown("---")
        st.subheader("📅 Current Sprint Spillover Prediction")

        SPRINT_END_DATE = datetime.date(2026, 4, 7)
        SPRINT_DURATION_DAYS = 10

        committed_sp = pd.to_numeric(current_sprint_df["StoryPoints"], errors="coerce").sum() if not current_sprint_df.empty else 0
        completed_sp_summary = pd.to_numeric(
            current_sprint_df.loc[current_sprint_df["Status"].astype(str).str.strip().str.lower() == "done", "StoryPoints"],
            errors="coerce"
        ).sum() if not current_sprint_df.empty else 0
        todo_sp = pd.to_numeric(
            current_sprint_df.loc[current_sprint_df["Status"].astype(str).str.strip().str.lower() == "to do", "StoryPoints"],
            errors="coerce"
        ).sum() if not current_sprint_df.empty else 0

        remaining_sp_summary = max(0, committed_sp - completed_sp_summary)
        ideal_burn_rate = committed_sp / SPRINT_DURATION_DAYS if SPRINT_DURATION_DAYS > 0 else 0

        today = datetime.date.today()
        remaining_days = (SPRINT_END_DATE - today).days
        if remaining_days > 0:
            required_burn_rate = remaining_sp_summary / remaining_days
        else:
            required_burn_rate = remaining_sp_summary  # all remaining SP due today or overdue

        spillover_risk_pct = (todo_sp / committed_sp * 100) if committed_sp > 0 else 0

        cs1, cs2, cs3, cs4, cs5 = st.columns(5)
        cs1.metric("Committed SP", round(committed_sp))
        cs2.metric("Ideal Burn Rate", f"{round(ideal_burn_rate)} SP/day")
        cs3.metric("Completed SP", round(completed_sp_summary))
        cs4.metric("Required Burn Rate", f"{round(required_burn_rate)} SP/day")
        cs5.metric("Predictive Spillover Risk", f"{round(spillover_risk_pct)}%")

        st.caption(
            f"Sprint end: {SPRINT_END_DATE} | Sprint duration: {SPRINT_DURATION_DAYS} days | "
            f"Remaining days: {max(0, remaining_days)} | Remaining SP: {round(remaining_sp_summary)}"
        )

        # --- PREDICTIVE KPIS ---
        confidence_metrics = calculate_sprint_confidence(current_sprint_df, df)
        velocity_metrics = get_velocity_metrics(df)

        total_sp = metrics["total_sp"]
        completed_sp = metrics["completed_sp"]
        remaining_sp = metrics["remaining_sp"]
        predicted_completion_sp = min(total_sp, completed_sp + velocity_metrics["avg_velocity"])

        success_probability = (predicted_completion_sp / total_sp) * 100 if total_sp > 0 else 0
        spillover_sp = max(0, total_sp - predicted_completion_sp)

        active_df = current_sprint_df
        blocked = len(active_df[active_df['Blocked'].astype(str).str.strip().str.lower() == 'yes'])
        not_started = len(active_df[active_df['Status'].astype(str).str.strip().str.lower() == 'to do'])

        remaining_pct = (remaining_sp / total_sp) * 100 if total_sp > 0 else 0
        blocked_pct = (blocked / len(active_df)) * 100 if len(active_df) > 0 else 0
        not_started_pct = (not_started / len(active_df)) * 100 if len(active_df) > 0 else 0

        risk_index = (
            0.4 * remaining_pct +
            0.3 * blocked_pct +
            0.3 * not_started_pct
        )

        avg_predictability = completed_health_df["Predictability %"].mean() if not completed_health_df.empty else confidence_metrics["current_completion"]
        confidence_score = (
            0.5 * avg_predictability -
            0.2 * blocked_pct -
            0.2 * remaining_pct
        )

        # --- PREDICTIVE ANALYSIS ---
        st.markdown("---")
        st.markdown("### 🔮 Predictive Analysis")

        st.markdown("""
<style>
.card {
    padding: 22px 16px;
    border-radius: 14px;
    color: #FAFAFA;
    text-align: center;
    font-size: 1.15rem;
    font-weight: 700;
    line-height: 1.6;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    border: 1px solid rgba(255,255,255,0.08);
    transition: transform 0.15s;
}
.card:hover { transform: translateY(-2px); }
.green  { background: linear-gradient(135deg, #1a7a4a, #28a745); }
.yellow { background: linear-gradient(135deg, #a07800, #ffc107); color: #1a1a1a; }
.red    { background: linear-gradient(135deg, #8b1a1a, #dc3545); }
</style>
""", unsafe_allow_html=True)

        st.subheader("📊 Predictive KPI Dashboard")

        col1, col2, col3, col4 = st.columns(4)

        color1 = get_color(success_probability, 85, 60)
        col1.markdown(f"""
<div class="card {color1}">
    🚀 {round(success_probability)}% <br>
    Success Probability
</div>
""", unsafe_allow_html=True)

        color2 = "red" if spillover_sp > 5 else "green"
        col2.markdown(f"""
<div class="card {color2}">
    📉 {round(spillover_sp)} SP <br>
    Spillover
</div>
""", unsafe_allow_html=True)

        color3 = "green" if risk_index < 30 else "yellow" if risk_index < 60 else "red"
        col3.markdown(f"""
<div class="card {color3}">
    ⚠️ {round(risk_index)} <br>
    Risk Index
</div>
""", unsafe_allow_html=True)

        color4 = get_color(confidence_score, 75, 50)
        col4.markdown(f"""
<div class="card {color4}">
    🎯 {round(confidence_score)}% <br>
    Confidence Score
</div>
""", unsafe_allow_html=True)

        # --- SPRINT HEALTH INDICATOR ---
        st.subheader("🚦 Sprint Health Indicator")

        if success_probability >= 85:
            indicator_color = "#28a745"
            indicator_gradient = "#1a7a4a"
            indicator_text = "🟢 ON TRACK"
            text_color = "white"
        elif success_probability >= 60:
            indicator_color = "#ffc107"
            indicator_gradient = "#a07800"
            indicator_text = "🟡 AT RISK"
            text_color = "black"
        else:
            indicator_color = "#dc3545"
            indicator_gradient = "#8b1a1a"
            indicator_text = "🔴 HIGH RISK"
            text_color = "white"

        st.markdown(f"""
<div style="
    background: linear-gradient(135deg, {indicator_gradient}, {indicator_color});
    padding: 32px 20px;
    border-radius: 16px;
    text-align: center;
    font-size: 2rem;
    font-weight: 800;
    color: {text_color};
    box-shadow: 0 6px 24px rgba(0,0,0,0.45);
    border: 1px solid rgba(255,255,255,0.1);
    letter-spacing: 1px;">
    {indicator_text} <br>
    <span style="font-size:1.1rem; font-weight:400; opacity:0.85;">{round(success_probability)}% Confidence</span>
</div>
""", unsafe_allow_html=True)

        # --- AI INSIGHTS ---
        st.subheader("🧠 AI Recommendations")
        if st.button("🚀 Generate Advisor Insights", key="generate_advisor_insights"):
            insights = generate_ai_insights(current_sprint_df, full_df=df)
            if insights:
                st.session_state.ai_insights = insights

        if "ai_insights" in st.session_state and st.session_state.ai_insights:
            st.markdown(st.session_state.ai_insights)
        else:
            st.info("💡 Generate insights to see targeted Scrum Master recommendations.")

        # --- WHAT IF SIMULATION ---
        st.subheader("🔮 What-If Analysis")
        extra_sp = st.slider("If additional SP completed:", 0, 30, 5)

        # Current values
        total_sp = metrics["total_sp"]
        completed_sp = metrics["completed_sp"]
        remaining_sp = metrics["remaining_sp"]

        # --- Simulated completion ---
        sim_completed = completed_sp + extra_sp
        sim_remaining = max(0, total_sp - sim_completed)

        # --- Predictability ---
        sim_predictability = (sim_completed / total_sp * 100) if total_sp > 0 else 0

        # --- Spillover ---
        sim_spillover = (sim_remaining / total_sp * 100) if total_sp > 0 else 0

        # --- Velocity impact ---
        velocity_metrics = get_velocity_metrics(df)
        avg_velocity = velocity_metrics["avg_velocity"]

        # How many sprints needed after simulation
        sprints_needed = sim_remaining / avg_velocity if avg_velocity > 0 else 0

        # --- Confidence Score ---
        sim_confidence = (
            0.5 * sim_predictability -
            0.3 * sim_spillover
        )

        # --- UI Output ---
        c1, c2, c3, c4 = st.columns(4)

        c1.metric("📈 Predictability", f"{round(sim_predictability)}%")
        c2.metric("📉 Spillover Risk", f"{round(sim_spillover)}%")
        c3.metric("⚡ Sprints Needed", f"{round(sprints_needed, 1)}")
        c4.metric("🎯 Confidence", f"{round(sim_confidence)}%")

        # --- Insight ---
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
    
    # Tab 4: AI Insights
    with tab4:
        st.markdown("## 🧠 AI Delivery Coach")
        st.markdown("*Powered by Groq — Senior Scrum Master + SAFe RTE perspective*")

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
            # Get current sprint for risk calculation
            current_sprint_df_ai, current_sprint_name_ai = get_current_sprint_df(df)
            ai_metrics = calculate_metrics(current_sprint_df_ai)
            ai_risk = ai_metrics["risk_percentage"]

            # Auto coaching alert banner
            if ai_risk > RISK_HIGH_THRESHOLD:
                st.error(f"🚨 AI Alert: High sprint risk detected — {round(ai_risk)}% risk index. Immediate action required.")
            elif ai_risk > RISK_MODERATE_THRESHOLD:
                st.warning(f"⚠️ AI Alert: Sprint is at risk — {round(ai_risk)}% risk index. Monitor closely.")

            # Quick question suggestion buttons
            st.markdown("### 💡 Quick Questions")
            q_col1, q_col2, q_col3 = st.columns(3)
            quick_question = None
            with q_col1:
                if st.button("Will we meet the sprint goal?", use_container_width=True):
                    quick_question = "Will we meet the sprint goal?"
            with q_col2:
                if st.button("What should I do today?", use_container_width=True):
                    quick_question = "What should I do today as Scrum Master?"
            with q_col3:
                if st.button("Biggest risk right now?", use_container_width=True):
                    quick_question = "What is the biggest risk right now?"

            if quick_question:
                with st.spinner("🤔 Thinking..."):
                    quick_response = chat_with_ai(df, quick_question)
                st.info(f"**{quick_question}**\n\n{quick_response}")

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
    
    # Tab 5: Chat
    with tab5:
        st.subheader("🤖 Ask Delivery Copilot")
        
        if not os.getenv("GROQ_API_KEY"):
            st.info("📝 Please enter your Groq API key in the sidebar (⚙️ Configuration) to use the chat.")
        else:
            st.markdown("""
            **Ask me anything about your sprint!**
            - "How can we improve our velocity?"
            - "What should we do about the blocked items?"
            - "Which sprint is at risk?"
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
                        response = chat_with_ai(df, preset_question)
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
                        response = chat_with_ai(df, user_input)
                        st.markdown(response)
                    
                    # Add assistant response to history
                    st.session_state.chat_history.append({"role": "assistant", "content": response})

    # Tab 6: Delivery Performance Metrics
    with tab6:
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

 
