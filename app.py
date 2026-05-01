from fpdf import FPDF
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import bcrypt
import os
from dotenv import load_dotenv
from database import get_db, init_db
from groq_helper import get_ai_discussion, parse_scores

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_secret_123")

init_db()


# ---------- AUTH ROUTES ----------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"].encode("utf-8")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and bcrypt.checkpw(password, user["password"]):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        college = request.form["college"].strip()
        branch = request.form["branch"].strip()
        password = request.form["password"].encode("utf-8")

        hashed = bcrypt.hashpw(password, bcrypt.gensalt())

        try:
            conn = get_db()
            conn.execute(
                "INSERT INTO users (name, email, college, branch, password) VALUES (?, ?, ?, ?, ?)",
                (name, email, college, branch, hashed)
            )
            conn.commit()
            conn.close()
            flash("Account created! Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash("Email already registered. Please log in.", "error")

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- DASHBOARD ----------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    user_id = session["user_id"]

    total_sessions = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()[0]

    avg_score = conn.execute(
        "SELECT ROUND(AVG(score_overall), 1) FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()[0] or 0

    best_score = conn.execute(
        "SELECT MAX(score_overall) FROM sessions WHERE user_id = ?", (user_id,)
    ).fetchone()[0] or 0

    this_week = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE user_id = ? AND created_at >= datetime('now', '-7 days')", (user_id,)
    ).fetchone()[0]

    recent_sessions = conn.execute(
        "SELECT topic, difficulty, score_overall, created_at FROM sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
        (user_id,)
    ).fetchall()

    chart_data = conn.execute(
        "SELECT score_overall, created_at FROM sessions WHERE user_id = ? ORDER BY created_at ASC LIMIT 10",
        (user_id,)
    ).fetchall()

    conn.close()

    chart_labels = [row["created_at"][:10] for row in chart_data]
    chart_scores = [row["score_overall"] for row in chart_data]

    return render_template("dashboard.html",
        name=session["user_name"],
        total_sessions=total_sessions,
        avg_score=avg_score,
        best_score=best_score,
        this_week=this_week,
        recent_sessions=recent_sessions,
        chart_labels=chart_labels,
        chart_scores=chart_scores
    )

# ---------- PRACTICE ----------

@app.route("/practice")
def practice():
    if "user_id" not in session:
        return redirect(url_for("login"))
    return render_template("practice.html")


@app.route("/submit_response", methods=["POST"])
def submit_response():
    if "user_id" not in session:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json()
    user_response = data.get("user_response", "")
    topic = data.get("topic", "")
    difficulty = data.get("difficulty", "Medium")

    ai_output = get_ai_discussion(user_response, topic, difficulty)
    scores = parse_scores(ai_output)

    # Parse speakers and feedback
    lines = ai_output.split("\n")
    confident, aggressive, logical = "", "", ""
    strengths, weaknesses, suggestions = "", "", ""
    current = ""

    for line in lines:
        l = line.strip()
        if "Confident Speaker:" in l: current = "confident"
        elif "Aggressive Debater:" in l: current = "aggressive"
        elif "Logical Thinker:" in l: current = "logical"
        elif l.startswith("Strengths:"): strengths = l.replace("Strengths:", "").strip()
        elif l.startswith("Weaknesses:"): weaknesses = l.replace("Weaknesses:", "").strip()
        elif l.startswith("Suggestions:"): suggestions = l.replace("Suggestions:", "").strip()
        elif l and current == "confident" and not confident: confident = l
        elif l and current == "aggressive" and not aggressive: aggressive = l
        elif l and current == "logical" and not logical: logical = l

    # Save to database
    conn = get_db()
    conn.execute("""
        INSERT INTO sessions
        (user_id, topic, difficulty, user_response, ai_discussion,
         score_overall, score_clarity, score_logic, score_confidence, score_relevance, feedback)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"], topic, difficulty, user_response, ai_output,
        scores["overall"], scores["clarity"], scores["logic"],
        scores["confidence"], scores["relevance"],
        f"Strengths: {strengths} | Weaknesses: {weaknesses} | Suggestions: {suggestions}"
    ))
    conn.commit()
    conn.close()

    return jsonify({
        "confident": confident,
        "aggressive": aggressive,
        "logical": logical,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
        "scores": scores
    })

# ---------- HISTORY ----------

@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    sessions = conn.execute(
        "SELECT id, topic, difficulty, score_overall, feedback, created_at FROM sessions WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],)
    ).fetchall()
    conn.close()

    return render_template("history.html", sessions=sessions)


# ---------- PROFILE ----------

@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        name = request.form["name"].strip()
        college = request.form["college"].strip()
        branch = request.form["branch"].strip()

        conn.execute(
            "UPDATE users SET name = ?, college = ?, branch = ? WHERE id = ?",
            (name, college, branch, session["user_id"])
        )
        conn.commit()
        session["user_name"] = name
        flash("Profile updated!", "success")
        return redirect(url_for("profile"))

    conn.close()
    return render_template("profile.html",
        name=user["name"],
        email=user["email"],
        college=user["college"],
        branch=user["branch"]
    )

# ---------- PDF DOWNLOAD ----------

@app.route("/download_pdf/<int:session_id>")
def download_pdf(session_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()
    s = conn.execute(
        "SELECT * FROM sessions WHERE id = ? AND user_id = ?",
        (session_id, session["user_id"])
    ).fetchone()
    user = conn.execute(
        "SELECT * FROM users WHERE id = ?", (session["user_id"],)
    ).fetchone()
    conn.close()

    if not s:
        return "Session not found", 404

    pdf = FPDF()
    pdf.add_page()

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(83, 74, 183)
    pdf.cell(0, 12, "GD Simulator", ln=True, align="C")

    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "Session Feedback Report", ln=True, align="C")
    pdf.ln(5)

    # Divider
    pdf.set_draw_color(83, 74, 183)
    pdf.set_line_width(0.5)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)

    # User info
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, f"Name: {user['name']}", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 7, f"College: {user['college']} | Branch: {user['branch']}", ln=True)
    pdf.cell(0, 7, f"Date: {s['created_at']}", ln=True)
    pdf.ln(5)

    # Session info
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, f"Topic: {s['topic']}", ln=True)
    pdf.cell(0, 8, f"Difficulty: {s['difficulty']}", ln=True)
    pdf.ln(5)

    # Scores
    pdf.set_draw_color(200, 200, 200)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(83, 74, 183)
    pdf.cell(0, 8, "Your Scores", ln=True)
    pdf.ln(3)

    scores = [
        ("Clarity", s['score_clarity']),
        ("Logic", s['score_logic']),
        ("Confidence", s['score_confidence']),
        ("Relevance", s['score_relevance']),
        ("Overall", s['score_overall']),
    ]

    for label, score in scores:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(60, 8, f"{label}:", ln=False)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"{score} / 10", ln=True)

    pdf.ln(5)

    # Feedback
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(83, 74, 183)
    pdf.cell(0, 8, "Feedback", ln=True)
    pdf.ln(3)

    feedback = s['feedback'] or ""
    for part in feedback.split("|"):
        part = part.strip()
        if part:
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(30, 30, 30)
            if ":" in part:
                label, content = part.split(":", 1)
                pdf.cell(0, 7, f"{label.strip()}:", ln=True)
                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 7, content.strip())
            pdf.ln(2)

    # Your response
    pdf.ln(3)
    pdf.set_line_width(0.3)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(83, 74, 183)
    pdf.cell(0, 8, "Your Response", ln=True)
    pdf.ln(3)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(80, 80, 80)
    pdf.multi_cell(0, 7, s['user_response'] or "")

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 8, "Generated by GD Simulator — Practice for your campus placements", align="C")

    from flask import make_response
    response = make_response(pdf.output())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=GD_Report_{session_id}.pdf"
    return response

if __name__ == "__main__":
    app.run(debug=True)