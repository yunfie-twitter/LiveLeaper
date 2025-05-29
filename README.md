# LiveLeaper

**LiveLeaper** is a Python tool for easily downloading YouTube videos.  
It supports both a command line (CLI) version and a GUI version included as a sub-module.

---

## ✅ Features

- 🎬 **YouTube support** - supports downloading high quality videos (using `yt-dlp`)
- 🖥️ **CLI & GUI both support** - can be used even by people who are not good with terminal
- ⚡ **Fast and stable** - parses streaming URLs directly instead of official API
- 🪟 **Multi-OS support** - runs on Windows / macOS / Linux.

--- **Fast and stable** - parses streaming URLs directly instead of through official APIs

## 🖥️ System Requirements

- Python 3.8 or higher
- OS: Windows 10+ / macOS 10.14+ / Debian Linux (Ubuntu, etc.)

--- ##

## 📦 Installation instructions

```bash
# Clone the repository (including submodules)
git clone --recurse-submodules https://github.com/yunfie-twitter/LiveLeaper.git
cd LiveLeaper

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate # On Windows: venv\Scripts\activate

# Install necessary packages
pip install -r requirements.txt

```

## 🎛 Use the GUI version.
```bash
cd LiveLeaper-GUI
pip install -r requirements.txt
python main.py
```

## ⚙️ How to use the CLI version
```bash
python main.py [URL1 URL2 ...] [options].
```

Available options
Option Description
--audio Extract and save audio only (according to default configuration file)
--ext Specify output file extension (e.g. mp4, webm, mp3)
--output Specify destination directory (e.g., downloads)
--lang Specify language file (e.g. en, ja)
--info Get only video information without downloading

## 🤝 How to contribute
Pull Requests and Issues are welcome!
```bash
# Create a branch
git checkout -b feature/your-feature

# Edit code and commit
git commit -m “Add new feature”

# Push to create a PR
git push origin feature/your-feature
```

## [Sponsor this project By Ko-Fi](https://ko-fi.com/liveleaper).

