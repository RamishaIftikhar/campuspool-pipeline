import os
import pymysql
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

application = app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me")


def db():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 3306)),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "campuspool"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def q(sql, args=(), one=False, write=False):
    conn = db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            if write:
                return cur.lastrowid
            return cur.fetchone() if one else cur.fetchall()
    finally:
        conn.close()


def init_db():
    schema = open(os.path.join(os.path.dirname(__file__), "schema.sql")).read()
    for stmt in schema.split(";"):
        if stmt.strip():
            q(stmt, write=True)


try:
    init_db()
except Exception as e:
    print("DB init failed:", e)


def login_required(f):
    @wraps(f)
    def wrapper(*a, **k):
        if "uid" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrapper


@app.route("/")
def index():
    s = q("SELECT (SELECT COUNT(*) FROM rides WHERE status='open') AS rides, "
          "(SELECT COUNT(*) FROM users) AS users, "
          "(SELECT COUNT(*) FROM bookings WHERE status='approved') AS seats", one=True)
    return render_template("index.html", s=s)


@app.route("/health")
def health():
    try:
        q("SELECT 1")
        return "OK", 200
    except Exception as e:
        return "DB error: %s" % e, 500


# ---- Module 1: accounts ----
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        if len(f["username"].strip()) < 3 or len(f["password"]) < 6 or not f["full_name"].strip():
            flash("Enter your name, a username of 3+ characters and a password of 6+.")
        else:
            try:
                q("INSERT INTO users (username, full_name, password_hash) VALUES (%s,%s,%s)",
                  (f["username"].strip(), f["full_name"].strip(), generate_password_hash(f["password"])), write=True)
                flash("Account created. Log in to continue.")
                return redirect(url_for("login"))
            except pymysql.err.IntegrityError:
                flash("That username is taken.")
    return render_template("auth.html", title="Register", register=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q("SELECT * FROM users WHERE username=%s", (request.form["username"].strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.update(uid=u["id"], user=u["full_name"])
            return redirect(url_for("dashboard"))
        flash("Wrong username or password.")
    return render_template("auth.html", title="Login", register=False)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---- Module 2: rides ----
@app.route("/rides")
def rides():
    o, d = request.args.get("from", ""), request.args.get("to", "")
    rows = q("SELECT r.*, u.full_name FROM rides r JOIN users u ON u.id=r.driver_id "
             "WHERE r.status='open' AND r.origin LIKE %s AND r.destination LIKE %s ORDER BY r.depart_at",
             ("%" + o + "%", "%" + d + "%"))
    return render_template("rides.html", rides=rows, o=o, d=d)


@app.route("/rides/new", methods=["GET", "POST"])
@login_required
def new_ride():
    if request.method == "POST":
        f = request.form
        try:
            seats, price = int(f["seats"]), int(f["price"])
        except ValueError:
            seats, price = 0, -1
        if seats < 1 or price < 0:
            flash("Seats must be at least 1 and the price cannot be negative.")
        else:
            q("INSERT INTO rides (driver_id, origin, destination, depart_at, seats, price) VALUES (%s,%s,%s,%s,%s,%s)",
              (session["uid"], f["origin"], f["destination"], f["depart_at"].replace("T", " "), seats, price), write=True)
            flash("Ride posted.")
            return redirect(url_for("dashboard"))
    return render_template("ride_form.html")


@app.route("/rides/<int:rid>/cancel", methods=["POST"])
@login_required
def cancel_ride(rid):
    r = q("SELECT * FROM rides WHERE id=%s", (rid,), one=True)
    if r and r["driver_id"] == session["uid"] and r["status"] == "open":
        q("UPDATE rides SET status='cancelled' WHERE id=%s", (rid,), write=True)
        q("UPDATE bookings SET status='cancelled' WHERE ride_id=%s AND status IN ('pending','approved')", (rid,), write=True)
        flash("Ride cancelled and passengers released.")
    else:
        flash("You can only cancel your own open rides.")
    return redirect(url_for("dashboard"))


# ---- Module 3: seat requests ----
@app.route("/rides/<int:rid>/book", methods=["POST"])
@login_required
def book(rid):
    r = q("SELECT * FROM rides WHERE id=%s", (rid,), one=True)
    dup = q("SELECT id FROM bookings WHERE ride_id=%s AND rider_id=%s AND status IN ('pending','approved')",
            (rid, session["uid"]), one=True)
    if not r or r["status"] != "open" or r["seats"] < 1:
        flash("This ride is full or closed.")
    elif r["driver_id"] == session["uid"]:
        flash("You cannot book your own ride.")
    elif dup:
        flash("You already requested this ride.")
    else:
        q("INSERT INTO bookings (ride_id, rider_id) VALUES (%s,%s)", (rid, session["uid"]), write=True)
        flash("Seat requested. The driver will approve or reject it.")
    return redirect(url_for("rides"))


@app.route("/bookings/<int:bid>/<action>", methods=["POST"])
@login_required
def booking_action(bid, action):
    b = q("SELECT b.*, r.driver_id, r.seats AS seats_left FROM bookings b JOIN rides r ON r.id=b.ride_id WHERE b.id=%s",
          (bid,), one=True)
    uid = session["uid"]
    if not b:
        flash("Booking not found.")
    elif action == "approve" and b["driver_id"] == uid and b["status"] == "pending":
        if b["seats_left"] < 1:
            flash("No seats left on this ride.")
        else:
            q("UPDATE bookings SET status='approved' WHERE id=%s", (bid,), write=True)
            q("UPDATE rides SET seats=seats-1 WHERE id=%s", (b["ride_id"],), write=True)
            flash("Passenger approved.")
    elif action == "reject" and b["driver_id"] == uid and b["status"] == "pending":
        q("UPDATE bookings SET status='rejected' WHERE id=%s", (bid,), write=True)
        flash("Request rejected.")
    elif action == "cancel" and b["rider_id"] == uid and b["status"] in ("pending", "approved"):
        if b["status"] == "approved":
            q("UPDATE rides SET seats=seats+1 WHERE id=%s", (b["ride_id"],), write=True)
        q("UPDATE bookings SET status='cancelled' WHERE id=%s", (bid,), write=True)
        flash("Booking cancelled.")
    else:
        flash("That action is not allowed.")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["uid"]
    mine = q("SELECT * FROM rides WHERE driver_id=%s ORDER BY depart_at DESC", (uid,))
    reqs = q("SELECT b.*, u.full_name, r.origin, r.destination FROM bookings b JOIN rides r ON r.id=b.ride_id "
             "JOIN users u ON u.id=b.rider_id WHERE r.driver_id=%s ORDER BY b.created_at DESC", (uid,))
    trips = q("SELECT b.*, r.origin, r.destination, r.depart_at, u.full_name AS driver FROM bookings b "
              "JOIN rides r ON r.id=b.ride_id JOIN users u ON u.id=r.driver_id WHERE b.rider_id=%s "
              "ORDER BY b.created_at DESC", (uid,))
    return render_template("dashboard.html", mine=mine, reqs=reqs, trips=trips)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
