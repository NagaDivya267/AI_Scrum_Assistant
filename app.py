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
api_key = st.sidebar.text_input(
    "Groq API Key", 
    value=os.getenv("GROQ_API_KEY", ""),
    type="password",
    help="Get your FREE API key from https://console.groq.com/keys"
)

# Store API key in session
if api_key:
    os.environ["GROQ_API_KEY"] = api_key
    st.sidebar.success("✅ Groq API Key loaded")
else:
    st.sidebar.warning("⚠️ Enter Groq API Key for AI insights (FREE at https://console.groq.com)")

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

def generate_ai_insights(df):
    """Generate AI-powered insights using Groq"""
    if not os.getenv("GROQ_API_KEY"):
        return None
    
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        summary = prepare_llm_summary(df)
        
        prompt = f"""You are an expert Scrum Master and agile coach with 10+ years of experience.

Analyze the following sprint data and provide:
1. **Sprint Health Assessment** - Overall status and trajectory
2. **Key Risks** - Top 3 risks that could impact delivery
3. **Root Cause Analysis** - Why are these risks occurring?
4. **Predictive Insights** - What's likely to happen if current trends continue?
5. **Actionable Recommendations** - 3-5 specific actions to improve sprint health

Be concise, data-driven, and focus on what matters most.

{summary}"""
        
        with st.spinner("🧠 AI is analyzing your sprint data..."):
            try:
                response = client.chat.completions.create(
                    model="llama-3.1-70b-versatile",  # Fast, stable, and supported
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1500
                )
            except Exception as e:
                # Fallback to another model if primary fails
                st.warning(f"⚠️ Primary model busy, trying backup model...")
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.7,
                    max_tokens=1500
                )
        
        return response.choices[0].message.content
    
    except Exception as e:
        st.error(f"❌ Error calling Groq API: {str(e)}")
        return None

def chat_with_ai(df, user_question):
    """Chat with AI about sprint data and provide suggestions"""
    if not os.getenv("GROQ_API_KEY"):
        return None
    
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        
        summary = prepare_llm_summary(df)
        
        prompt = f"""You are an expert Scrum Master helping teams solve problems and improve their sprints.

SPRINT DATA CONTEXT:
{summary}

USER QUESTION: {user_question}

Provide:
1. **Direct Answer** - Address their question specifically
2. **Problem Analysis** - What might be causing this issue
3. **Team Suggestions** - 2-3 concrete actions the team can take now
4. **Prevention Tips** - How to avoid this problem in future sprints

Be concise, practical, and actionable. Focus on what helps the team most."""
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",  # Fast, stable, and actively supported
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000
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
        st.subheader("Key Metrics")
        
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
