
from flask import Flask, send_file, request, Response, render_template_string, redirect, url_for
import os, threading, time, random, json, zipfile
from datetime import datetime
import pyautogui
import math

CONFIG_FILE = "config.json"
DEFAULT_CONFIG = {
    "min_interval": 15,
    "max_interval": 30,
    "save_dir": "screenshots",
    "username": "admin",
    "password": "Okayynopass"
}

if not os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=4)

with open(CONFIG_FILE, "r") as f:
    config = json.load(f)

os.makedirs(config["save_dir"], exist_ok=True)

app = Flask(__name__)
running = False
thread = None
counter = 1

def take_screenshot():
    global counter
    date_folder = datetime.now().strftime("%Y-%m-%d")
    day_path = os.path.join(config["save_dir"], date_folder)
    os.makedirs(day_path, exist_ok=True)
    timestamp = datetime.now().strftime("%H-%M-%S")
    filename = f"{counter:04d}_{timestamp}.png"
    filepath = os.path.join(day_path, filename)
    pyautogui.screenshot().save(filepath)
    log(f"Saved: {filepath}")
    counter += 1

def screenshot_loop():
    while running:
        take_screenshot()
        interval = random.randint(config["min_interval"], config["max_interval"])
        time.sleep(interval)

def log(message):
    print(message)
    with open("server.log", "a") as log_file:
        log_file.write(f"[{datetime.now()}] {message}\n")

def check_auth(username, password):
    return username == config["username"] and password == config["password"]

def authenticate():
    return Response('Authentication required.', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    decorated.__name__ = f.__name__
    return decorated

def get_all_screenshots():
    """Return a list of screenshots sorted by date (newest first)."""
    files = []
    for root, _, filenames in os.walk(config["save_dir"]):
        for f in filenames:
            path = os.path.join(root, f)
            files.append((os.path.getmtime(path), path))
    files.sort(reverse=True)  # newest first
    return [f[1] for f in files]

def get_latest_file():
    files = get_all_screenshots()
    return files[0] if files else None

@app.route('/')
@requires_auth
def index():
    latest_img = get_latest_file()
    latest_url = url_for('latest_screenshot') if latest_img else None
    profiles = {
        "Fast": (5, 10),
        "Medium": (15, 30),
        "Slow": (60, 120)
    }
    return render_template_string("""
    <html>
    <head>
        <title>Screenshot Server</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f8f9fa; }
            h1 { color: #333; }
            .status { display: inline-block; width: 12px; height: 12px; border-radius: 50%; }
            .running { background: green; }
            .stopped { background: red; }
            .config, .form-box { margin: 10px 0; background: #fff; padding: 10px; border-radius: 5px; }
            a.button, button { display: inline-block; padding: 8px 15px; margin: 5px; 
                       background: #007BFF; color: white; border-radius: 5px; text-decoration: none; border: none; cursor: pointer; }
            a.button:hover, button:hover { background: #0056b3; }
            img { max-width: 200px; border: 1px solid #ccc; margin: 5px; }
            form { margin-top: 10px; }
        </style>
    </head>
    <body>
        <h1>📸 Screenshot Server</h1>
        <p>Status: <span class="status {{ 'running' if running else 'stopped' }}"></span>
            {{ "Running" if running else "Stopped" }}</p>

        <div class="config">
            <b>Min Interval:</b> {{ config.min_interval }}s |
            <b>Max Interval:</b> {{ config.max_interval }}s |
            <b>Save Dir:</b> {{ config.save_dir }} |
            <b>User:</b> {{ config.username }}
        </div>

        <!-- Start Form -->
        <div class="form-box">
            <form action="/start" method="post">
                <label>Profile:</label>
                <select name="profile" onchange="setProfile(this)">
                    <option value="">Custom</option>
                    {% for name, vals in profiles.items() %}
                    <option value="{{ name }}">{{ name }} ({{ vals[0] }}-{{ vals[1] }}s)</option>
                    {% endfor %}
                </select>
                <br><br>
                <label>Min Interval (seconds):</label>
                <input type="number" id="min_interval" name="min_interval" value="{{ config.min_interval }}" required>
                <label>Max Interval (seconds):</label>
                <input type="number" id="max_interval" name="max_interval" value="{{ config.max_interval }}" required>
                <br><br>
                <button type="submit">▶ Start</button>
            </form>
        </div>

        <!-- Stop Button -->
        <a href="/stop" class="button">⏹ Stop</a>
        <a href="/download" class="button">⬇ Download All</a>
        <a href="/gallery" class="button">🖼 Gallery</a>

        <!-- Change Credentials -->
        <div class="form-box">
            <h3>Change Credentials</h3>
            <form action="/update_credentials" method="post">
                <label>Username:</label>
                <input type="text" name="username" value="{{ config.username }}" required>
                <label>Password:</label>
                <input type="password" name="password" placeholder="New password" required>
                <button type="submit">Update</button>
            </form>
        </div>

        {% if latest_url %}
            <h3>Latest Screenshot:</h3>
            <img src="{{ latest_url }}" alt="Latest Screenshot">
        {% endif %}

        <script>
            const profiles = {{ profiles | tojson }};
            function setProfile(select) {
                let profile = select.value;
                if (profile && profiles[profile]) {
                    document.getElementById('min_interval').value = profiles[profile][0];
                    document.getElementById('max_interval').value = profiles[profile][1];
                }
            }
        </script>
    </body>
    </html>
    """, running=running, config=config, profiles=profiles)

@app.route('/start', methods=["POST"])
@requires_auth
def start_server():
    global running, thread, config
    try:
        config["min_interval"] = int(request.form.get("min_interval", config["min_interval"]))
        config["max_interval"] = int(request.form.get("max_interval", config["max_interval"]))
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except ValueError:
        pass

    if not running:
        running = True
        thread = threading.Thread(target=screenshot_loop, daemon=True)
        thread.start()
        log("Screenshot server started.")

    return redirect(url_for("index"))

@app.route('/stop')
@requires_auth
def stop_server():
    global running
    running = False
    log("Screenshot server stopped.")
    return redirect(url_for("index"))

@app.route('/latest')
@requires_auth
def latest_screenshot():
    latest_file = get_latest_file()
    if latest_file:
        return send_file(latest_file)
    return "No screenshots yet."

@app.route('/gallery')
@requires_auth
def gallery():
    page = int(request.args.get("page", 1))
    per_page = 10
    all_files = get_all_screenshots()
    total_pages = math.ceil(len(all_files) / per_page)
    files = all_files[(page - 1) * per_page: page * per_page]
    return render_template_string("""
    <html>
    <head>
        <title>Screenshot Gallery</title>
        <style>
            body { font-family: Arial; padding: 20px; background: #f8f9fa; }
            img { max-width: 200px; margin: 5px; border: 1px solid #ccc; }
            a.button { padding: 8px 15px; background: #007BFF; color: white; border-radius: 5px; text-decoration: none; margin: 5px; }
            a.button:hover { background: #0056b3; }
        </style>
    </head>
    <body>
        <h1>Gallery</h1>
        <a href="/" class="button">🏠 Home</a>
        <div>
            {% for file in files %}
                <a href="/view?path={{ file }}"><img src="/view?path={{ file }}"></a>
            {% endfor %}
        </div>
        <div>
            {% if page > 1 %}
                <a href="/gallery?page={{ page-1 }}" class="button">⬅ Prev</a>
            {% endif %}
            {% if page < total_pages %}
                <a href="/gallery?page={{ page+1 }}" class="button">Next ➡</a>
            {% endif %}
        </div>
    </body>
    </html>
    """, files=files, page=page, total_pages=total_pages)

@app.route('/view')
@requires_auth
def view_file():
    path = request.args.get("path")
    if path and os.path.exists(path):
        return send_file(path)
    return "File not found."

@app.route('/update_credentials', methods=["POST"])
@requires_auth
def update_credentials():
    global config
    config["username"] = request.form.get("username", config["username"])
    config["password"] = request.form.get("password", config["password"])
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
    log("Credentials updated.")
    return redirect(url_for("index"))

@app.route('/download')
@requires_auth
def download_all():
    zip_filename = "screenshots.zip"
    with zipfile.ZipFile(zip_filename, 'w') as z:
        for root, _, files in os.walk(config["save_dir"]):
            for f in files:
                z.write(os.path.join(root, f))
    return send_file(zip_filename, as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
