
cat > README.md << 'EOF'


# Discord Hack Bot

Star Citizen–themed mini-game bot built with Python and discord.py. Players log in with an alias, attempt easy or hard word-scramble hacks, and earn XP (levels 0–4). Features Subnet AI flavor text, anti-abuse protections, leaderboards, and persistent leveling via SQLite.

## Quick Start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_TOKEN="YOUR_TOKEN"
python discord_hack_bot.py
