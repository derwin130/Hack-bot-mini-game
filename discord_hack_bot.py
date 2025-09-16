import os
import random
import asyncio
import time
from collections import deque
import discord
from discord.ext import commands

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="\\", intents=intents, help_command=None, case_insensitive=True)

# --- Sessions (per user) ---
active_sessions = {}

# Simple per-user cooldown to prevent start spam
LAST_SHELL_START = {}
START_COOLDOWN_SEC = 5  # user must wait this many seconds between starting hacks

# --- Global active-word lock: only 1 puzzle per word at a time ---
ACTIVE_WORDS = set()

# --- Word pools (Star Citizen themed, single-token only) ---
# Easier: short/common ships, places, gameplay nouns (100 items)
EASY_WORDS = [
    # 1-25
    "aurora","mustang","avenger","cutlass","gladius","sabre","hornet","talon","hawk","corsair",
    "nomad","titan","pisces","vulture","mule","argo","aegis","anvil","origin","drake",
    "misc","rsi","crusader","tumbril","greycat",
    # 26-50
    "arccorp","hurston","lorville","orison","grimhex","yela","daymar","cellin","lyria","wala",
    "calliope","clio","euterpe","arial","aberdeen","magda","ita","stanton","terra","pyro",
    "salvage","mining","cargo","bunker","outpost",
    # 51-75
    "hangar","quantum","jump","mobiglas","comms","tressler","baijini","everus","olisar","refinery",
    "scrap","racing","cave","beacon","patrol","escort","skimmer","shubin","kiosk","trade",
    "courier","runner","mercury","msr","carrack",
    # 76-100
    "constellation","freelancer","prospector","mole","hercules","valkyrie","arrow","prowler","reclaimer","buccaneer",
    "scorpius","phoenix","aquila","taurus","andromeda","apollo","polaris","perseus","nautilus","liberator",
    "kraken","javelin","idris","hammerhead","eclipse",
]

# Harder: longer names/places/systems but still “friendly” (100 items)
HARD_WORDS = [
    # 1-25
    "caterpillar","starfarer","retaliator","harbinger","glaive","starlifter","genesis","pioneer",
    "endeavor","idris","hammerhead","scorpius","microtech","newbabbage","area18","lorville","platform","baijinipoint",
    "porttressler","grimhex","portolisar","refinery","hurston","ursa",
    # 26-50
    "crusader","mining","covalex","terminal","office","banshee","kareah","jumptown","outpost",
    "hydroponic","scrapyard","blacksite","datavault","commarray","quantumtravel","beacon","commlink","signal","harvest",
    "cavern","armistice","interdiction","contraband","newdeal",
    # 51-75
    "teasa","astroarmada","cubbyblast","dumpersdepot","apex","orison","lorville","clouds",
    "icefield","glacier","gravlev","quantumdrive","generator","powerplant","cooler","hardpoint","marker","waypoint",
    "overclock","underclock","firmware","trace","infiltration",
    # 76-100
    "exfiltration","decryption","encryption","synchronization","configuration","virtualization","fragmentation","exploitation","reconnaissance",
    "surveillance","transponder","starchart","protocols","failsafe","tracker","satnetwork","voidspace","starlancer","ironclad","starforge","overwatch",
]

# Ensure exactly 100 each (pad with safe placeholders if needed)
def _pad_to(words, n, pad_token):
    if len(words) >= n:
        return words[:n]
    extra = [f"{pad_token}{i}" for i in range(1, n - len(words) + 1)]
    return words + extra

EASY_WORDS = _pad_to(EASY_WORDS, 100, "easyfill")
HARD_WORDS = _pad_to(HARD_WORDS, 100, "hardfill")

# --- No-repeat shuffled queues ---
def _make_queue(words):
    return deque(random.sample(words, len(words)))

EASY_QUEUE = _make_queue(EASY_WORDS)
HARD_QUEUE = _make_queue(HARD_WORDS)

def _next_available(queue, full_list):
    """Pop until we find a word not currently active. If all are active, return None."""
    if not queue:
        # reshuffle a fresh rotation
        queue.extend(random.sample(full_list, len(full_list)))
    tried = 0
    total = len(queue)
    while tried < total:
        w = queue.popleft()
        if w not in ACTIVE_WORDS:
            return w
        queue.append(w)
        tried += 1
    return None  # all locked

def next_easy():
    return _next_available(EASY_QUEUE, EASY_WORDS)

def next_hard():
    return _next_available(HARD_QUEUE, HARD_WORDS)

# --- Timers (swapped per your change) ---
EASY_TIME = 90     # 1.5 minutes
HARD_TIME = 180    # 3 minutes

# --- Optional LLM (OpenAI) ---
try:
    from openai import OpenAI
    OPENAI_OK = True
except Exception:
    OPENAI_OK = False

_ai_client = None
SYSTEM_PROMPT = (
    "You are 'Subnet', a terse in-universe Star Citizen systems ops AI. "
    "Tone: mission control / ops officer on a comm-relay. "
    "Use lore-friendly terms (UEE, Advocacy, Stanton, Crusader, microTech, Hurston, quantum, mobiGlas, ATC, comm-relay). "
    "Be brief (1–2 short sentences). Never reveal puzzle answers. No out-of-character chatter."
)

def have_openai():
    return OPENAI_OK and bool(os.getenv("OPENAI_API_KEY"))

def get_ai_client():
    global _ai_client
    if _ai_client is None:
        _ai_client = OpenAI()
    return _ai_client

async def ai_say_subnet(prompt_text: str) -> str:
    """Subnet replies in SC RP voice. Uses Responses API first, falls back to Chat Completions."""
    if not have_openai():
        return "🛰️ [Subnet AI link offline]"
    client = get_ai_client()

    # Try Responses API
    try:
        resp = client.responses.create(
            model="gpt-4o-mini",
            instructions=SYSTEM_PROMPT,
            input=prompt_text,
            max_output_tokens=80,
        )
        text = getattr(resp, "output_text", "") or ""
        text = text.strip()
        if text:
            print("[Subnet/Responses] ->", text)
            return text
    except Exception as e:
        print("[Subnet/Responses ERROR]", e)

    # Fallback to Chat Completions
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt_text},
            ],
            max_completion_tokens=80,
        )
        content = ""
        if resp and getattr(resp, "choices", None):
            msg = resp.choices[0].message if len(resp.choices) > 0 else None
            if msg and getattr(msg, "content", None):
                content = (msg.content or "").strip()
        if content:
            print("[Subnet/ChatCompletions] ->", content)
            return content
    except Exception as e:
        print("[Subnet/ChatCompletions ERROR]", e)

    return "🛰️ Subnet online. (No telemetry returned from relay.)"

async def ai_hint_sc(scramble: str, attempts_left: int) -> str:
    if not have_openai():
        return ""
    prompt = (
        "Provide a single-sentence, non-spoiler hint to help a pilot unscramble a word. "
        f"Scramble: {scramble}. Attempts left: {attempts_left}. "
        "Do NOT reveal the answer. Voice: Subnet, SC ops AI."
    )
    return await ai_say_subnet(prompt)

# --- Utility helpers ---
def scramble_word(word: str) -> str:
    """Shuffle letters, ensuring >1 letter moves positions for a non-trivial scramble."""
    letters = list(word)
    for _ in range(20):
        random.shuffle(letters)
        mixed = "".join(letters)
        if mixed != word:
            diffs = sum(1 for a, b in zip(mixed, word) if a != b)
            if diffs >= min(2, len(word)):
                return mixed
    return "".join(letters) if "".join(letters) != word else word[::-1]

async def cancel_timer(task):
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

async def timeout_watcher(ctx, user_id):
    """Checks per-user hack deadline every second; times out when now >= deadline."""
    while True:
        await asyncio.sleep(1)
        session = active_sessions.get(user_id)
        if not session or not session.get("scramble"):
            return
        deadline = session.get("deadline")
        if not deadline:
            return
        if time.monotonic() >= deadline:
            await end_current_hack(ctx, user_id, timed_out=True)
            return

def requester_line(ctx, session):
    alias = session.get("alias")
    if alias:
        return f"👤 Requested by {ctx.author.mention} — alias `{alias}`"
    return f"👤 Requested by {ctx.author.mention}"

async def end_current_hack(ctx, user_id, timed_out=False, failed=False, success=False):
    """
    Ends the current hack attempt. On fail or timeout, reveals the answer.
    Manual abort via \shell End does NOT reveal the answer.
    """
    session = active_sessions.get(user_id)
    if not session:
        return

    revealed_answer = session.get("answer")
    difficulty = session.get("difficulty")
    started_at = session.get("started_at")
    answer_word = session.get("answer")

    # stop task and CLEAR all session fields (include perk/timer stuff)
    await cancel_timer(session.get("task"))

    # release the active word lock
    if answer_word in ACTIVE_WORDS:
        ACTIVE_WORDS.discard(answer_word)

    session.update({
        "scramble": None, "answer": None, "tries": 0, "task": None,
        "difficulty": None, "started_at": None,
        "perk_limit": 1, "perks_used": 0, "revealed_indices": set(), "deadline": None
    })

    if success:
        await ctx.send("✅ **Hack successful — access granted** // ATC uplink synced. Clearance updated on mobiGlas.")
        elapsed_sec = None
        if started_at is not None:
            elapsed_sec = max(0.0, time.monotonic() - started_at)

        levels = bot.get_cog("LevelsCog")
        if levels:
            fallback = EASY_TIME if difficulty == "easy" else HARD_TIME
            duration = elapsed_sec if (elapsed_sec is not None) else float(fallback)
            state, applied, leveled, note = await levels.record_hack_success(
                ctx.author,
                difficulty=difficulty or "easy",
                duration_sec=float(duration)
            )
            if applied > 0:
                await ctx.send(f"🎖️ {ctx.author.mention} earned **{applied} XP**. (Level {state.level}) {note}")
            if leveled:
                await ctx.send(f"📡 Rank Unlocked: **Level {state.level}**!")
    elif timed_out:
        msg = "⏳ **Hack timed out — access denied** // Comms window closed."
        if revealed_answer:
            msg += f"\n🧩 **Answer revealed:** `{revealed_answer}`"
        await ctx.send(msg)
    elif failed:
        msg = "❌ **Hack failed — access denied** // ICE tripped."
        if revealed_answer:
            msg += f"\n🧩 **Answer revealed:** `{revealed_answer}`"
        await ctx.send(msg)

async def end_full_session(channel, user_id, alias_text="Session terminated"):
    session = active_sessions.pop(user_id, None)
    if session:
        await cancel_timer(session.get("task"))
        # release lock if any
        if session.get("answer") in ACTIVE_WORDS:
            ACTIVE_WORDS.discard(session.get("answer"))
    await channel.send(f"⚡ {alias_text}")

# --- Events ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (discord.py {discord.__version__})")
    try:
        await bot.load_extension("levels_cog")
        print("📡 LevelsCog loaded")
    except Exception as e:
        print("❌ Failed to load LevelsCog:", e)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    content = message.content.strip()
    if not content.startswith("\\"):
        await bot.process_commands(message)
        return
    stripped = content.lstrip("\\").strip()
    parts = stripped.split()
    if len(parts) >= 2:
        alias, key = parts[0], parts[1].lower()
        if key == "online":
            active_sessions[message.author.id] = {
                "alias": alias, "scramble": None, "answer": None,
                "tries": 0, "task": None, "difficulty": None, "started_at": None,
                "perk_limit": 1, "perks_used": 0, "revealed_indices": set(), "deadline": None
            }
            await message.channel.send(f"💻 {alias} logged in. Use `\\shell 01` or `\\shell 02`.")

            levels = bot.get_cog("LevelsCog")
            if levels:
                state, applied, leveled = await levels.record_online(message.author)
                if applied > 0:
                    await message.channel.send(f"🎖️ Daily login bonus: +{applied} XP (Level {state.level})")
                if leveled:
                    await message.channel.send(f"📡 Rank Unlocked: **Level {state.level}**!")
            return

        if key == "offline":
            await end_full_session(message.channel, message.author.id, "Session terminated")
            return
    await bot.process_commands(message)

# --- Commands ---
@bot.command(name="shell")
async def shell_cmd(ctx: commands.Context, *, arg: str = None):
    user_id = ctx.author.id
    session = active_sessions.get(user_id)
    if not session:
        await ctx.send("⚠️ You must be online first.")
        return
    if not arg:
        await ctx.send("⚠️ Usage: `\\shell 01`, `\\shell 02`, or `\\shell End`")
        return

    # Start-cooldown (anti-spam)
    now = time.monotonic()
    last = LAST_SHELL_START.get(user_id, 0)
    if now - last < START_COOLDOWN_SEC:
        await ctx.send(f"⏳ Please wait {int(START_COOLDOWN_SEC - (now - last))}s before starting another hack.")
        return
    LAST_SHELL_START[user_id] = now

    key = arg.strip().lower()
    if key == "01":
        word = next_easy()
        if word is None:
            return await ctx.send("⚠️ All EASY puzzles are currently in use. Try again in a moment.")
        scramble = scramble_word(word)
        await cancel_timer(session.get("task"))

        # set perk limit based on current level (L4 gets 2; others 1)
        level = await get_user_level(ctx.author)
        perk_limit = 2 if level >= 4 else 1

        session.update({
            "scramble": scramble, "answer": word, "tries": 3, "difficulty": "easy",
            "started_at": time.monotonic(),
            "perk_limit": perk_limit, "perks_used": 0, "revealed_indices": set(),
            "deadline": time.monotonic() + EASY_TIME
        })
        ACTIVE_WORDS.add(word)
        session["task"] = asyncio.create_task(timeout_watcher(ctx, user_id))
        await ctx.send(
            f"💻 **RCE (EASY)**\n{requester_line(ctx, session)}\n"
            f"🔐 Unscramble: `{scramble}`\n⏳ 90 seconds\n⚡ `\\RCE <answer>`"
        )

    elif key == "02":
        word = next_hard()
        if word is None:
            return await ctx.send("⚠️ All HARD puzzles are currently in use. Try again in a moment.")
        scramble = scramble_word(word)
        await cancel_timer(session.get("task"))

        level = await get_user_level(ctx.author)
        perk_limit = 2 if level >= 4 else 1

        session.update({
            "scramble": scramble, "answer": word, "tries": 3, "difficulty": "hard",
            "started_at": time.monotonic(),
            "perk_limit": perk_limit, "perks_used": 0, "revealed_indices": set(),
            "deadline": time.monotonic() + HARD_TIME
        })
        ACTIVE_WORDS.add(word)
        session["task"] = asyncio.create_task(timeout_watcher(ctx, user_id))
        await ctx.send(
            f"💻 **RCE (HARD)**\n{requester_line(ctx, session)}\n"
            f"🔐 Unscramble: `{scramble}`\n⏳ 3 minutes\n⚡ `\\RCE <answer>`"
        )

    elif key == "end":
        if session.get("scramble"):
            await end_current_hack(ctx, user_id)  # manual abort, no reveal
            await ctx.send("🛑 RCE aborted.")
        else:
            await ctx.send("⚠️ No active hack.")
    else:
        await ctx.send("⚠️ Unknown option.")

@bot.command(name="RCE")
async def rce_cmd(ctx: commands.Context, *, answer: str = None):
    user_id = ctx.author.id
    session = active_sessions.get(user_id)
    if not session:
        await ctx.send("⚠️ No active session.")
        return
    if not session.get("scramble"):
        await ctx.send("⚠️ No active hack.")
        return
    if not answer:
        await ctx.send("⚠️ Usage: `\\RCE <answer>`")
        return

    if answer.strip().lower() == (session["answer"] or "").lower():
        await end_current_hack(ctx, user_id, success=True)
    else:
        session["tries"] -= 1
        if session["tries"] > 0:
            hint = await ai_hint_sc(session["scramble"], session["tries"])
            await ctx.send(f"❌ Wrong. Attempts left: {session['tries']}\n💡 {hint or ''}")
        else:
            await end_current_hack(ctx, user_id, failed=True)

@bot.command(name="clear")
async def clear_cmd(ctx: commands.Context, *, arg: str = None):
    if arg != "terminal":
        await ctx.send("⚠️ Usage: `\\clear terminal`")
        return
    if ctx.guild and not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        await ctx.send("❌ Need Manage Messages permission.")
        return
    deleted = await ctx.channel.purge(limit=100, check=lambda m: not m.pinned)
    await ctx.send(f"🧹 Cleared {len(deleted)} messages.", delete_after=5)

@bot.command(name="subnet")
async def subnet_cmd(ctx, *, message: str = None):
    if not message:
        await ctx.send("⚠️ Usage: `\\subnet <message>`")
        return
    line = await ai_say_subnet(message)
    if not line.strip():
        line = "🛰️ Subnet link active. (No content received.)"
    await ctx.send(line)

# ---------- Perk helpers & commands ----------

async def get_user_level(member: discord.Member) -> int:
    """Returns the user's current level (0-4) using LevelsCog; falls back to 0 on error."""
    levels = bot.get_cog("LevelsCog")
    if not levels:
        return 0
    try:
        state = await levels.store.get_or_create_user(member.id, member.guild.id)
        return int(state.level)
    except Exception:
        return 0

def _ensure_active(ctx):
    user_id = ctx.author.id
    session = active_sessions.get(user_id)
    if not session:
        return None, "⚠️ No active session."
    if not session.get("scramble"):
        return None, "⚠️ No active hack."
    return session, None

def _perks_remaining(session):
    limit = int(session.get("perk_limit", 1))
    used = int(session.get("perks_used", 0))
    return max(0, limit - used)

async def _mark_perk_used(ctx, session, note: str):
    session["perks_used"] = int(session.get("perks_used", 0)) + 1
    line = await ai_say_subnet(note) if have_openai() else ""
    await ctx.send(f"{line or '🛰️ [Subnet]'}")

# ---- Perk gating helpers (p3 daily, p4 XP penalty) ----
P4_FAIL_XP_PENALTY = 5  # change if you want a different penalty

async def _levels_or_zero():
    return bot.get_cog("LevelsCog")

async def _p3_allowed(member: discord.Member):
    """Check daily usage for p3 using LevelsCog store."""
    levels = await _levels_or_zero()
    if not levels or not hasattr(levels, "perk_can_use_p3"):
        return True, 0
    return await levels.perk_can_use_p3(member)

async def _p3_mark_used(member: discord.Member):
    levels = await _levels_or_zero()
    if levels and hasattr(levels, "perk_mark_p3_used"):
        await levels.perk_mark_p3_used(member)

async def _apply_xp_delta(member: discord.Member, delta: int, note: str = ""):
    """Add (or subtract) XP via LevelsCog."""
    levels = await _levels_or_zero()
    if not levels or not hasattr(levels, "add_xp_delta"):
        return None
    try:
        state = await levels.add_xp_delta(member, delta, note=note)
        return state
    except Exception:
        return None

@bot.command(name="p1")
async def perk_reveal(ctx: commands.Context):
    session, err = _ensure_active(ctx)
    if err: return await ctx.send(err)
    if _perks_remaining(session) <= 0:
        return await ctx.send("⚡ No perks remaining for this hack.")
    # Level check (level 1+)
    level = await get_user_level(ctx.author)
    if level < 1:
        return await ctx.send("🔒 Perk locked. Reach **Level 1** to use `\\p1`.")
    # Reveal 2 distinct indices
    answer = session["answer"]
    n = len(answer)
    idxs = set(session.get("revealed_indices", set()))
    choices = [i for i in range(n) if i not in idxs]
    if len(choices) == 0:
        return await ctx.send("ℹ️ Nothing to reveal.")
    pick_count = 2 if len(choices) >= 2 else 1
    pick = random.sample(choices, k=pick_count)
    idxs.update(pick)
    session["revealed_indices"] = idxs
    # Build masked hint
    hint = "".join(ch if i in idxs else "•" for i, ch in enumerate(answer))
    await _mark_perk_used(ctx, session, "Releasing partial cipher. Keep pressure on the node.")
    await ctx.send(f"🧩 **Reveal** → `{hint}`")

@bot.command(name="p2")
async def perk_pause(ctx: commands.Context):
    session, err = _ensure_active(ctx)
    if err: return await ctx.send(err)
    if _perks_remaining(session) <= 0:
        return await ctx.send("⚡ No perks remaining for this hack.")
    level = await get_user_level(ctx.author)
    if level < 2:
        return await ctx.send("🔒 Perk locked. Reach **Level 2** to use `\\p2`.")
    # Extend deadline by 10s
    dl = session.get("deadline")
    if not dl:
        return await ctx.send("ℹ️ No active timer.")
    session["deadline"] = dl + 10.0
    await _mark_perk_used(ctx, session, "Holding the gate. Window extended ten seconds.")
    await ctx.send("⏱️ **Stall** → +10s added to the clock.")

@bot.command(name="p3")
async def perk_skip(ctx: commands.Context):
    session, err = _ensure_active(ctx)
    if err: return await ctx.send(err)
    if _perks_remaining(session) <= 0:
        return await ctx.send("⚡ No perks remaining for this hack.")
    level = await get_user_level(ctx.author)
    if level < 3:
        return await ctx.send("🔒 Perk locked. Reach **Level 3** to use `\\p3`.")

    allowed, seconds_left = await _p3_allowed(ctx.author)
    if not allowed:
        mins = int(seconds_left // 60)
        secs = int(seconds_left % 60)
        return await ctx.send(f"⏳ `\\p3` on cooldown. Try again in **{mins}m {secs}s**.")

    await _mark_perk_used(ctx, session, "Bypass injected. ATC uplink green.")
    await _p3_mark_used(ctx.author)
    await end_current_hack(ctx, ctx.author.id, success=True)

@bot.command(name="p4")
async def perk_autosolve(ctx: commands.Context):
    session, err = _ensure_active(ctx)
    if err: return await ctx.send(err)
    if _perks_remaining(session) <= 0:
        return await ctx.send("⚡ No perks remaining for this hack.")
    level = await get_user_level(ctx.author)
    if level < 4:
        return await ctx.send("🔒 Perk locked. Reach **Level 4** to use `\\p4`.")
    # Chance formula: base 30% + 10% * level; capped at 70%
    chance = min(0.30 + 0.10 * level, 0.70)
    roll = random.random()
    await ctx.send("🎲 Running exploit…")
    if roll <= chance:
        await _mark_perk_used(ctx, session, "Exploit latched. Solved.")
        await end_current_hack(ctx, ctx.author.id, success=True)
    else:
        # consume a perk even on fail, and apply XP penalty
        session["perks_used"] = int(session.get("perks_used", 0)) + 1
        state = await _apply_xp_delta(ctx.author, -P4_FAIL_XP_PENALTY, note="Overclock failed")
        line = await ai_say_subnet("Exploit rejected. ICE held.") if have_openai() else ""
        tail = f"\n🩹 **Penalty:** –{P4_FAIL_XP_PENALTY} XP" if state is not None else ""
        await ctx.send(f"{line or '🛰️ [Subnet]'}\n❗ **Overclock failed.** Keep trying.{tail}")

# --- Run Bot ---
if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("❌ ERROR: DISCORD_TOKEN not set.")
        raise SystemExit(1)
    bot.run(token)
