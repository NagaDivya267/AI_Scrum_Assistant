# 🚀 AI SCRUM ASSISTANT - Deployment Guide

## Deploy on Streamlit Cloud (FREE, takes 5 minutes)

### Step 1: Ensure Everything is Committed to GitHub

```bash
cd c:\Users\home\AI_Scrum_Assistant
git add -A
git commit -m "Ready for deployment - add requirements and config files"
git push origin main
```

### Step 2: Go to Streamlit Cloud

1. Visit: **https://streamlit.io/cloud**
2. Click **"Sign up"** (use your GitHub account or email)
3. Click **"Deploy an app"**

### Step 3: Configure Deployment

1. **Repository:** Select `NagaDivya267/AI-Scrum-Master-dynamic`
2. **Branch:** `main`
3. **Main file path:** `app.py`
4. Click **"Deploy"**

Wait 2-3 minutes for deployment...

### Step 4: Add Your Groq API Key (Important!)

Once deployed:
1. Click the **⚙️ Settings** button (top right)
2. Click **"Secrets"** on the left sidebar
3. Paste your API key in the text area:

```
GROQ_API_KEY = "gsk_paste_your_key_here"
```

4. Click **"Save"** at the bottom

Your app will automatically restart with the API key!

### Step 5: Share Your Public URL

Your app will be available at:
```
https://ai-scrum-master-dynamic.streamlit.app
```

Share this link with anyone - they can access it immediately! 🎉

---

## 🔐 Getting Your Free Groq API Key

1. Go to: **https://console.groq.com/keys**
2. Click **"Sign up"** (email or GitHub)
3. Verify your email
4. Click **"Create API Key"**
5. Copy the key (starts with `gsk_`)

---

## ⚡ Alternative: Hugging Face Spaces (Also FREE)

If Streamlit Cloud is slow:

1. Go to: **https://huggingface.co/spaces**
2. Click **"Create new Space"**
3. Choose **"Streamlit"** as the space SDK
4. Push your repo there instead
5. Add your API key to Secrets in the Space settings

---

## 📊 Accessing Your Deployed App

Once deployed, open your public URL and:
1. Enter your Groq API key in the sidebar ⚙️
2. Go through the 5 tabs:
   - 📊 **All Data** - View sprint data table
   - 📈 **Sprint Summary** - See sprint completion %
   - 🎯 **Metrics** - Current & Predictive Analytics
   - 🧠 **AI Insights** - Generate AI analysis
   - 💬 **Chat** - Ask questions about your sprint

---

## ✅ Your App is Production-Ready!

✅ Real-time sprint data tracking
✅ Velocity-based predictions
✅ AI-powered insights (Groq)
✅ Interactive chat with sprint data
✅ Beautiful dashboard with 5 tabs
✅ Fully responsive design
✅ No payment required (FREE forever with Groq)

---

## 🆘 Troubleshooting

**Issue: "App not deployed yet"**
- Wait 3-5 minutes, can take longer on first deploy

**Issue: "API key not working"**
- Make sure you added it in Settings > Secrets (not sidebar)
- Try refreshing the page after adding the secret

**Issue: "Redeployed but changes not showing"**
- Streamlit Cloud auto-redeploys on push
- Hard refresh browser (Ctrl+Shift+R)

**Issue: "Want custom domain?"**
- Contact Streamlit support for premium features

