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


## 🧬 Perks (v1.3)

Perks add clutch tools during a hack. **Level 4 can use up to 2 perks per hack**; all other levels can use **1 perk per hack**.  
Use quick commands:

- `\p1 — Reveal`  
  Reveals **2 letters** of the answer at random positions.  
  *Subnet:* “Releasing partial cipher. Keep pressure on the node.”  
  *Unlock:* Level 1+

- `\p2 — Stall`  
  Adds **+10 seconds** to the current hack’s timer.  
  *Subnet:* “Holding the gate. Window extended ten seconds.”  
  *Unlock:* Level 2+

- `\p3 — Bypass` *(once per day per user)*  
  **Instant success** (awards XP as normal).  
  *Subnet:* “Bypass injected. ATC uplink green.”  
  *Unlock:* Level 3+ • **Daily limit**

- `\p4 — Overclock` *(risk vs reward)*  
  **Chance to auto-solve**. Chance = `min(30% + 10% × level, 70%)` (Level 4 ⇒ 60%).  
  **If it fails, you lose 5 XP.**  
  *Subnet:* “Spinning exploit… stand by.” → success/fail feedback shown  
  *Unlock:* Level 4+

> ⚖️ **Per-hack limit:** Level 0–3 → 1 perk; **Level 4 → 2 perks** (any mix; `\p3` still has daily cooldown).  
> 🔒 Only one active puzzle per word across the server (no duplicate live puzzles).



## 🗒️ Changelog

### 1.3
- **Global puzzle lock:** only one active puzzle per word across the server.
- **Perk limits:** Level 0–3 → 1 perk per hack; **Level 4 → 2 perks** per hack.
- **\p3 (Bypass):** now **once per day** per user.
- **\p4 (Overclock):** failure applies **–5 XP** penalty.
- Confirmed timer swap: Easy **90s**, Hard **180s**.
- Minor wording and balance tweaks.

### 1.2
- Added perk system with quick commands: `\p1` (Reveal), `\p2` (Stall +10s), `\p3` (Bypass), `\p4` (Overclock chance).
- Implemented deadline-based timers and Subnet flavor lines.

### 1.0
- Initial release: Star Citizen–themed word-scramble hacks, XP levels (0–4), rank/leaderboard, optional Subnet AI.

