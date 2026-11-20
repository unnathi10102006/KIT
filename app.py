"""Local Farmer Market Information System  (version 2)
Backend: Python + Flask + SQLite  |  Frontend: HTML + CSS + a little JavaScript
Run:  python app.py
"""
import json
import math
import os
import socket
import sqlite3
import urllib.request
import uuid
from datetime import datetime
from functools import wraps

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-real-use")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB photo limit

CATEGORIES = ["Vegetables", "Fruits", "Grains", "Pulses", "Dairy", "Spices", "Other"]
UNITS = ["kg", "quintal", "dozen", "litre", "piece"]
BUYER_KINDS = ["Retailer", "Wholesaler", "Restaurant", "Processor", "Hostel / Canteen"]
PERISHABLE = {"Vegetables", "Fruits", "Dairy"}

# Approximate town coordinates (latitude, longitude) used to measure distance.
TOWNS = {
    "Challakere": (14.3167, 76.6500), "Chitradurga": (14.2251, 76.3980),
    "Hiriyur": (13.9400, 76.6200), "Molakalmuru": (14.7167, 76.7333),
    "Hosadurga": (13.7956, 76.2867), "Holalkere": (14.0400, 76.1833),
    "Davanagere": (14.4644, 75.9218), "Tumakuru": (13.3379, 77.1173),
    "Sira": (13.7414, 76.9040), "Pavagada": (14.1000, 77.2833),
    "Ballari": (15.1394, 76.9214), "Hosapete": (15.2689, 76.3871),
    "Anantapur": (14.6819, 77.6006), "Bengaluru": (12.9716, 77.5946),
    "Mysuru": (12.2958, 76.6394), "Shivamogga": (13.9299, 75.5681),
    "Hubballi": (15.3647, 75.1240),
}

# Reference market prices: name -> (base price, unit, category, emoji)
MARKET = {
    "tomato": (24, "kg", "Vegetables", "🍅"), "onion": (22, "kg", "Vegetables", "🧅"),
    "potato": (20, "kg", "Vegetables", "🥔"), "carrot": (38, "kg", "Vegetables", "🥕"),
    "cabbage": (16, "kg", "Vegetables", "🥬"), "brinjal": (30, "kg", "Vegetables", "🍆"),
    "chilli": (70, "kg", "Vegetables", "🌶️"), "garlic": (120, "kg", "Vegetables", "🧄"),
    "banana": (45, "dozen", "Fruits", "🍌"), "mango": (60, "kg", "Fruits", "🥭"),
    "grapes": (70, "kg", "Fruits", "🍇"), "orange": (55, "kg", "Fruits", "🍊"),
    "watermelon": (14, "kg", "Fruits", "🍉"), "coconut": (28, "piece", "Fruits", "🥥"),
    "groundnut": (78, "kg", "Pulses", "🥜"), "toor dal": (105, "kg", "Pulses", "🫘"),
    "ragi": (36, "kg", "Grains", "🌾"), "maize": (22, "kg", "Grains", "🌽"),
    "rice": (40, "kg", "Grains", "🌾"), "milk": (44, "litre", "Dairy", "🥛"),
    "turmeric": (95, "kg", "Spices", "🟡"),
}
CAT_ICON = {"Vegetables": "🥬", "Fruits": "🍎", "Grains": "🌾", "Pulses": "🫘",
            "Dairy": "🥛", "Spices": "🌶️", "Other": "🌱"}


# ================================================================ database
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS farmers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            village TEXT NOT NULL, phone TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL, lat REAL, lon REAL);
        CREATE TABLE IF NOT EXISTS crops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_id INTEGER NOT NULL REFERENCES farmers(id),
            name TEXT NOT NULL, category TEXT NOT NULL, price REAL NOT NULL,
            unit TEXT NOT NULL, quantity REAL NOT NULL,
            available INTEGER NOT NULL DEFAULT 1, image TEXT,
            updated TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS buyers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            kind TEXT NOT NULL, town TEXT NOT NULL, phone TEXT NOT NULL,
            buys TEXT NOT NULL, lat REAL, lon REAL);
    """)
    if db.execute("SELECT COUNT(*) FROM farmers").fetchone()[0] == 0:
        lat, lon = TOWNS["Challakere"]
        db.execute("INSERT INTO farmers (name, village, phone, password_hash, lat, lon) "
                   "VALUES (?,?,?,?,?,?)",
                   ("Ramesh Gowda", "Challakere", "9999999999",
                    generate_password_hash("demo123"), lat, lon))
        db.executemany(
            "INSERT INTO crops (farmer_id, name, category, price, unit, quantity) VALUES (1,?,?,?,?,?)",
            [("Tomato", "Vegetables", 27, "kg", 200), ("Groundnut", "Pulses", 74, "kg", 500),
             ("Banana", "Fruits", 48, "dozen", 100), ("Ragi", "Grains", 36, "kg", 800),
             ("Onion", "Vegetables", 21, "kg", 350)])
    if db.execute("SELECT COUNT(*) FROM buyers").fetchone()[0] == 0:
        demo = [
            ("Sri Lakshmi Fruits & Vegetables", "Retailer", "Challakere", "9000000001", "Tomato,Onion,Banana,Potato"),
            ("Malnad Mess (Hotel)", "Restaurant", "Chitradurga", "9000000002", "Tomato,Onion,Potato,Chilli"),
            ("Chitradurga APMC Traders", "Wholesaler", "Chitradurga", "9000000003", "Groundnut,Ragi,Maize,Onion"),
            ("Hiriyur Oil Mill", "Processor", "Hiriyur", "9000000004", "Groundnut"),
            ("Fresh Basket Super Mart", "Retailer", "Tumakuru", "9000000005", "Tomato,Banana,Mango,Carrot"),
            ("Davanagere Grain Merchants", "Wholesaler", "Davanagere", "9000000006", "Maize,Ragi,Rice"),
            ("Students Hostel Mess Group", "Hostel / Canteen", "Challakere", "9000000007", "Rice,Tomato,Onion,Potato"),
            ("Bengaluru Fresh Outlet", "Retailer", "Bengaluru", "9000000008", "Tomato,Banana,Mango,Carrot,Cabbage"),
        ]
        db.executemany("INSERT INTO buyers (name, kind, town, phone, buys, lat, lon) VALUES (?,?,?,?,?,?,?)",
                       [(n, k, t, p, b, *TOWNS[t]) for n, k, t, p, b in demo])
    db.commit()
    db.close()


# ================================================================ market prices
def _phase(name):
    return (sum(ord(c) for c in name.lower()) % 628) / 100.0


def market_price(name, back=0):
    """Reference price that changes smoothly every 5 minutes (demo/simulated)."""
    item = MARKET.get(name.lower())
    if not item:
        return None
    bucket = int(datetime.now().timestamp() // 300) - back
    ph = _phase(name)
    swing = 0.07 * math.sin(bucket / 12 + ph) + 0.03 * math.sin(bucket / 4 + ph * 2)
    return round(item[0] * (1 + swing), 2)


def price_snapshot():
    rows = []
    for name, (base, unit, cat, icon) in MARKET.items():
        now, before = market_price(name), market_price(name, back=1)
        change = round((now - before) / before * 100, 2)
        trend = "up" if change > 0.05 else "down" if change < -0.05 else "flat"
        rows.append({"name": name.title(), "icon": icon, "category": cat, "unit": unit,
                     "price": now, "change": change, "trend": trend})
    return rows


def compare(name, price, unit):
    """Compare a farmer's price with the market price (converted to the same unit)."""
    item = MARKET.get(str(name).lower())
    if not item:
        return None
    mp, m_unit = market_price(name), item[1]
    if unit == m_unit:
        pass
    elif unit == "quintal" and m_unit == "kg":
        mp *= 100
    elif unit == "kg" and m_unit == "quintal":
        mp /= 100
    else:
        return None
    diff = round((price - mp) / mp * 100, 1)
    if diff > 5:
        label, cls = f"{diff:g}% above market", "above"
    elif diff < -5:
        label, cls = f"{abs(diff):g}% below market", "below"
    else:
        label, cls = "At market price", "fair"
    return {"market": round(mp, 2), "diff": diff, "label": label, "cls": cls}


def crop_icon(name, category="Other"):
    item = MARKET.get(str(name).lower())
    return item[3] if item else CAT_ICON.get(category, "🌱")


app.jinja_env.filters["crop_icon"] = crop_icon
app.jinja_env.globals["compare"] = compare


# ================================================================ helpers
def distance_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def nearby_buyers(farmer, radius=None, crop=""):
    out = []
    for b in get_db().execute("SELECT * FROM buyers").fetchall():
        d = distance_km(farmer["lat"], farmer["lon"], b["lat"], b["lon"])
        if radius and d > radius:
            continue
        buys = [x.strip() for x in b["buys"].split(",") if x.strip()]
        if crop and crop.lower() not in [x.lower() for x in buys]:
            continue
        out.append({**dict(b), "distance": round(d), "buys_list": buys})
    return sorted(out, key=lambda x: x["distance"])


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "farmer_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Please log in"}), 401
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def current_farmer():
    return get_db().execute("SELECT * FROM farmers WHERE id=?", (session["farmer_id"],)).fetchone()


def read_crop_form():
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "Other")
    unit = request.form.get("unit", "kg")
    try:
        price = float(request.form.get("price", ""))
        quantity = float(request.form.get("quantity", ""))
    except ValueError:
        return None, "Price and quantity must be numbers."
    if not name:
        return None, "Crop name is required."
    if price < 0 or quantity < 0:
        return None, "Price and quantity cannot be negative."
    if category not in CATEGORIES or unit not in UNITS:
        return None, "Invalid category or unit."
    return (name, category, price, unit, quantity), None


def save_image(file):
    """Save an uploaded photo. Returns filename, None (no file) or raises ValueError."""
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in {"png", "jpg", "jpeg", "webp"}:
        raise ValueError("Photo must be a PNG, JPG or WEBP file.")
    name = uuid.uuid4().hex + "." + ext
    file.save(os.path.join(UPLOAD_DIR, name))
    return name


def remove_image(name):
    if name:
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass


def own_crop(crop_id):
    return get_db().execute("SELECT * FROM crops WHERE id=? AND farmer_id=?",
                            (crop_id, session["farmer_id"])).fetchone()


@app.errorhandler(413)
def too_big(_e):
    return render_template("message.html", text="That photo is too large (max 4 MB)."), 413


# ================================================================ AI advisor
KNOW = {
    "tomato": dict(
        season="Tomato can be grown most of the year. In Karnataka, nurseries are commonly sown around June-July and Oct-Nov.",
        water="Water regularly but never let water stand. Drip irrigation saves water and lowers disease risk.",
        pests="Watch for fruit borer, whitefly (leaf curl virus) and blight. Remove infected plants, use yellow sticky traps, and ask your local Krishi Vigyan Kendra (KVK) before spraying.",
        store="Tomato is perishable. Sell within 3-5 days. Pick at the firm, just-turning-red stage for transport.",
        fert="Use well-rotted farmyard manure with balanced NPK. A soil test tells you the exact amount."),
    "onion": dict(
        season="Onion is commonly sown in kharif (June-July) and rabi (Oct-Nov) in Karnataka.",
        water="Light, frequent irrigation early on. Stop watering 10-15 days before harvest so bulbs cure well.",
        pests="Thrips and purple blotch are common. Avoid overcrowding, keep fields weed-free, and consult KVK for spray advice.",
        store="After harvest, dry (cure) bulbs in shade for a week. Store in a dry, well-ventilated place. Onions keep for weeks, so you can wait for a better price.",
        fert="Needs good organic matter and balanced NPK; extra sulphur helps bulb quality. Do a soil test."),
    "groundnut": dict(
        season="Groundnut is usually sown June-July (kharif) and sometimes Oct-Nov (rabi) under irrigation.",
        water="Needs moisture at flowering and pod formation. Avoid waterlogging.",
        pests="Leaf spot and leaf miner are common. Use treated seed and rotate crops. Ask KVK for the right spray if needed.",
        store="Dry pods well (below about 8-9% moisture) before storing, to avoid mould. Dry pods store well, so you can hold for a better price.",
        fert="Gypsum at flowering helps pod filling. Follow a soil test for the rest."),
    "ragi": dict(
        season="Ragi is a kharif crop, usually sown June-August with the monsoon.",
        water="Hardy and drought tolerant. One or two protective irrigations in dry spells help yield.",
        pests="Blast disease is the main concern in wet weather. Use disease-free seed and ask KVK about resistant varieties.",
        store="Store grain after drying properly. Ragi stores for a long time, so waiting for a better price is usually safe.",
        fert="Farmyard manure plus modest NPK is usually enough."),
    "maize": dict(
        season="Maize is sown June-July (kharif) and can also be sown in rabi/summer with irrigation.",
        water="Critical times for water are tasseling and grain filling.",
        pests="Fall armyworm is a serious pest. Scout fields weekly, check the whorl of young plants, and contact KVK early.",
        store="Dry grain to about 12-13% moisture before storage to prevent mould and insects.",
        fert="Maize responds well to nitrogen, applied in 2-3 splits."),
    "banana": dict(
        season="Banana can be planted most of the year if water is available; avoid the hottest weeks.",
        water="Needs regular water. Drip irrigation is strongly recommended.",
        pests="Watch for Sigatoka leaf spot and rhizome weevil. Remove dry leaves and keep the field clean.",
        store="Cut bunches at the right maturity and sell quickly. Do not store near ripening fruit.",
        fert="Heavy feeder: organic manure plus split doses of NPK, especially potash."),
    "chilli": dict(
        season="Chilli is usually transplanted June-July or Oct-Nov.",
        water="Moderate watering; both drought and waterlogging cause flower drop.",
        pests="Thrips, mites and leaf curl are common. Use sticky traps and consult KVK.",
        store="Dry red chilli well in shade or sun and store in airy bags. Dried chilli keeps for months.",
        fert="Balanced NPK with organic manure; avoid too much nitrogen."),
    "coconut": dict(
        season="Coconut seedlings are planted at the start of the monsoon.",
        water="Needs regular watering in summer, especially for young palms.",
        pests="Rhinoceros beetle and red palm weevil are the main pests. Keep the crown clean and ask KVK for control methods.",
        store="Mature nuts can be stored for some weeks. Copra (dried kernel) stores longer and can fetch a better price.",
        fert="Apply manure and NPK twice a year around the palm."),
    "potato": dict(
        season="Potato is commonly planted in kharif or rabi, depending on your area's cool weather.",
        water="Light, regular irrigation; avoid waterlogging.",
        pests="Late blight is the big risk in cool, damp weather. Use healthy seed tubers and consult KVK.",
        store="Cure tubers and store in a cool, dark, dry place. Light turns them green and bitter.",
        fert="Needs organic manure and balanced NPK, with extra potash."),
}
INTENTS = [
    ("buyer", ["buyer", "where to sell", "who buys", "customer", "wholesale", "shop", "trader"]),
    ("pest", ["pest", "disease", "insect", "worm", "spot", "blight", "yellow", "wilt", "spray"]),
    ("water", ["water", "irrigat", "drip"]),
    ("fert", ["fertili", "manure", "soil", "npk", "compost"]),
    ("store", ["store", "storage", "preserve", "shelf"]),
    ("season", ["season", "sow", "plant", "grow", "month", "kharif", "rabi"]),
    ("sell", ["sell", "price", "rate", "worth", "profit", "market", "hold", "wait", "demand", "cost"]),
]
SYSTEM_PROMPT = ("You are a friendly farming and market advisor for small farmers near Challakere, "
                 "Karnataka, India. Give short, practical, simple answers (under 150 words). Use the "
                 "farmer's data below when relevant. Prices shown are demo prices, so mention that real "
                 "mandi rates should be checked. Never give exact pesticide doses; tell the farmer to "
                 "consult the local Krishi Vigyan Kendra or agriculture officer for chemicals.")


def sell_advice(crop):
    name, price, unit, cat = crop["name"], crop["price"], crop["unit"], crop["category"]
    snap = {p["name"].lower(): p for p in price_snapshot()}.get(name.lower())
    cmp_ = compare(name, price, unit)
    if not cmp_ or not snap:
        return f"I don't have a market price for {name} yet, so I can't compare. Check your nearest mandi rate before fixing the price."
    trend = {"up": "rising", "down": "falling", "flat": "steady"}[snap["trend"]]
    lines = [f"{name}: market price now is about ₹{cmp_['market']:g}/{unit} and it is {trend}. Your price is ₹{price:g}/{unit} ({cmp_['label']})."]
    if cmp_["cls"] == "above":
        lines.append("Buyers may bargain. If you want to sell quickly, consider coming closer to the market price.")
    elif cmp_["cls"] == "below":
        lines.append(f"You may be underpricing. You could raise it toward ₹{cmp_['market']:g}/{unit}.")
    else:
        lines.append("Your price is fair for today.")
    if snap["trend"] == "up" and cat not in PERISHABLE:
        lines.append("Prices are rising and this crop stores well, so holding for a few days could pay off.")
    elif snap["trend"] == "down" and cat in PERISHABLE:
        lines.append("This crop is perishable and prices are falling, so selling soon is safer.")
    elif cat in PERISHABLE:
        lines.append("It is perishable, so don't wait too long.")
    return " ".join(lines)


def rule_based_advice(question, farmer, crops):
    q = question.lower()
    names = {c["name"].lower(): c for c in crops}
    crop_key = next((k for k in list(names) + list(KNOW) + list(MARKET) if k in q), None)
    intent = next((i for i, words in INTENTS if any(w in q for w in words)), None)

    if intent == "buyer":
        buyers = nearby_buyers(farmer, 100, crop_key.title() if crop_key else "")[:3]
        if not buyers:
            return "I couldn't find buyers for that within 100 km. Open Nearby Buyers and widen the search."
        txt = "Nearest buyers" + (f" for {crop_key.title()}" if crop_key else "") + ":\n"
        txt += "\n".join(f"- {b['name']} ({b['kind']}), {b['town']}, {b['distance']} km, phone {b['phone']}" for b in buyers)
        return txt + "\nOpen the Nearby Buyers page for call and WhatsApp buttons."

    if intent in ("pest", "water", "fert", "store", "season") and crop_key in KNOW:
        key = {"pest": "pests", "water": "water", "fert": "fert", "store": "store", "season": "season"}[intent]
        tail = " For chemicals and exact doses, please ask your local KVK or agriculture officer." if intent == "pest" else ""
        return KNOW[crop_key][key] + tail
    if intent in ("pest", "water", "fert", "store", "season") and crop_key not in KNOW:
        return ("Which crop is this about? I have detailed tips for: " + ", ".join(c.title() for c in KNOW) + ".")

    if crop_key and (intent == "sell" or intent is None):
        if crop_key in names:
            return sell_advice(names[crop_key])
        item = MARKET.get(crop_key)
        if item:
            return f"{crop_key.title()} market price now is about ₹{market_price(crop_key):g}/{item[1]} (demo price)."
    if intent == "sell" or any(w in q for w in ("summary", "hello", "hi", "help", "today")):
        if not crops:
            return "You haven't added any crops yet. Add a crop in My Crops and I will compare your price with the market."
        return "\n\n".join(sell_advice(c) for c in crops[:4])
    return ("I can help with selling prices, nearby buyers, watering, pests, fertilizer, storage and sowing season. "
            "Try: 'Should I sell my tomato now?' or 'How to store onion?'")


def ask_llm(question, farmer, crops):
    """Optional: uses Claude if ANTHROPIC_API_KEY is set. Returns text or None."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    ctx = (f"Farmer: {farmer['name']}, {farmer['village']}.\nTheir crops: " +
           "; ".join(f"{c['name']} ₹{c['price']:g}/{c['unit']}, {c['quantity']:g} {c['unit']}" for c in crops) +
           "\nMarket demo prices: " + "; ".join(f"{p['name']} ₹{p['price']:g}/{p['unit']} ({p['trend']})" for p in price_snapshot()[:12]))
    body = json.dumps({
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"), "max_tokens": 600,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"{ctx}\n\nQuestion: {question}"}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
        return text or None
    except Exception:
        return None


# ================================================================ cart & likes
@app.route("/cart/add/<int:crop_id>", methods=["POST"])
def cart_add(crop_id):
    crop = get_db().execute(
        "SELECT c.*, f.name AS farmer_name, f.phone FROM crops c JOIN farmers f ON f.id=c.farmer_id WHERE c.id=? AND c.available=1",
        (crop_id,)).fetchone()
    if crop:
        cart = session.get("cart", {})
        key = str(crop_id)
        qty = int(request.form.get("qty", 1))
        if key in cart:
            cart[key]["qty"] += qty
        else:
            cart[key] = {"id": crop_id, "name": crop["name"], "price": crop["price"],
                         "unit": crop["unit"], "farmer": crop["farmer_name"],
                         "phone": crop["phone"], "qty": qty}
        session["cart"] = cart
        flash(f"{crop['name']} added to cart! 🛒", "ok")
    return redirect(request.referrer or url_for("index"))


@app.route("/cart/remove/<int:crop_id>", methods=["POST"])
def cart_remove(crop_id):
    cart = session.get("cart", {})
    cart.pop(str(crop_id), None)
    session["cart"] = cart
    return redirect(url_for("cart"))


@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = {}
    flash("Cart cleared.", "ok")
    return redirect(url_for("cart"))


@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    total = sum(v["price"] * v["qty"] for v in cart.values())
    return render_template("cart.html", cart=cart, total=total)


@app.route("/cart/checkout", methods=["POST"])
def checkout():
    session["cart"] = {}
    flash("✅ Order placed! The farmer will contact you shortly.", "ok")
    return redirect(url_for("index"))


@app.route("/like/<int:crop_id>", methods=["POST"])
def like_crop(crop_id):
    likes = session.get("likes", [])
    if crop_id in likes:
        likes.remove(crop_id)
    else:
        likes.append(crop_id)
    session["likes"] = likes
    return jsonify({"liked": crop_id in likes, "count": likes.count(crop_id)})


# ================================================================ public pages
@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    rows = get_db().execute(
        """SELECT c.*, f.name AS farmer_name, f.village, f.phone, f.id AS fid
           FROM crops c JOIN farmers f ON f.id = c.farmer_id
           WHERE c.available = 1 AND (c.name LIKE ? OR f.village LIKE ?)
             AND (? = '' OR c.category = ?)
           ORDER BY c.updated DESC""", (f"%{q}%", f"%{q}%", category, category)).fetchall()
    return render_template("index.html", crops=rows, q=q, category=category, categories=CATEGORIES,
                           likes=session.get("likes", []), cart=session.get("cart", {}))


@app.route("/prices")
def prices():
    return render_template("prices.html", prices=price_snapshot(), stamp=datetime.now().strftime("%d %b %Y, %I:%M %p"))


@app.route("/api/prices")
def api_prices():
    return jsonify({"prices": price_snapshot(), "stamp": datetime.now().strftime("%d %b %Y, %I:%M:%S %p")})


@app.route("/farmer/<int:farmer_id>")
def farmer(farmer_id):
    db = get_db()
    f = db.execute("SELECT * FROM farmers WHERE id=?", (farmer_id,)).fetchone()
    if f is None:
        return render_template("message.html", text="Farmer not found."), 404
    crops = db.execute("SELECT * FROM crops WHERE farmer_id=? AND available=1 ORDER BY name", (farmer_id,)).fetchall()
    return render_template("farmer.html", f=f, crops=crops)


# ================================================================ accounts
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        town = request.form.get("village", "")
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        if not (name and town in TOWNS and phone.isdigit() and len(phone) == 10):
            flash("Fill all fields. Phone must be 10 digits.", "error")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            try:
                db = get_db()
                cur = db.execute("INSERT INTO farmers (name, village, phone, password_hash, lat, lon) VALUES (?,?,?,?,?,?)",
                                 (name, town, phone, generate_password_hash(password), *TOWNS[town]))
                db.commit()
                session["farmer_id"], session["farmer_name"] = cur.lastrowid, name
                flash("Welcome! Your account is ready. Add your crops below.", "ok")
                return redirect(url_for("dashboard"))
            except sqlite3.IntegrityError:
                flash("That phone number is already registered.", "error")
    return render_template("register.html", towns=sorted(TOWNS))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        f = get_db().execute("SELECT * FROM farmers WHERE phone=?", (phone,)).fetchone()
        if f and check_password_hash(f["password_hash"], request.form.get("password", "")):
            session["farmer_id"], session["farmer_name"] = f["id"], f["name"]
            return redirect(url_for("dashboard"))
        flash("Wrong phone number or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "ok")
    return redirect(url_for("index"))


# ================================================================ farmer area
@app.route("/dashboard")
@login_required
def dashboard():
    f = current_farmer()
    crops = get_db().execute("SELECT * FROM crops WHERE farmer_id=? ORDER BY updated DESC", (f["id"],)).fetchall()
    live = [c for c in crops if c["available"]]
    rows = [{"crop": c, "cmp": compare(c["name"], c["price"], c["unit"])} for c in crops]
    stock_value = sum(c["price"] * c["quantity"] for c in live)
    chart = sorted(({"name": c["name"], "value": c["price"] * c["quantity"]} for c in live),
                   key=lambda x: -x["value"])[:6]
    top = max([x["value"] for x in chart], default=1) or 1
    for x in chart:
        x["pct"] = max(4, round(x["value"] / top * 100))
    buyers = nearby_buyers(f, 50)
    tip = sell_advice(live[0]) if live else "Add your first crop to get price tips."
    return render_template("dashboard.html", f=f, rows=rows, total=len(crops), live=len(live),
                           stock_value=stock_value, chart=chart, buyers=buyers, tip=tip,
                           snap=price_snapshot()[:6], now=datetime.now().strftime("%A, %d %B"))


@app.route("/crops")
@login_required
def my_crops():
    crops = get_db().execute("SELECT * FROM crops WHERE farmer_id=? ORDER BY updated DESC", (session["farmer_id"],)).fetchall()
    return render_template("crops.html", crops=crops)


@app.route("/crop/add", methods=["GET", "POST"])
@login_required
def add_crop():
    if request.method == "POST":
        data, error = read_crop_form()
        image = None
        if not error:
            try:
                image = save_image(request.files.get("photo"))
            except ValueError as e:
                error = str(e)
        if error:
            flash(error, "error")
        else:
            db = get_db()
            db.execute("INSERT INTO crops (farmer_id, name, category, price, unit, quantity, image) VALUES (?,?,?,?,?,?,?)",
                       (session["farmer_id"], *data, image))
            db.commit()
            flash("Crop added.", "ok")
            return redirect(url_for("my_crops"))
    return render_template("crop_form.html", crop=None, categories=CATEGORIES, units=UNITS)


@app.route("/crop/<int:crop_id>/edit", methods=["GET", "POST"])
@login_required
def edit_crop(crop_id):
    crop = own_crop(crop_id)
    if crop is None:
        return render_template("message.html", text="Crop not found."), 404
    if request.method == "POST":
        data, error = read_crop_form()
        new_image = None
        if not error:
            try:
                new_image = save_image(request.files.get("photo"))
            except ValueError as e:
                error = str(e)
        if error:
            flash(error, "error")
        else:
            image = crop["image"]
            if new_image:
                remove_image(image)
                image = new_image
            elif request.form.get("remove_photo"):
                remove_image(image)
                image = None
            db = get_db()
            db.execute("UPDATE crops SET name=?, category=?, price=?, unit=?, quantity=?, image=?, "
                       "updated=CURRENT_TIMESTAMP WHERE id=?", (*data, image, crop_id))
            db.commit()
            flash("Crop updated.", "ok")
            return redirect(url_for("my_crops"))
    return render_template("crop_form.html", crop=crop, categories=CATEGORIES, units=UNITS)


@app.route("/crop/<int:crop_id>/toggle", methods=["POST"])
@login_required
def toggle_crop(crop_id):
    if own_crop(crop_id):
        db = get_db()
        db.execute("UPDATE crops SET available = 1 - available, updated=CURRENT_TIMESTAMP WHERE id=?", (crop_id,))
        db.commit()
    return redirect(url_for("my_crops"))


@app.route("/crop/<int:crop_id>/delete", methods=["POST"])
@login_required
def delete_crop(crop_id):
    crop = own_crop(crop_id)
    if crop:
        remove_image(crop["image"])
        db = get_db()
        db.execute("DELETE FROM crops WHERE id=?", (crop_id,))
        db.commit()
        flash("Crop deleted.", "ok")
    return redirect(url_for("my_crops"))


@app.route("/buyers")
@login_required
def buyers():
    f = current_farmer()
    try:
        radius = int(request.args.get("radius", 50))
    except ValueError:
        radius = 50
    crop = request.args.get("crop", "").strip()
    my_crops_ = {c["name"].lower() for c in get_db().execute("SELECT name FROM crops WHERE farmer_id=?", (f["id"],))}
    return render_template("buyers.html", f=f, buyers=nearby_buyers(f, radius or None, crop), radius=radius,
                           crop=crop, my_crops=my_crops_, kinds=BUYER_KINDS, towns=sorted(TOWNS),
                           crop_names=sorted(c.title() for c in MARKET))


@app.route("/buyers/add", methods=["POST"])
@login_required
def add_buyer():
    name = request.form.get("name", "").strip()
    kind = request.form.get("kind", "Retailer")
    town = request.form.get("town", "")
    phone = request.form.get("phone", "").strip()
    buys = ",".join(x.strip().title() for x in request.form.get("buys", "").split(",") if x.strip())
    if name and town in TOWNS and kind in BUYER_KINDS and phone.isdigit() and len(phone) == 10 and buys:
        db = get_db()
        db.execute("INSERT INTO buyers (name, kind, town, phone, buys, lat, lon) VALUES (?,?,?,?,?,?,?)",
                   (name, kind, town, phone, buys, *TOWNS[town]))
        db.commit()
        flash("Buyer added.", "ok")
    else:
        flash("Fill every field. Phone must be 10 digits.", "error")
    return redirect(url_for("buyers"))


@app.route("/advisor")
@login_required
def advisor():
    crops = get_db().execute("SELECT name FROM crops WHERE farmer_id=?", (session["farmer_id"],)).fetchall()
    chips = [f"Should I sell my {c['name']} now?" for c in crops[:2]]
    if crops:
        chips.append(f"How do I store {crops[0]['name']}?")
    chips += ["Which buyers are near me?", "Best season to grow ragi?"]
    return render_template("advisor.html", chips=chips, ai_on=bool(os.environ.get("ANTHROPIC_API_KEY")))


@app.route("/api/advisor", methods=["POST"])
@login_required
def api_advisor():
    question = (request.get_json(silent=True) or {}).get("question", "").strip()[:500]
    if not question:
        return jsonify({"reply": "Please type a question."})
    f = current_farmer()
    crops = get_db().execute("SELECT * FROM crops WHERE farmer_id=?", (f["id"],)).fetchall()
    reply = ask_llm(question, f, crops) or rule_based_advice(question, f, crops)
    return jsonify({"reply": reply})


# ================================================================ start
def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


# Initialize DB on startup (works both for direct run and gunicorn)
with app.app_context():
    init_db()

if __name__ == "__main__":
    port = 5000
    print("\n==============================================")
    print(" Farmer Market v2 is running!")
    print(f" On this laptop : http://localhost:{port}")
    print(f" On your phone  : http://{local_ip()}:{port}   (same Wi-Fi)")
    print(" Demo farmer login: phone 9999999999 / password demo123")
    print(" Press CTRL+C to stop")
    print("==============================================\n")
    app.run(host="0.0.0.0", port=port, debug=False)
