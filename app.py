import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
import datetime
import database
from data_structures import Queue, Stack, ComplaintHistoryList

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-fallback-key-change-me")

processing_queue = Queue()
undo_stack = Stack()


def is_admin_logged_in():
    return session.get("admin_id") is not None


def is_inspector_logged_in():
    return session.get("inspector_id") is not None

def block_staff():
    """Return True if admin/inspector is trying to access student pages."""
    return session.get("admin_id") is not None or session.get("inspector_id") is not None



def load_queue_from_db():
    global processing_queue
    processing_queue = Queue()
    for c in database.get_pending_complaints_fifo():
        processing_queue.enqueue(c)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/student")
def student_menu():
    if block_staff():
        return redirect(url_for("index"))
    return render_template("student_menu.html")


@app.route("/student/submit", methods=["GET", "POST"])
def student_submit():
    if block_staff():
        flash("Staff cannot submit complaints.", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        name = request.form.get("student_name", "").strip()
        roll = request.form.get("roll_number", "").strip().upper()
        roll = " ".join(roll.split())
        student_class = request.form.get("student_class", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        if not name or not roll or not student_class or not description or not category:
            flash("All fields are required.", "error")
            return redirect(url_for("student_submit"))
        date_submitted = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_id = database.insert_complaint(name, roll, student_class, category, description, date_submitted)
        if new_id is None:
            flash("Failed to submit.", "error")
            return redirect(url_for("student_submit"))
        return render_template("student_submitted.html", complaint_id=new_id, name=name)
    categories = ["Classroom", "Laboratory", "Washroom", "Library",
                  "Wi-Fi", "Electrical", "Water", "Furniture", "Teacher", "ID Card", "Other"]
    classes = ["AIML-A", "AIML-B", "AIML-C", "CO-A", "CO-B", "IT-A", "IT-B", "ME-A", "CE-A", "EE-A"]
    return render_template("student_submit.html", categories=categories, classes=classes)


@app.route("/student/track", methods=["GET", "POST"])
def student_track():
    if block_staff():
        flash("Staff cannot track complaints.", "error")
        return redirect(url_for("index"))
    complaint = None
    if request.method == "POST":
        try:
            cid = int(request.form.get("complaint_id", ""))
        except ValueError:
            flash("Enter a valid ID.", "error")
            return redirect(url_for("student_track"))
        complaint = database.get_complaint_by_id(cid)
        if complaint is None:
            flash("No complaint found.", "error")
    return render_template("student_track.html", complaint=complaint)


@app.route("/student/history", methods=["GET", "POST"])
def student_history():
    if block_staff():
        flash("Staff cannot view student history.", "error")
        return redirect(url_for("index"))
    history = None
    roll = ""
    if request.method == "POST":
        roll = request.form.get("roll_number", "").strip().upper()
        roll = " ".join(roll.split())
        if not roll:
            flash("Enter your roll number.", "error")
            return redirect(url_for("student_history"))
        complaints = database.get_complaints_by_roll(roll)
        hl = ComplaintHistoryList()
        for c in complaints:
            hl.add_complaint(c)
        history = hl.to_list()
        if not history:
            flash("No complaints found.", "error")
    return render_template("student_history.html", history=history, roll=roll)


# ---------------- ADMIN ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        admin = database.verify_admin(username, password)
        if admin:
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            load_queue_from_db()
            flash("Welcome, " + admin["username"] + "!", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid credentials.", "error")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_username", None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    selected_class = request.args.get("class", "")
    stats = database.get_complaint_stats(student_class=selected_class or None)
    dash = database.get_dashboard_data(student_class=selected_class or None)
    classes = database.get_class_summary()
    return render_template("admin_dashboard.html", stats=stats, dash=dash,
                           classes=classes, selected_class=selected_class,
                           queue_size=processing_queue.size(),
                           undo_size=undo_stack.size())


@app.route("/admin/complaints")
def admin_complaints():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    selected_class = request.args.get("class", "")
    sort_by = request.args.get("sort", "id")
    complaints = database.get_all_complaints(student_class=selected_class or None, sort_by=sort_by)
    classes = database.get_class_summary()
    # Mini dashboard for the current filter
    stats = database.get_complaint_stats(student_class=selected_class or None)
    dash = database.get_dashboard_data(student_class=selected_class or None)
    return render_template("admin_complaints.html", complaints=complaints,
                           classes=classes, selected_class=selected_class,
                           sort_by=sort_by, stats=stats, dash=dash)


@app.route("/admin/archived")
def admin_archived():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    complaints = database.get_all_complaints(include_archived=True)
    archived = [c for c in complaints if c.get("is_archived") == 1]
    return render_template("admin_archived.html", complaints=archived)


@app.route("/admin/reports")
def admin_reports():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    selected_class = request.args.get("class", "")
    dash = database.get_dashboard_data(student_class=selected_class or None)
    stats = database.get_complaint_stats(student_class=selected_class or None)
    classes = database.get_class_summary()
    return render_template("admin_reports.html", dash=dash, stats=stats,
                           classes=classes, selected_class=selected_class)


@app.route("/admin/process", methods=["POST"])
def admin_process():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    load_queue_from_db()
    if processing_queue.is_empty():
        flash("Queue is empty.", "error")
        return redirect(url_for("admin_dashboard"))
    c = processing_queue.dequeue()
    old_status = c["status"]
    new_status = "In Progress"
    database.update_complaint_status(c["complaint_id"], new_status, "")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    database.add_status_history(c["complaint_id"], old_status, new_status, now)
    undo_stack.push({"complaint_id": c["complaint_id"], "old_status": old_status,
                     "new_status": new_status, "remark": c["remark"] or ""})
    flash("Processed ID " + str(c["complaint_id"]) + " -> In Progress", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/search", methods=["GET", "POST"])
def admin_search():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    results = None
    mode = None
    query = ""
    if request.method == "POST":
        mode = request.form.get("mode", "id")
        query = request.form.get("query", "").strip()
        complaints = database.get_all_complaints()
        results = []
        if mode == "id":
            try:
                target = int(query)
            except ValueError:
                flash("Enter a valid ID.", "error")
                return render_template("admin_search.html", results=None)
            for c in complaints:
                if c["complaint_id"] == target:
                    results.append(c)
                    break
        else:
            for c in complaints:
                if c["roll_number"] == query:
                    results.append(c)
        if not results:
            flash("No matches found.", "error")
    return render_template("admin_search.html", results=results, mode=mode, query=query)


@app.route("/admin/sort", methods=["GET", "POST"])
def admin_sort():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    complaints = None
    order = None
    if request.method == "POST":
        order = request.form.get("order", "asc")
        complaints = database.get_all_complaints()
        n = len(complaints)
        for i in range(n - 1):
            for j in range(n - 1 - i):
                if order == "asc":
                    if complaints[j]["complaint_id"] > complaints[j + 1]["complaint_id"]:
                        complaints[j], complaints[j + 1] = complaints[j + 1], complaints[j]
                else:
                    if complaints[j]["complaint_id"] < complaints[j + 1]["complaint_id"]:
                        complaints[j], complaints[j + 1] = complaints[j + 1], complaints[j]
    return render_template("admin_sort.html", complaints=complaints, order=order)


@app.route("/admin/update")
def admin_update_list():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    complaints = database.get_all_complaints()
    return render_template("admin_update_list.html", complaints=complaints)


@app.route("/admin/update/<int:cid>", methods=["GET", "POST"])
def admin_update(cid):
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    complaint = database.get_complaint_by_id(cid)
    if complaint is None:
        flash("Not found.", "error")
        return redirect(url_for("admin_update_list"))
    if request.method == "POST":
        new_status = request.form.get("new_status", "").strip()
        remark = request.form.get("remark", "").strip()
        old_status = complaint["status"]
        valid = False
        if old_status == "Pending" and new_status == "In Progress":
            valid = True
        elif old_status == "In Progress" and new_status == "Resolved":
            valid = True
        if not valid:
            flash("Invalid transition.", "error")
            return redirect(url_for("admin_update", cid=cid))
        database.update_complaint_status(cid, new_status, remark)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        database.add_status_history(cid, old_status, new_status, now)
        undo_stack.push({"complaint_id": cid, "old_status": old_status,
                         "new_status": new_status, "remark": complaint["remark"] or ""})
        if new_status == "Resolved":
            database.archive_complaint(cid)
            flash("Complaint resolved and archived.", "success")
        else:
            flash("Status updated.", "success")
        return redirect(url_for("admin_update_list"))
    return render_template("admin_update.html", complaint=complaint)


@app.route("/admin/delete/<int:cid>", methods=["POST"])
def admin_delete(cid):
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    if database.delete_complaint(cid):
        flash("Complaint deleted.", "success")
    else:
        flash("Delete failed.", "error")
    return redirect(url_for("admin_complaints"))


@app.route("/admin/delete-resolved", methods=["POST"])
def admin_delete_resolved():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    complaints = database.get_all_complaints()
    deleted = 0
    for c in complaints:
        if c["status"] == "Resolved":
            if database.delete_complaint(c["complaint_id"]):
                deleted += 1
    flash("Deleted " + str(deleted) + " resolved complaint(s).", "success")
    return redirect(url_for("admin_complaints"))


@app.route("/admin/undo", methods=["POST"])
def admin_undo():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    if undo_stack.is_empty():
        flash("Nothing to undo.", "error")
        return redirect(url_for("admin_dashboard"))
    record = undo_stack.pop()
    cid = record["complaint_id"]
    old_status = record["old_status"]
    new_status = record["new_status"]
    existing = database.get_complaint_by_id(cid)
    if existing is None:
        flash("Cannot undo: complaint deleted.", "error")
        return redirect(url_for("admin_dashboard"))
    database.update_complaint_status(cid, old_status, record["remark"])
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    database.add_status_history(cid, new_status, old_status, now)
    flash("Undo successful.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/history/<int:cid>")
def admin_history(cid):
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    complaint = database.get_complaint_by_id(cid)
    if complaint is None:
        flash("Not found.", "error")
        return redirect(url_for("admin_complaints"))
    history = database.get_status_history(cid)
    return render_template("admin_history.html", complaint=complaint, history=history)


@app.route("/admin/manage-admins", methods=["GET", "POST"])
def admin_manage_admins():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if not username or not password:
                flash("All fields required.", "error")
            else:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ok, msg = database.add_admin(username, password, now)
                flash(msg, "success" if ok else "error")
        elif action == "delete":
            try:
                aid = int(request.form.get("admin_id", "0"))
            except ValueError:
                aid = 0
            if aid == session.get("admin_id"):
                flash("Cannot delete yourself.", "error")
            else:
                ok, msg = database.delete_admin(aid)
                flash(msg, "success" if ok else "error")
        return redirect(url_for("admin_manage_admins"))
    admins = database.get_all_admins()
    return render_template("admin_manage_admins.html", admins=admins)


@app.route("/admin/manage-inspectors", methods=["GET", "POST"])
def admin_manage_inspectors():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "create":
            name = request.form.get("name", "").strip()
            password = request.form.get("password", "").strip()
            if not name or not password:
                flash("All fields required.", "error")
            else:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ok, msg = database.add_inspector(name, password, session.get("admin_username"), now)
                flash(msg, "success" if ok else "error")
        elif action == "delete":
            try:
                iid = int(request.form.get("inspector_id", "0"))
            except ValueError:
                iid = 0
            ok, msg = database.delete_inspector(iid)
            flash(msg, "success" if ok else "error")
        return redirect(url_for("admin_manage_inspectors"))
    inspectors = database.get_all_inspectors()
    return render_template("admin_manage_inspectors.html", inspectors=inspectors)


# ---------------- INSPECTOR ----------------
@app.route("/inspector/login", methods=["GET", "POST"])
def inspector_login():
    if request.method == "POST":
        password = request.form.get("password", "").strip()
        inspector = database.verify_inspector(password)
        if inspector:
            session["inspector_id"] = inspector["id"]
            session["inspector_name"] = inspector["name"]
            flash("Welcome, " + inspector["name"] + "!", "success")
            return redirect(url_for("inspector_dashboard"))
        flash("Invalid password.", "error")
    return render_template("inspector_login.html")


@app.route("/inspector/logout")
def inspector_logout():
    session.pop("inspector_id", None)
    session.pop("inspector_name", None)
    flash("Logged out.", "success")
    return redirect(url_for("index"))


@app.route("/inspector/dashboard")
def inspector_dashboard():
    if not is_inspector_logged_in():
        return redirect(url_for("inspector_login"))
    selected_class = request.args.get("class", "")
    sort_by = request.args.get("sort", "id")
    complaints = database.get_all_complaints(student_class=selected_class or None, sort_by=sort_by)
    classes = database.get_class_summary()
    stats = database.get_complaint_stats(student_class=selected_class or None)
    dash = database.get_dashboard_data(student_class=selected_class or None)
    return render_template("inspector_dashboard.html", complaints=complaints,
                           classes=classes, selected_class=selected_class,
                           sort_by=sort_by, stats=stats, dash=dash)


@app.route("/inspector/view/<int:cid>")
def inspector_view(cid):
    if not is_inspector_logged_in():
        return redirect(url_for("inspector_login"))
    complaint = database.get_complaint_by_id(cid)
    if complaint is None:
        flash("Not found.", "error")
        return redirect(url_for("inspector_dashboard"))
    history = database.get_status_history(cid)
    return render_template("inspector_view.html", complaint=complaint, history=history)


def seed_sample_data():
    if len(database.get_all_complaints()) > 0:
        return
    sample = [
        ("Aarav Sharma", "AIML01", "AIML-A", "Classroom", "Fan not working in room 101", "2024-01-10 09:15:00"),
        ("Diya Patel",   "AIML02", "AIML-A", "Classroom", "Projector not displaying", "2024-01-10 10:00:00"),
        ("Rohan Mehta",  "AIML03", "AIML-B", "Washroom",  "Washroom near lab not clean", "2024-01-11 11:20:00"),
        ("Sara Khan",    "AIML04", "AIML-B", "Laboratory","Computer no. 12 not starting", "2024-01-11 12:00:00"),
        ("Vivaan Joshi", "AIML05", "AIML-C", "Wi-Fi",     "Wi-Fi very slow in library", "2024-01-12 09:30:00"),
        ("Anaya Desai",  "AIML06", "AIML-C", "Library",   "Library books not arranged", "2024-01-12 10:45:00"),
        ("Kabir Singh",  "CO01",   "CO-A",   "Water",     "Water cooler not working", "2024-01-13 08:50:00"),
        ("Isha Verma",   "CO02",   "CO-A",   "Furniture", "Broken bench in room 205", "2024-01-13 11:10:00"),
        ("Arjun Rao",    "IT01",   "IT-A",   "Teacher",   "Teacher not attending lectures", "2024-01-14 09:00:00"),
        ("Meera Nair",   "IT02",   "IT-B",   "ID Card",   "ID card not received", "2024-01-14 10:30:00"),
    ]
    for s in sample:
        database.insert_complaint(s[0], s[1], s[2], s[3], s[4], s[5])




@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

if __name__ == "__main__":
    database.init_db()
    seed_sample_data()
    port = int(os.environ.get("PORT", 5000))
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug_mode)



# ============================================================
# WSGI Entry Point (for production servers: Gunicorn, Waitress)
# ============================================================
# Hosting platforms like Render look for "application" here.
# Local dev uses "py app.py" which runs the __main__ block above.

application = app
