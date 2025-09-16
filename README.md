# ⚡ Hack Bot Mini Game

A **Star Citizen–themed Discord mini-game** built with Python and [discord.py].  
Log in with your alias, dive into terminal-style hacking puzzles, earn XP, and climb from **Level 0 → Level 4** while immersing yourself in the Subnet AI comm-relay experience.

---

## ✨ Features

- 🎮 **Word-scramble hacks**  
  - `\shell 01` → Easy (90 seconds)  
  - `\shell 02` → Hard (3 minutes)  

- 🧩 **Randomized puzzle pools**  
  - 100+ Star Citizen–related words (ships, planets, moons, locales)  
  - Shuffled so repeats are rare  

- 🧠 **Subnet AI integration** *(optional)*  
  - Flavorful in-universe responses powered by GPT  
  - Lore-friendly comm-relay style  

- 🏅 **Leveling system (0–4)**  
  - Gain XP from successful hacks and daily logins  
  - Persistent progress stored in SQLite  

- 📊 **Leaderboards & Ranks**  
  - `\rank` → view your level & XP progress  
  - `\leaderboard` → see the top 10 hackers in your server  

- 🔧 **Admin controls**  
  - Manually adjust XP or levels for testing & events  

---

## 🖥️ Commands

```text
\YourAlias online     → Log in under an alias
\YourAlias offline    → End your session

\shell 01             → Start an EASY hack
\shell 02             → Start a HARD hack
\shell end            → Abort your current hack
\RCE <answer>         → Submit a guess

\rank                 → Check your level & XP
\leaderboard          → View server leaderboard

\clear terminal       → Clear last 100 messages
\subnet <msg>         → Chat with Subnet AI
