# HariCompile 🚀

A full-featured online compiler powered by a local Flask backend.

## Files
```
haricompile/
├── app.py           ← Flask backend (compiler server)
├── compiler.html    ← Frontend (open via Flask, not directly)
├── requirements.txt
└── README.md
```

## Setup & Run

### 1. Install Python dependencies
```bash
pip install flask
```

### 2. Install system compilers (if not already installed)

**Ubuntu/Debian:**
```bash
sudo apt install python3 nodejs g++ default-jdk golang rustc
```

**macOS (Homebrew):**
```bash
brew install node openjdk go rust
# g++ comes with Xcode Command Line Tools: xcode-select --install
```

**Windows:**
- Python: https://python.org
- Node.js: https://nodejs.org
- g++ (MinGW): https://winlibs.com
- Java JDK: https://adoptium.net
- Go: https://go.dev
- Rust: https://rustup.rs

### 3. Start the Flask server
```bash
python app.py
```

### 4. Open the compiler
Visit: **http://localhost:5000**

> ⚠️ Open via `http://localhost:5000`, NOT by double-clicking compiler.html,
> otherwise the browser will block API calls to Flask.

## Supported Languages
| Language   | Runtime     | Status       |
|------------|-------------|--------------|
| Python     | python3     | ✅ Always available |
| JavaScript | node        | ✅ Always available |
| C / C++    | g++         | ✅ Needs g++  |
| Java       | javac + java| ✅ Needs JDK  |
| Go         | go run      | ⚡ Needs Go   |
| Rust       | rustc       | ⚡ Needs Rust |

## API Endpoints
- `POST /api/run` — compile & run code
- `GET  /api/status` — check which languages are available
- `GET  /` — serves the frontend

## Request Format
```json
{
  "language": "python",
  "code": "print('Hello!')",
  "stdin": ""
}
```
