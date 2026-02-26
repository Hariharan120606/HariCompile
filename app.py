"""
HariCompile - Flask Backend
Supports: Python, JavaScript, C/C++, Java, Go, Rust
Run:  pip install flask  →  python app.py  →  open http://localhost:5000
"""

import os, re, sys, subprocess, tempfile, shutil, time
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".")

# ── CORS ──────────────────────────────────────────────────
@app.after_request
def add_cors(r):
    r.headers["Access-Control-Allow-Origin"]  = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    r.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return r

@app.route("/api/run",    methods=["OPTIONS"])
@app.route("/api/status", methods=["OPTIONS"])
def options_handler(): return "", 204

TIMEOUT = 10

# ── FIND PYTHON ON WINDOWS ────────────────────────────────
def find_python():
    """
    On Windows, 'python3' often doesn't exist and 'python'
    may redirect to the Microsoft Store stub. Try in this order:
      1. py   (Python Launcher — most reliable on Windows)
      2. python3
      3. python  (verify it actually works, not the MS Store stub)
    """
    candidates = ["py", "python3", "python"]
    for cmd in candidates:
        if shutil.which(cmd):
            # Verify it actually runs (not the MS Store stub which exits 9009)
            try:
                r = subprocess.run(
                    [cmd, "--version"], capture_output=True,
                    text=True, timeout=5
                )
                if r.returncode == 0 and "Python" in (r.stdout + r.stderr):
                    return cmd
            except Exception:
                continue
    return sys.executable  # absolute fallback: same Python running this script

def cmd_exists(c): return shutil.which(c) is not None

PYTHON_CMD = find_python()

AVAILABLE = {
    "python":     PYTHON_CMD is not None,
    "javascript": cmd_exists("node"),
    "cpp":        cmd_exists("g++"),
    "java":       cmd_exists("javac") and cmd_exists("java"),
    "go":         cmd_exists("go"),
    "rust":       cmd_exists("rustc"),
}

print("\n── HariCompile Compiler Availability ──")
print(f"  Python command: {PYTHON_CMD}")
for lang, ok in AVAILABLE.items():
    print(f"  {'✓' if ok else '✗'} {lang}")
print("────────────────────────────────────────\n")


# ── SHORT TEMP DIR (avoids MinGW linker bugs on Windows) ──
def make_tmpdir():
    if os.name == "nt":
        base = r"C:\hc_tmp"
        os.makedirs(base, exist_ok=True)
        return tempfile.mkdtemp(dir=base, prefix="hc_")
    return tempfile.mkdtemp(prefix="haricompile_")


# ── SUBPROCESS HELPER ─────────────────────────────────────
def run_proc(cmd, stdin_data="", cwd=None):
    try:
        proc = subprocess.run(
            cmd, input=stdin_data, capture_output=True,
            text=True, timeout=TIMEOUT, cwd=cwd,
        )
        return {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Time limit exceeded ({TIMEOUT}s)", "returncode": -1}
    except Exception as e:
        return {"stdout": "", "stderr": str(e), "returncode": -1}


# ── /api/run ──────────────────────────────────────────────
@app.route("/api/run", methods=["POST"])
def api_run():
    data  = request.get_json(force=True)
    lang  = data.get("language", "").lower()
    code  = data.get("code", "")
    stdin = data.get("stdin", "")

    if lang not in AVAILABLE:
        return jsonify({"error": f"Unknown language: {lang}"}), 400
    if not AVAILABLE[lang]:
        return jsonify({"stdout": "", "stderr": f"'{lang}' is not installed on this server.",
                        "returncode": -1, "compile_error": ""})

    tmpdir = make_tmpdir()
    try:
        result = compile_and_run(lang, code, stdin, tmpdir)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return jsonify(result)


# ── C++ MULTI-FLAG FALLBACK (fixes ucrt64/MSYS2 WinMain error) ──
CPP_FLAG_SETS = [
    ["-std=c++17", "-O2", "-Wl,--subsystem,console"],
    ["-std=c++17", "-O2", "-Wl,-subsystem,console"],
    ["-std=c++17", "-O2", "-mconsole"],
    ["-std=c++17", "-O2"],
    ["-std=c++14"],
    [],
]

def compile_cpp(src, exe, cwd):
    last = None
    for flags in CPP_FLAG_SETS:
        r = run_proc(["g++", "-o", exe, src] + flags, cwd=cwd)
        if r["returncode"] == 0:
            return r
        last = r
    return last


# ── COMPILE + RUN ─────────────────────────────────────────
def compile_and_run(lang, code, stdin, tmpdir):
    t0 = time.time()

    if lang == "python":
        f = os.path.join(tmpdir, "main.py")
        open(f, "w", encoding="utf-8").write(code)
        r = run_proc([PYTHON_CMD, f], stdin_data=stdin, cwd=tmpdir)
        return make_result(r, time.time() - t0)

    elif lang == "javascript":
        f = os.path.join(tmpdir, "main.js")
        open(f, "w", encoding="utf-8").write(code)
        r = run_proc(["node", f], stdin_data=stdin, cwd=tmpdir)
        return make_result(r, time.time() - t0)

    elif lang == "cpp":
        src = os.path.join(tmpdir, "main.cpp")
        exe = os.path.join(tmpdir, "main.exe" if os.name == "nt" else "main")
        open(src, "w", encoding="utf-8").write(code)
        cr = compile_cpp(src, exe, tmpdir)
        if cr["returncode"] != 0:
            return error_result(cr, time.time() - t0)
        r = run_proc([exe], stdin_data=stdin, cwd=tmpdir)
        return make_result(r, time.time() - t0)

    elif lang == "java":
        cls = extract_java_classname(code) or "Main"
        src = os.path.join(tmpdir, f"{cls}.java")
        open(src, "w", encoding="utf-8").write(code)
        cr = run_proc(["javac", src], cwd=tmpdir)
        if cr["returncode"] != 0:
            return error_result(cr, time.time() - t0)
        r = run_proc(["java", "-cp", tmpdir, cls], stdin_data=stdin, cwd=tmpdir)
        return make_result(r, time.time() - t0)

    elif lang == "go":
        f = os.path.join(tmpdir, "main.go")
        open(f, "w", encoding="utf-8").write(code)
        r = run_proc(["go", "run", f], stdin_data=stdin, cwd=tmpdir)
        return make_result(r, time.time() - t0)

    elif lang == "rust":
        src = os.path.join(tmpdir, "main.rs")
        exe = os.path.join(tmpdir, "main.exe" if os.name == "nt" else "main")
        open(src, "w", encoding="utf-8").write(code)
        cr = run_proc(["rustc", "-o", exe, src], cwd=tmpdir)
        if cr["returncode"] != 0:
            return error_result(cr, time.time() - t0)
        r = run_proc([exe], stdin_data=stdin, cwd=tmpdir)
        return make_result(r, time.time() - t0)

    return {"stdout": "", "stderr": "Unsupported language", "returncode": -1, "time": 0}


def make_result(r, elapsed):
    return {"stdout": r["stdout"], "stderr": r["stderr"],
            "compile_error": "", "returncode": r["returncode"],
            "time": round(elapsed, 3)}

def error_result(r, elapsed):
    return {"stdout": "", "stderr": r["stderr"],
            "compile_error": r["stderr"], "returncode": r["returncode"],
            "time": round(elapsed, 3)}

def extract_java_classname(code):
    m = re.search(r'\bpublic\s+class\s+(\w+)', code)
    return m.group(1) if m else "Main"


# ── /api/status ───────────────────────────────────────────
@app.route("/api/status", methods=["GET"])
def api_status(): return jsonify(AVAILABLE)


# ── Serve frontend ────────────────────────────────────────
@app.route("/")
def index(): return send_from_directory(".", "compiler.html")


if __name__ == "__main__":
    print("🚀 HariCompile running at http://localhost:5000")
    app.run(debug=True, port=5000)
