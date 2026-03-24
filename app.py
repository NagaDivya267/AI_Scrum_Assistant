import streamlit as st
import pandas as pd
import csv
import os
import re
import datetime
from groq import Groq

# Page config
st.set_page_config(page_title="AI Scrum Assistant", layout="wide", initial_sidebar_state="expanded")

# Define the CSV file path
csv_file = "sprint_data.csv"

# Sidebar - API Key Setup
st.sidebar.markdown("### ⚙️ Configuration")

# Sidebar - Data Source
st.sidebar.markdown("### 📁 Sprint Data")
uploaded_file = st.sidebar.file_uploader("Upload Sprint CSV", type=["csv"])

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

def generate_ai_insights(df, project_context="agile software delivery"):
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
        # Blocked % = blocked SP / committed SP
        blocker_pct = (metrics['blocked_sp'] / total_sp * 100) if total_sp > 0 else 0
        risk_pct = metrics['risk_percentage']
        
        # Velocity gap based on avg velocity from last 3 completed sprints vs required remaining work
        velocity_metrics = get_velocity_metrics(df)
        avg_velocity = velocity_metrics['avg_velocity']
        velocity_gap_pct = (metrics['remaining_sp'] - avg_velocity) / total_sp * 100 if total_sp > 0 else 0
        
        prompt = f"""You are an experienced Scrum Master coach working in {project_context} projects.

Analyze the sprint health based on:

- Remaining Work: {remaining_pct:.0f}%
- Blockers: {blocker_pct:.0f}%
- Not Started Work: {not_started_pct:.0f}%
- Velocity Gap: {velocity_gap_pct:.0f}%
- Overall Risk: {risk_pct:.0f}%
- Blocked Items: {metrics['blocked_count']}
- In Progress: {metrics['in_progress_sp']} pts
- Current Completion: {metrics['completion_rate']:.0f}%

Provide response in this format:

1. Sprint Health Summary (1-2 lines)

2. Key Risks (bullet points)
   - Be specific (e.g., too many stories not started, high blocker rate)

3. Root Cause Analysis
   - Why this is happening

4. Recommended Actions (very practical)
   - What Scrum Master should do tomorrow

Keep it concise and actionable."""
        
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
        
        prompt = f"""You are an expert Scrum Master with 10+ years of experience helping agile teams deliver successfully.

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
        df = pd.read_csv(uploaded_file)
        st.sidebar.success("✅ Using uploaded sprint data")
    except Exception as e:
        st.sidebar.error(f"❌ Upload error: {e}")

if df is None:
    df = read_from_csv()
    if df is not None:
        st.sidebar.info("ℹ️ Using default sprint_data.csv")

if df is not None:
    # Create tabs with new AI Insights tab and Chat tab
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 All Data", "📈 Sprint Summary", "🎯 Metrics", "🧠 AI Insights", "💬 Chat"])
    
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

        # --- RISK STATUS ---
        st.subheader("📍 Current Sprint Risk Status")
        status = get_risk_status(metrics["risk"])

        if "High Risk" in status:
            st.error(status)
        elif "Medium Risk" in status:
            st.warning(status)
        else:
            st.success(status)

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
    padding: 20px;
    border-radius: 12px;
    color: white;
    text-align: center;
    font-size: 20px;
    font-weight: bold;
}
.green { background-color: #28a745; }
.yellow { background-color: #ffc107; color: black; }
.red { background-color: #dc3545; }
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
            indicator_text = "🟢 ON TRACK"
            text_color = "white"
        elif success_probability >= 60:
            indicator_color = "#ffc107"
            indicator_text = "🟡 AT RISK"
            text_color = "black"
        else:
            indicator_color = "#dc3545"
            indicator_text = "🔴 HIGH RISK"
            text_color = "white"

        st.markdown(f"""
<div style="
    background-color:{indicator_color};
    padding:30px;
    border-radius:15px;
    text-align:center;
    font-size:28px;
    font-weight:bold;
    color:{text_color};">
    {indicator_text} <br>
    {round(success_probability)}% Confidence
</div>
""", unsafe_allow_html=True)

        # --- AI INSIGHTS ---
        st.subheader("🧠 AI Recommendations")
        if st.button("🚀 Generate Advisor Insights", key="generate_advisor_insights"):
            insights = generate_ai_insights(current_sprint_df)
            if insights:
                st.session_state.ai_insights = insights

        if "ai_insights" in st.session_state and st.session_state.ai_insights:
            st.markdown(st.session_state.ai_insights)
        else:
            st.info("💡 Generate insights to see targeted Scrum Master recommendations.")

        # --- WHAT IF SIMULATION ---
        st.subheader("🔮 What-If Analysis")
        extra_sp = st.slider("If additional SP completed today:", 0, 20, 5, key="what_if_sp")

        simulated_remaining = max(0, metrics["remaining_sp"] - extra_sp)
        simulated_risk = (simulated_remaining / metrics["total_sp"] * 100) if metrics["total_sp"] > 0 else 0

        st.info(f"👉 New Risk: {round(simulated_risk)}%")
    
    # Tab 4: AI Insights
    with tab4:
        st.subheader("🧠 AI-Powered Sprint Analysis (Powered by Groq)")
        
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
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col2:
                if st.button("🚀 Generate AI Insights", use_container_width=True):
                    insights = generate_ai_insights(df)
                    
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
                st.info("💡 Click 'Generate AI Insights' to get AI-powered analysis of your sprint health, risks, and recommendations.")
    
    # Tab 5: Chat
    with tab5:
        st.subheader("💬 Chat with Sprint Assistant")
        
        if not os.getenv("GROQ_API_KEY"):
            st.info("📝 Please enter your Groq API key in the sidebar (⚙️ Configuration) to use the chat.")
        else:
            st.markdown("""
            **Ask me anything about your sprint!**
            - "How can we improve our velocity?"
            - "What should we do about the blocked items?"
            - "Which sprint is at risk?"
            """)
            
            # Example questions for Scrum Masters
            st.markdown("**💡 Try asking:**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write("- Will we meet sprint goal?")
            with col2:
                st.write("- What are the key risks?")
            with col3:
                st.write("- What should I do as Scrum Master?")
            
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
    
    st.markdown("---")
    st.markdown("*Last updated: Real-time from sprint_data.csv*")
