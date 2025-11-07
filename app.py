
import streamlit as st
import pandas as pd
import google.generativeai as genai
from io import BytesIO
import json, os, re
from dotenv import load_dotenv
import altair as alt

# ============ CONFIGURATION ============
load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

FILE_PATH = "transactions.xlsx"

# ============ DATA HANDLING ============
if os.path.exists(FILE_PATH):
    df = pd.read_excel(FILE_PATH)
else:
    df = pd.DataFrame(columns=["Type", "Category", "Amount", "Balance", "Description"])

balance = df["Balance"].iloc[-1] if not df.empty else 0.0

# ============ STREAMLIT CONFIG ============
st.set_page_config(page_title="💸 AI Expense Tracker", page_icon="💬", layout="wide")
st.title("💬 AI Expense Tracker")
st.caption("Manage your income and expenses through conversation — powered by **Gemini AI**.")

# ============ SESSION STATE ============
if "messages" not in st.session_state:
    st.session_state.messages = []

# ============ SIDEBAR PLACEHOLDERS ============
balance_placeholder = st.sidebar.empty()
income_placeholder = st.sidebar.empty()
expense_placeholder = st.sidebar.empty()
st.sidebar.divider()
st.sidebar.write("PUKULO SOLUTIONS")

def update_sidebar(df, balance):
    total_income = df[df["Type"] == "income"]["Amount"].sum()
    total_expense = df[df["Type"] == "expense"]["Amount"].sum()
    balance_placeholder.metric("💰 Current Balance", f"${balance:.2f}")
    income_placeholder.metric("📈 Total Income", f"${total_income:.2f}")
    expense_placeholder.metric("📉 Total Expenses", f"${total_expense:.2f}")

update_sidebar(df, balance)

# ============ UTILITY: EXTRACT JSON ============
def extract_first_json(text):
    """
    Safely extract the first JSON object from AI response, even if
    extra text or multiple objects exist.
    """
    stack = []
    start_idx = None
    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                start_idx = i
            stack.append('{')
        elif char == '}':
            if stack:
                stack.pop()
                if not stack and start_idx is not None:
                    try:
                        return json.loads(text[start_idx:i+1])
                    except json.JSONDecodeError:
                        return None
    return None

# ============ CHAT HISTORY ============
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_input = st.chat_input("💬 Type something like 'I bought snacks for $80'")

if user_input:
    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Analyzing your transaction..."):
        prompt = f"""
        You are an AI financial tracker.
        User message: "{user_input}"
        Extract details and respond with valid JSON only:

        {{
            "data": {{
                "type": "income" or "expense",
                "amount": number,
                "category": short one-word category,
                "description": short summary
            }},
            "reply": "a friendly confirmation message for the user"
        }}
        """

        try:
            response = model.generate_content(prompt)
            data = extract_first_json(response.text)
            if data is None:
                raise ValueError("Could not extract valid JSON from AI response")

            info = data.get("data", {})
            reply = data.get("reply", "Transaction recorded!")

            # ======= PARSE TRANSACTION SAFELY =======
            t_type = (info.get("type") or "").lower().strip()
            amount_raw = info.get("amount", None)
            category = info.get("category", "other").strip()
            desc = info.get("description", "").strip()

            # Convert amount
            try:
                amount = float(amount_raw)
            except (ValueError, TypeError):
                amount = None

            # Fallback: extract first number from user input
            if amount is None:
                numbers = re.findall(r"\d+\.?\d*", user_input.replace(",", ""))
                if numbers:
                    amount = float(numbers[0])

            # 🚨 If invalid or missing amount/type, show popup
            if t_type not in ["income", "expense"] or amount is None or amount <= 0:
                st.toast("⚠️ Please include a valid amount (e.g. '$200' or 'for 300').", icon="⚠️")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": "⚠️ Please include a valid amount (e.g. '$200' or 'for 300')."
                })
                st.stop()

            # ======= UPDATE BALANCE =======
            if t_type == "income":
                balance += amount
            else:
                balance -= amount

            # Append transaction
            new_row = pd.DataFrame([{
                "Type": t_type,
                "Category": category,
                "Amount": amount,
                "Balance": balance,
                "Description": desc
            }])
            df = pd.concat([df, new_row], ignore_index=True)
            df.to_excel(FILE_PATH, index=False)

            # Display AI reply
            ai_message = f"✅ {reply}\n\n**New Balance:** ${balance:.2f}"
            st.chat_message("assistant").markdown(ai_message)
            st.session_state.messages.append({"role": "assistant", "content": ai_message})

            update_sidebar(df, balance)

        except Exception as e:
            st.toast("❌ Oops! Something went wrong while processing your message.", icon="❌")


# ============ TRANSACTION HISTORY ============
st.subheader("🧾 Transaction History")
st.dataframe(df, use_container_width=True)

# ============ CHARTS SECTION ============
if not df.empty:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("💸 Expenses by Category")
        exp_df = df[df["Type"] == "expense"]
        if not exp_df.empty:
            pie = alt.Chart(exp_df).mark_arc(innerRadius=50).encode(
                theta="Amount:Q",
                color="Category:N",
                tooltip=["Category", "Amount"]
            ).properties(width=350, height=350)
            st.altair_chart(pie, use_container_width=True)
        else:
            st.info("No expenses yet!")

    with col2:
        st.subheader("📈 Balance Over Time")
        line = alt.Chart(df.reset_index()).mark_line(point=True).encode(
            x=alt.X("index", title="Transaction #"),
            y=alt.Y("Balance", title="Balance ($)"),
            color=alt.Color("Type", legend=alt.Legend(title="Type")),
            tooltip=["Type", "Amount", "Balance"]
        ).properties(width=350, height=350)
        st.altair_chart(line, use_container_width=True)

# ============ DOWNLOAD EXCEL ============
def convert_df_to_excel(df):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Transactions")
    buffer.seek(0)
    return buffer

st.download_button(
    label="⬇️ Download Excel Report",
    data=convert_df_to_excel(df),
    file_name="transactions.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
