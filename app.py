import streamlit as st
import pandas as pd
import csv
import os
from groq import Groq

# Page config
st.set_page_config(page_title="AI Scrum Assistant", layout="wide", initial_sidebar_state="expanded")

# Define the CSV file path
csv_file = "sprint_data.csv"

# Sidebar - API Key Setup
st.sidebar.markdown("### ⚙️ Configuration")

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
    blocked_count = len(df[df['Blocked'] == 'Yes'])
    
    completion_rate = (total_completed / total_story_points * 100) if total_story_points > 0 else 0
    risk_percentage = ((total_in_progress + total_todo) / total_story_points * 100) if total_story_points > 0 else 0
    
    return {
        "total_sp": total_story_points,
        "completed_sp": total_completed,
        "remaining_sp": total_todo + total_in_progress,
        "in_progress_sp": total_in_progress,
        "todo_sp": total_todo,
        "blocked_count": blocked_count,
        "completion_rate": completion_rate,
        "risk_percentage": risk_percentage
    }

def get_velocity_metrics(df):
    """Calculate velocity-based metrics across sprints"""
    sprints_summary = get_sprint_summary(df)
    
    # Calculate velocity (completed story points) per sprint
    sprint_velocities = []
    for sprint_name, stats in sorted(sprints_summary.items()):
        sprint_velocities.append(stats['Done'])
    
    if len(sprint_velocities) > 0:
        avg_velocity = sum(sprint_velocities) / len(sprint_velocities)
    else:
        avg_velocity = 0
    
    return {
        "avg_velocity": avg_velocity,
        "velocities": sprint_velocities,
        "velocity_trend": "Stable" if len(sprint_velocities) <= 1 else ("📈 Improving" if sprint_velocities[-1] > avg_velocity else "📉 Declining" if sprint_velocities[-1] < avg_velocity else "➡️ Stable")
    }

def get_traffic_light(confidence):
    """Return traffic light emoji and status based on confidence percentage"""
    if confidence >= 85:
        return "🟢", "On Track"
    elif confidence >= 60:
        return "🟡", "At Risk"
    else:
        return "🔴", "High Risk"

def calculate_sprint_confidence(df):
    """Calculate confidence in sprint goal completion based on velocity and current progress"""
    metrics = calculate_metrics(df)
    velocity_metrics = get_velocity_metrics(df)
    
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
    - Completion Rate: {metrics['completion_rate']:.1f}%
    - Risk Percentage: {metrics['risk_percentage']:.1f}%
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
        blocker_pct = (metrics['blocked_count'] / len(df) * 100) if len(df) > 0 else 0
        risk_pct = metrics['risk_percentage']
        
        # Calculate velocity gap (difference between expected and actual)
        velocity_metrics = get_velocity_metrics(df)
        avg_velocity = velocity_metrics['avg_velocity']
        velocity_gap_pct = ((total_sp - metrics['completed_sp']) - avg_velocity) / total_sp * 100 if total_sp > 0 else 0
        
        prompt = f"""You are an experienced Scrum Master coach working in {project_context} projects.

Analyze the sprint health based on:

- Remaining Work: {remaining_pct:.1f}%
- Blockers: {blocker_pct:.1f}%
- Not Started Work: {not_started_pct:.1f}%
- Velocity Gap: {velocity_gap_pct:.1f}%
- Overall Risk: {risk_pct:.1f}%
- Blocked Items: {metrics['blocked_count']}
- In Progress: {metrics['in_progress_sp']} pts
- Current Completion: {metrics['completion_rate']:.1f}%

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
                    model="llama-3.1-70b-versatile",  # Fast, stable, and supported
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

# Read data
df = read_from_csv()

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
        # Create subtabs for Current vs Predictive Metrics
        metrics_tab1, metrics_tab2 = st.tabs(["📊 Current Metrics", "🔮 Predictive Analytics"])
        
        with metrics_tab1:
            st.subheader("Current Sprint Metrics")
            
            # Calculate overall metrics
            sprints_summary = get_sprint_summary(df)
            total_story_points = sum(s["Total"] for s in sprints_summary.values())
            total_completed = sum(s["Done"] for s in sprints_summary.values())
            total_in_progress = sum(s["In Progress"] for s in sprints_summary.values())
            total_todo = sum(s["To Do"] for s in sprints_summary.values())
            
            m1, m2, m3, m4 = st.columns(4)
            with m1:
                st.metric("Total Story Points", total_story_points)
            with m2:
                st.metric("Completed", f"{total_completed}/{total_story_points}")
            with m3:
                st.metric("In Progress", total_in_progress)
            with m4:
                st.metric("To Do", total_todo)
            
            # Completion rate
            overall_completion = (total_completed / total_story_points * 100) if total_story_points > 0 else 0
            st.metric("Overall Completion Rate", f"{overall_completion:.1f}%")
            
            # Status distribution
            st.subheader("Status Distribution")
            status_count = df['Status'].value_counts()
            st.bar_chart(status_count)
            
            # Blocked items
            st.subheader("Blocked Items")
            blocked_df = df[df['Blocked'] == 'Yes']
            if len(blocked_df) > 0:
                st.warning(f"⚠️ {len(blocked_df)} items are blocked")
                st.dataframe(blocked_df[['Sprint', 'Story', 'Status', 'StoryPoints']], width='stretch')
            else:
                st.success("✅ No blocked items")
        
        with metrics_tab2:
            st.subheader("🔮 Predictive Metrics & Sprint Goal Confidence")
            
            # Get prediction metrics
            confidence_metrics = calculate_sprint_confidence(df)
            velocity_metrics = get_velocity_metrics(df)
            metrics = calculate_metrics(df)
            
            # Current completion and prediction row
            pred_col1, pred_col2, pred_col3 = st.columns(3)
            
            with pred_col1:
                current = confidence_metrics['current_completion']
                st.metric(
                    "📊 Current Completion",
                    f"{round(current, 2)}%"
                )
            
            with pred_col2:
                predicted = confidence_metrics['predicted_completion']
                delta_val = round(predicted - current, 2)
                st.metric(
                    "🚀 Predicted Completion",
                    f"{round(predicted, 2)}%",
                    delta=f"{delta_val}% trend"
                )
            
            with pred_col3:
                icon, status = get_traffic_light(confidence_metrics['confidence'])
                st.metric(
                    f"{icon} Goal Status",
                    status,
                    delta=f"{round(confidence_metrics['confidence'], 2)}% confidence"
                )
            
            # Velocity Analysis Section
            st.markdown("---")
            st.subheader("⚡ Velocity Analysis")
            
            vel_col1, vel_col2, vel_col3 = st.columns(3)
            
            with vel_col1:
                st.metric(
                    "📈 Avg Velocity (Past Sprints)",
                    f"{round(velocity_metrics['avg_velocity'], 2)} pts"
                )
            
            with vel_col2:
                st.metric(
                    "🎯 Velocity-Based Forecast",
                    f"{round(velocity_metrics['avg_velocity'] * 1.1, 2)} pts",  # 1.1x for optimistic forecast
                    delta="Next sprint estimate"
                )
            
            with vel_col3:
                st.metric(
                    "📊 Velocity Trend",
                    velocity_metrics['velocity_trend']
                )
            
            # Sprint Goal Confidence Section
            st.markdown("---")
            st.subheader("🎯 Sprint Goal Confidence")
            
            confidence_val = confidence_metrics['confidence']
            icon, status_text = get_traffic_light(confidence_val)
            
            # Display traffic light status prominently
            st.info(f"### {icon} {status_text} - {round(confidence_val, 2)}% Confidence")
            
            # Key metrics affecting confidence
            st.markdown("---")
            st.subheader("📊 Key Factors Affecting Delivery")
            
            factors_col1, factors_col2, factors_col3, factors_col4 = st.columns(4)
            
            with factors_col1:
                st.metric("Blocked Items", f"{metrics['blocked_count']}")
                
            with factors_col2:
                st.metric("In Progress", f"{metrics['in_progress_sp']} pts")
                
            with factors_col3:
                st.metric("To Do", f"{metrics['todo_sp']} pts")
                
            with factors_col4:
                st.metric("Risk ⚠️", f"{round(metrics['risk_percentage'], 1)}%")
    
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
            col1, col2 = st.columns([3, 1])
            
            with col2:
                if st.button("🚀 Generate AI Insights", use_container_width=True):
                    insights = generate_ai_insights(df)
                    
                    if insights:
                        st.session_state.ai_insights = insights
            
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
            - "Why are we blocked on the Encryption Module?"
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
