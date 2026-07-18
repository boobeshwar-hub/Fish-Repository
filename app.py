import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Configuration
app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # change to a secure random value in production

# Make session cookies persistent when "remember me" is used
app.permanent_session_lifetime = timedelta(days=30)

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# MySQL connection helper
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="boobesh2007@server",
        database="FishRepository"
    )

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------- ROUTES ---------------- #

@app.route("/")
@app.route("/home")
def home():
    return render_template("home.html")


# ---------------- Authentication ---------------- #
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        role = request.form.get("role", "researcher")
        institution = request.form.get("institution", "")
        interests = request.form.get("interests", "")
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm-password", "")
        terms = request.form.get("terms")

        if not terms:
            flash("You must agree to the Terms of Service and Privacy Policy.", "error")
            return redirect(url_for("register"))

        if not fullname or not email or not password:
            flash("Please fill required fields.", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match!", "error")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            query = """
                INSERT INTO users (fullname, role, institution, interests, email, password_hash, terms_agreed, account_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
            """
            values = (fullname, role, institution, interests, email, password_hash, 1)
            cursor.execute(query, values)
            conn.commit()
            cursor.close()
            conn.close()
            flash("Account created successfully! Please sign in.", "success")
            return redirect(url_for("signin"))
        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")
            return redirect(url_for("register"))

    return render_template("register.html")


@app.route("/signin", methods=["GET", "POST"])
def signin():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember")  # checkbox value: 'on' if checked

        # Admin shortcut (example)
        if email == "admin@gmail.com" and password == "admin001":
            session.permanent = bool(remember)
            session["user_id"] = "admin"
            session["fullname"] = "Administrator"
            session["role"] = "admin"
            flash("Signed in as admin.", "success")
            return redirect(url_for("management"))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id, fullname, role, password_hash, account_status FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if not user:
                flash("No account found with that email.", "error")
                return redirect(url_for("signin"))

            if user["account_status"] == 0:
                flash("Your account has been deactivated.", "error")
                return redirect(url_for("signin"))

            if check_password_hash(user["password_hash"], password):
                # Set session permanence based on "remember me"
                session.permanent = bool(remember)
                session["user_id"] = user["id"]
                session["fullname"] = user["fullname"]
                session["role"] = user["role"]
                flash(f"Welcome back, {user['fullname']}!", "success")
                return redirect(url_for("dashboard"))
            else:
                flash("Incorrect password.", "error")
                return redirect(url_for("signin"))

        except mysql.connector.Error as err:
            flash(f"Database error: {err}", "error")
            return redirect(url_for("signin"))

    return render_template("sign_in.html")


@app.route("/logout")
def logout():
    # Clear session and explicitly expire the session cookie
    session.clear()
    response = make_response(redirect(url_for("signin")))
    # Flask's session cookie name is app.session_cookie_name (default 'session')
    response.set_cookie(app.session_cookie_name, "", expires=0)
    flash("You have been logged out.", "info")
    return response


# ---------------- Dashboard ---------------- #
@app.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Counts
    cursor.execute("SELECT COUNT(*) AS total_species FROM species_gallery")
    total_species = cursor.fetchone()["total_species"] or 0

    cursor.execute("SELECT COUNT(*) AS total_submissions FROM species_submissions")
    total_submissions = cursor.fetchone()["total_submissions"] or 0

    cursor.execute("SELECT COUNT(*) AS pending FROM species_submissions WHERE status='pending'")
    pending = cursor.fetchone()["pending"] or 0

    contributions = 0
    if "user_id" in session and session["user_id"] != "admin":
        cursor.execute("SELECT COUNT(*) AS contributions FROM species_submissions WHERE submitted_by=%s", (session["user_id"],))
        row = cursor.fetchone()
        contributions = row["contributions"] if row else 0

    # Recent additions (last 5 submissions)
    cursor.execute("SELECT id, scientific_name, common_name, environment_type, submitted_by, created_at, status FROM species_submissions ORDER BY created_at DESC LIMIT 5")
    recent_additions = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        total_species=total_species,
        total_submissions=total_submissions,
        pending=pending,
        user_contributions=contributions,
        recent_additions=recent_additions,
        fullname=session.get("fullname", "Researcher")
    )


# ---------------- Management ---------------- #
@app.route("/management")
def management():
    # Only admin allowed (simple check)
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("signin"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM species_submissions WHERE status='pending' ORDER BY created_at DESC")
    pending_observations = cursor.fetchall()

    cursor.execute("SELECT * FROM species_gallery ORDER BY created_at DESC LIMIT 5")
    recent_verified = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("management.html", pending_observations=pending_observations, recent_verified=recent_verified)


# ---------------- Gallery ---------------- #
def get_species():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM species_gallery ORDER BY id ASC")
    species = cursor.fetchall()
    cursor.close()
    conn.close()
    return species

@app.route("/gallery")
def gallery():
    species = get_species()
    return render_template("gallery.html", species=species)


# ---------------- Admin Upload to Gallery ---------------- #
@app.route("/upload_gallery", methods=["POST"])
def upload_gallery():
    # Only admin allowed
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("signin"))

    try:
        species_name = request.form.get("species_name", "").strip()
        scientific_name = request.form.get("scientific_name", "").strip()
        category = request.form.get("category", "").strip()
        caption = request.form.get("caption", "").strip()
        file = request.files.get("gallery_image")

        if not species_name or not scientific_name or not category:
            flash("Please provide species name, scientific name and category.", "error")
            return redirect(url_for("management"))

        if not file or file.filename == "":
            flash("No file selected.", "error")
            return redirect(url_for("management"))

        if not allowed_file(file.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("management"))

        filename = secure_filename(f"{int(datetime.utcnow().timestamp())}_{file.filename}")
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO species_gallery (species_name, scientific_name, category, image_url, created_at)
            VALUES (%s, %s, %s, %s, %s)
        """
        cursor.execute(query, (species_name, scientific_name, category, filepath, datetime.utcnow()))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Image uploaded successfully!", "success")
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")

    return redirect(url_for("management"))


# ---------------- Researcher: Submit Species ---------------- #
@app.route("/newspecies")
def newspecies():
    if "user_id" not in session:
        flash("Please sign in to submit species.", "error")
        return redirect(url_for("signin"))
    return render_template("speciesform.html")


@app.route("/submit_species", methods=["POST"])
def submit_species():
    if "user_id" not in session:
        flash("Please sign in to submit species.", "error")
        return redirect(url_for("signin"))

    try:
        scientific_name = request.form.get("scientific_name", "").strip()
        common_name = request.form.get("common_name", "").strip()
        family = request.form.get("family", "").strip()
        conservation_status = request.form.get("conservation_status", "").strip()
        environment_type = request.form.get("environment_type", "").strip()
        location = request.form.get("location", "").strip()
        depth_min = request.form.get("depth_min") or None
        depth_max = request.form.get("depth_max") or None
        description = request.form.get("description", "").strip()
        file = request.files.get("species_image")

        if not scientific_name or not common_name or not file:
            flash("Please provide required fields and an image.", "error")
            return redirect(url_for("newspecies"))

        if not allowed_file(file.filename):
            flash("Unsupported file type.", "error")
            return redirect(url_for("newspecies"))

        filename = secure_filename(f"{int(datetime.utcnow().timestamp())}_{file.filename}")
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)

        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO species_submissions
            (scientific_name, common_name, family, conservation_status, environment_type, location, depth_min, depth_max, description, image_url, status, submitted_by, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s)
        """
        values = (
            scientific_name, common_name, family, conservation_status, environment_type,
            location, depth_min, depth_max, description, filepath, session.get("user_id"), datetime.utcnow()
        )
        cursor.execute(query, values)
        conn.commit()
        cursor.close()
        conn.close()

        flash("Species submitted for verification!", "success")
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")

    return redirect(url_for("dashboard"))


# ---------------- Approve / Reject ---------------- #
@app.route("/approve_species/<int:species_id>", methods=["POST"])
def approve_species(species_id):
    # Only admin allowed
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("signin"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM species_submissions WHERE id=%s", (species_id,))
        species = cursor.fetchone()

        if species:
            # Insert into gallery
            insert_query = """
                INSERT INTO species_gallery (species_name, scientific_name, category, image_url, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """
            category = species.get("environment_type") or "Unknown"
            cursor2 = conn.cursor()
            cursor2.execute(insert_query, (
                species.get("common_name"),
                species.get("scientific_name"),
                category.capitalize(),
                species.get("image_url"),
                datetime.utcnow()
            ))

            # Update submission status
            cursor.execute("UPDATE species_submissions SET status='approved' WHERE id=%s", (species_id,))
            conn.commit()
            cursor2.close()
            flash("Species approved and added to gallery!", "success")
        else:
            flash("Species not found.", "error")

        cursor.close()
        conn.close()
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")

    return redirect(url_for("management"))


@app.route("/reject_species/<int:species_id>", methods=["POST"])
def reject_species(species_id):
    # Only admin allowed
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("signin"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE species_submissions SET status='rejected' WHERE id=%s", (species_id,))
        conn.commit()
        cursor.close()
        conn.close()
        flash("Species rejected.", "info")
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")

    return redirect(url_for("management"))


# ---------------- Utility: View All Submissions (optional) ---------------- #
@app.route("/submissions")
def submissions():
    # Accessible to signed-in users; admin sees all
    if "user_id" not in session:
        flash("Please sign in to view submissions.", "error")
        return redirect(url_for("signin"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    if session.get("role") == "admin":
        cursor.execute("SELECT * FROM species_submissions ORDER BY created_at DESC")
    else:
        cursor.execute("SELECT * FROM species_submissions WHERE submitted_by=%s ORDER BY created_at DESC", (session["user_id"],))

    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template("submissions.html", submissions=rows)


# ---------------- Run ---------------- #
if __name__ == "__main__":
    app.run(debug=True)
