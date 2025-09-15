import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Tuple, Dict

import aiosqlite
import discord
from discord.ext import commands

# =========================
# CONFIG
# =========================
DB_PATH = "levels.sqlite3"

# Level thresholds (0 → 4)
LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000]
MAX_LEVEL = 4

# XP awards
BASE_HACK_XP = 50
# Only two difficulties now
DIFFICULTY_BONUS = {"easy": 0, "hard": 50}
FIRST_SUCCESS_DAILY_BONUS = 25
FAILURE_XP = 5  # Optional tiny learning XP
DAILY_LOGIN_BONUS = 5

# Anti-abuse
MIN_PUZZLE_TIME_SEC = 6  # ignore completions faster than this
FULL_XP_HACKS_PER_HOUR = 5
REDUCED_XP_HACKS_PER_HOUR = 10
REDUCED_RATE = 0.2  # 20% XP after first 5 in an hour; after 10 -> 0 XP
DAILY_XP_CAP = 500

# Optional: map levels to role IDs per guild (you can fill at runtime)
ROLE_MAP_BY_GUILD: Dict[int, Dict[int, int]] = {}

# =========================
# DATA SHAPES
# =========================
@dataclass
class UserState:
    user_id: int
    guild_id: int
    level: int
    xp: int
    hacks_completed: int
    last_online_at: Optional[str]
    last_hack_at: Optional[str]
    streak_count: int
    last_daily_bonus_at: Optional[str]
    daily_xp_earned: int
    daily_reset_at: Optional[str]

# =========================
# UTIL
# =========================
def utc_now() -> dt.datetime:
    return dt.datetime.utcnow().replace(tzinfo=dt.timezone.utc)

def to_date_str(ts: dt.datetime) -> str:
    return ts.date().isoformat()

def level_for_xp(xp: int) -> int:
    lvl = 0
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            lvl = i
    return min(lvl, MAX_LEVEL)

def next_threshold(level: int) -> Optional[int]:
    if level >= MAX_LEVEL:
        return None
    return LEVEL_THRESHOLDS[level + 1]

async def fetchone_dict(cur) -> Optional[dict]:
    row = await cur.fetchone()
    if row is None:
        return None
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))

# =========================
# CORE STORAGE LAYER
# =========================
class LevelStore:
    def __init__(self, path: str):
        self.path = path
        self._lock = asyncio.Lock()

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS users(
              user_id INTEGER NOT NULL,
              guild_id INTEGER NOT NULL,
              level INTEGER NOT NULL DEFAULT 0,
              xp INTEGER NOT NULL DEFAULT 0,
              hacks_completed INTEGER NOT NULL DEFAULT 0,
              last_online_at TEXT,
              last_hack_at TEXT,
              streak_count INTEGER NOT NULL DEFAULT 0,
              last_daily_bonus_at TEXT,
              daily_xp_earned INTEGER NOT NULL DEFAULT 0,
              daily_reset_at TEXT,
              PRIMARY KEY(user_id, guild_id)
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS xp_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              guild_id INTEGER NOT NULL,
              amount INTEGER NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS hack_log(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              guild_id INTEGER NOT NULL,
              difficulty TEXT NOT NULL,
              duration_sec REAL NOT NULL,
              created_at TEXT NOT NULL
            )
            """)
            await db.commit()

    async def get_or_create_user(self, user_id: int, guild_id: int) -> UserState:
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT * FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            row = await fetchone_dict(cur); await cur.close()
            if row:
                return UserState(**row)
            await db.execute("""
            INSERT INTO users(user_id, guild_id, level, xp, hacks_completed,
                              last_online_at, last_hack_at, streak_count,
                              last_daily_bonus_at, daily_xp_earned, daily_reset_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """, (user_id, guild_id, 0, 0, 0, None, None, 0, None, 0, None))
            await db.commit()
            return UserState(user_id, guild_id, 0, 0, 0, None, None, 0, None, 0, None)

    async def _maybe_reset_daily(self, state: UserState, db):
        today = to_date_str(utc_now())
        if state.daily_reset_at != today:
            state.daily_reset_at = today
            state.daily_xp_earned = 0
            await db.execute("""
            UPDATE users SET daily_xp_earned=?, daily_reset_at=? 
            WHERE user_id=? AND guild_id=?
            """, (state.daily_xp_earned, state.daily_reset_at, state.user_id, state.guild_id))

    async def add_xp(self, user_id: int, guild_id: int, amount: int, reason: str) -> Tuple[UserState, int, bool]:
        """
        Returns: (updated_state, applied_amount, leveled_up_bool)
        Respects DAILY_XP_CAP.
        """
        async with self._lock:
            async with aiosqlite.connect(self.path) as db:
                cur = await db.execute("SELECT * FROM users WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                row = await fetchone_dict(cur); await cur.close()
                if not row:
                    state = await self.get_or_create_user(user_id, guild_id)
                else:
                    state = UserState(**row)

                await self._maybe_reset_daily(state, db)

                remaining_cap = max(0, DAILY_XP_CAP - state.daily_xp_earned)
                applied = max(0, min(amount, remaining_cap))
                if applied > 0:
                    new_xp = state.xp + applied
                    old_level = state.level
                    new_level = level_for_xp(new_xp)

                    state.xp = new_xp
                    state.level = new_level
                    state.daily_xp_earned += applied

                    await db.execute("""
                    UPDATE users SET xp=?, level=?, daily_xp_earned=? WHERE user_id=? AND guild_id=?
                    """, (state.xp, state.level, state.daily_xp_earned, user_id, guild_id))

                    await db.execute("""
                    INSERT INTO xp_log(user_id, guild_id, amount, reason, created_at)
                    VALUES(?,?,?,?,?)
                    """, (user_id, guild_id, applied, reason, utc_now().isoformat()))
                    leveled_up = new_level > old_level
                else:
                    leveled_up = False

                await db.commit()
                return state, applied, leveled_up

    async def log_hack(self, user_id: int, guild_id: int, difficulty: str, duration_sec: float):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
            INSERT INTO hack_log(user_id, guild_id, difficulty, duration_sec, created_at)
            VALUES(?,?,?,?,?)
            """, (user_id, guild_id, difficulty, float(duration_sec), utc_now().isoformat()))
            await db.commit()

    async def update_user_meta(self, user_id: int, guild_id: int, **fields):
        if not fields:
            return
        sets = ", ".join([f"{k}=?" for k in fields])
        values = list(fields.values()) + [user_id, guild_id]
        async with aiosqlite.connect(self.path) as db:
            await db.execute(f"UPDATE users SET {sets} WHERE user_id=? AND guild_id=?", values)
            await db.commit()

    async def top_users(self, guild_id: int, limit: int = 10):
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("""
            SELECT * FROM users WHERE guild_id=? ORDER BY level DESC, xp DESC LIMIT ?
            """, (guild_id, limit))
            rows = await cur.fetchall()
            cols = [c[0] for c in cur.description]
            await cur.close()
            return [dict(zip(cols, r)) for r in rows]

# =========================
# SERVICE (awards, rules)
# =========================
class LevelService:
    def __init__(self, store: LevelStore):
        self.store = store

    async def record_online(self, member: discord.Member) -> Tuple[UserState, int, bool]:
        """
        Apply daily login bonus at most once per day.
        """
        state = await self.store.get_or_create_user(member.id, member.guild.id)
        today = to_date_str(utc_now())
        applied = 0
        leveled = False
        if state.last_daily_bonus_at != today:
            state, applied, leveled = await self.store.add_xp(member.id, member.guild.id, DAILY_LOGIN_BONUS, "daily_login")
            await self.store.update_user_meta(member.id, member.guild.id,
                                              last_online_at=utc_now().isoformat(),
                                              last_daily_bonus_at=today)
        else:
            await self.store.update_user_meta(member.id, member.guild.id,
                                              last_online_at=utc_now().isoformat())
        return state, applied, leveled

    async def record_hack_success(self, member: discord.Member, difficulty: str = "easy",
                                  duration_sec: float = 10.0) -> Tuple[UserState, int, bool, str]:
        """
        Awards XP with difficulty bonuses, per-hour diminishing returns, and first-success-of-day bonus.
        Difficulty is 'easy' or 'hard' (fallback to 'easy').
        Returns: (state, applied_xp, leveled_up, note)
        """
        difficulty = (difficulty or "easy").lower()
        if difficulty not in DIFFICULTY_BONUS:
            difficulty = "easy"

        if duration_sec < MIN_PUZZLE_TIME_SEC:
            await self.store.log_hack(member.id, member.guild.id, difficulty, duration_sec)
            return await self.store.get_or_create_user(member.id, member.guild.id), 0, False, "Ignored: too fast"

        # Count hacks in the past hour for diminishing returns
        async with aiosqlite.connect(self.store.path) as db:
            one_hour_ago = (utc_now() - dt.timedelta(hours=1)).isoformat()
            cur = await db.execute("""
            SELECT COUNT(*) FROM hack_log 
            WHERE user_id=? AND guild_id=? AND created_at>=?
            """, (member.id, member.guild.id, one_hour_ago))
            count_in_hour = (await cur.fetchone())[0]
            await cur.close()

        base = BASE_HACK_XP + DIFFICULTY_BONUS[difficulty]
        multiplier = 1.0
        if count_in_hour >= FULL_XP_HACKS_PER_HOUR:
            if count_in_hour < REDUCED_XP_HACKS_PER_HOUR:
                multiplier = REDUCED_RATE
            else:
                multiplier = 0.0

        award = int(base * multiplier)

        # First success of the day bonus?
        async with aiosqlite.connect(self.store.path) as db:
            today = to_date_str(utc_now())
            cur = await db.execute("""
            SELECT COUNT(*) FROM xp_log 
            WHERE user_id=? AND guild_id=? AND reason='hack_success' AND created_at LIKE ?
            """, (member.id, member.guild.id, f"{today}%"))
            successes_today = (await cur.fetchone())[0]
            await cur.close()

        note_parts = []
        if multiplier == 0.0:
            note_parts.append("No XP (hourly limit reached)")
        elif multiplier == REDUCED_RATE:
            note_parts.append("Reduced XP (diminishing returns)")

        if successes_today == 0 and award > 0:
            award += FIRST_SUCCESS_DAILY_BONUS
            note_parts.append(f"+{FIRST_SUCCESS_DAILY_BONUS} daily bonus")

        await self.store.log_hack(member.id, member.guild.id, difficulty, duration_sec)
        state, applied, leveled = await self.store.add_xp(member.id, member.guild.id, award, "hack_success")

        await self.store.update_user_meta(member.id, member.guild.id,
                                          hacks_completed=state.hacks_completed + 1,
                                          last_hack_at=utc_now().isoformat())
        state = await self.store.get_or_create_user(member.id, member.guild.id)

        return state, applied, leveled, "; ".join(note_parts) if note_parts else "OK"

    async def record_hack_failure(self, member: discord.Member) -> Tuple[UserState, int, bool]:
        state, applied, leveled = await self.store.add_xp(member.id, member.guild.id, FAILURE_XP, "hack_failure")
        return state, applied, leveled

# =========================
# COG WITH COMMANDS
# =========================
class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = LevelStore(DB_PATH)
        self.svc = LevelService(self.store)
        self.ready = False
        self.bot.loop.create_task(self._init_once())

    async def _init_once(self):
        await self.store.init()
        self.ready = True

    # Public APIs you can call from other parts of your bot:
    async def record_online(self, member: discord.Member):
        return await self.svc.record_online(member)

    async def record_hack_success(self, member: discord.Member, difficulty: str = "easy", duration_sec: float = 10.0):
        return await self.svc.record_hack_success(member, difficulty, duration_sec)

    async def record_hack_failure(self, member: discord.Member):
        return await self.svc.record_hack_failure(member)

    async def _maybe_apply_role(self, member: discord.Member, new_level: int):
        guild_map = ROLE_MAP_BY_GUILD.get(member.guild.id, {})
        role_id = guild_map.get(new_level)
        if not role_id:
            return
        role = member.guild.get_role(role_id)
        if not role:
            return
        to_remove = [member.guild.get_role(rid) for lvl, rid in guild_map.items() if lvl != new_level]
        try:
            if to_remove:
                await member.remove_roles(*[r for r in to_remove if r in member.roles], reason="Level role update")
            await member.add_roles(role, reason="Level up role")
        except discord.Forbidden:
            pass

    async def _announce_level_up(self, member: discord.Member, new_level: int):
        try:
            await member.send(f"📡 Rank Unlocked: **Level {new_level}** — nice work, Operative.")
        except discord.Forbidden:
            pass

    @commands.hybrid_command(name="rank", description="Show your (or another user's) level and XP.")
    async def rank(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        if not member:
            member = ctx.author
        state = await self.store.get_or_create_user(member.id, ctx.guild.id)
        nt = next_threshold(state.level)
        xp_to_next = "MAX" if nt is None else max(0, nt - state.xp)
        emb = discord.Embed(title=f"{member.display_name} — Level {state.level}",
                            description=f"XP: **{state.xp}**  •  Next level: **{xp_to_next}**",
                            color=discord.Color.blue())
        emb.add_field(name="Hacks Completed", value=str(state.hacks_completed))
        if state.last_hack_at:
            emb.add_field(name="Last Hack", value=f"<t:{int(dt.datetime.fromisoformat(state.last_hack_at).timestamp())}:R>")
        if state.last_online_at:
            emb.add_field(name="Last Online", value=f"<t:{int(dt.datetime.fromisoformat(state.last_online_at).timestamp())}:R>")
        await ctx.reply(embed=emb, mention_author=False)

    @commands.hybrid_command(name="leaderboard", description="Top operatives by level and XP.")
    async def leaderboard(self, ctx: commands.Context):
        rows = await self.store.top_users(ctx.guild.id, limit=10)
        if not rows:
            return await self.reply("No data yet.")
        lines = []
        for i, r in enumerate(rows, 1):
            uid = r["user_id"]
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"User {uid}"
            lines.append(f"**{i}.** {name} — Level **{r['level']}** ({r['xp']} XP)")
        emb = discord.Embed(title=f"{ctx.guild.name} — Leaderboard", description="\n".join(lines), color=discord.Color.gold())
        await ctx.reply(embed=emb, mention_author=False)

    # ---- admin tools ----
    def _is_admin(self, ctx: commands.Context) -> bool:
        perms = getattr(ctx.author.guild_permissions, "administrator", False)
        return perms or (ctx.author.id == ctx.guild.owner_id)

    @commands.hybrid_group(name="xp", description="Admin: adjust XP")
    async def xp(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("Subcommands: add, set")

    @xp.command(name="add", description="Admin: add XP to a user")
    async def xp_add(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not self._is_admin(ctx):
            return await ctx.reply("You need admin to do that.")
        state, applied, leveled = await self.store.add_xp(member.id, ctx.guild.id, amount, "admin_add")
        await ctx.reply(f"Added **{applied} XP** to {member.display_name}. Now **{state.xp} XP**, Level **{state.level}**.")
        if leveled:
            await self._maybe_apply_role(member, state.level)
            await self._announce_level_up(member, state.level)

    @xp.command(name="set", description="Admin: set XP for a user")
    async def xp_set(self, ctx: commands.Context, member: discord.Member, amount: int):
        if not self._is_admin(ctx):
            return await ctx.reply("You need admin to do that.")
        new_level = level_for_xp(amount)
        await self.store.update_user_meta(member.id, ctx.guild.id, xp=amount, level=new_level)
        state = await self.store.get_or_create_user(member.id, ctx.guild.id)
        await ctx.reply(f"Set {member.display_name} to **{amount} XP**, Level **{state.level}**.")

    @commands.hybrid_group(name="level", description="Admin: adjust level")
    async def level_cmd(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("Subcommands: set")

    @level_cmd.command(name="set", description="Admin: set level for a user (0-4)")
    async def level_set(self, ctx: commands.Context, member: discord.Member, level: int):
        if not self._is_admin(ctx):
            return await self.reply("You need admin to do that.")
        level = max(0, min(MAX_LEVEL, level))
        xp = LEVEL_THRESHOLDS[level]
        await self.store.update_user_meta(member.id, ctx.guild.id, level=level, xp=xp)
        await ctx.reply(f"{member.display_name} set to Level **{level}** ({xp} XP).")
        await self._maybe_apply_role(member, level)

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelsCog(bot))
