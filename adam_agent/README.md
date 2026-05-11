# ADAM (Autonomous-Direct-Access-Model)

A standalone, privacy-focused AI agent with voice-to-text, text-to-voice, dictation, request optimizer, and token usage indicator. Runs as a separate Flask web app.

## Features
- Voice-to-text and text-to-voice (Chrome/Edge)
- Dictation and memory (local)
- Request optimizer (reduce token usage)
- Token usage indicator
- Modular and easy to export/remove

## Quick Start
1. Open a terminal in this folder.
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the app:
   ```
   python app.py
   ```
4. Open your browser to http://localhost:5050

## Export/Remove
- To export: Copy the entire `adam_agent/` folder to any location.
- To remove: Delete the `adam_agent/` folder. No other files are affected.

## Add Features
- Edit `templates/dashboard.html` for UI changes.
- Add Python modules or logic in `app.py` or new files.
- Update `.agent.md` for persona/policy changes.

---
ADAM is fully independent and does not affect your main project.
