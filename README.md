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


## 🧬 Perks (v1.2)

Levelled operatives can trigger **one perk per hack** using quick commands:

- `\p1 — Reveal`  
  Reveals **2 letters** of the answer at random positions.  
  *Subnet:* “Releasing partial cipher. Keep pressure on the node.”

- `\p2 — Stall`  
  Adds **+10 seconds** to the current hack’s timer (deadline extended).  
  *Subnet:* “Holding the gate. Window extended ten seconds.”

- `\p3 — Bypass`  
  **Instant success** (auto-completes the hack and awards XP) *Can only be used once per day  
  *Subnet:* “Bypass injected. ATC uplink green.”

- `\p4 — Overclock`  
  **Chance to auto-solve**. Success chance scales with level:  
  `chance = min(0.30 + 0.10 * level, 0.70)` → at Level 4 this is **60%**.  
  *Subnet:* “Spinning exploit… stand by.” → success/fail feedback shown.

> 🔒 Perk locks by level: `\p1` (Lvl 1+), `\p2` (Lvl 2+), `\p3` (Lvl 3+), `\p4` (Lvl 4).  
> ⚖️ Only **one perk** may be used per hack (even if `\p4` fails).



## 🗒️ Changelog

### 1.2
- Added perk system with quick commands: `\p1` (Reveal), `\p2` (Stall +10s), `\p3` (Bypass), `\p4` (Overclock chance).
- Implemented real deadline-based timers (enables pausing/extension).
- Subnet AI flavor lines for perk activations.
- Keeps no-repeat word queues, requester tagging, and XP integration from v1.0/1.1.

### 1.0
- Initial release: Star Citizen–themed word-scramble hacks, XP levels (0–4), rank/leaderboard, optional Subnet AI.

