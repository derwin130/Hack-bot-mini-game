import asyncio
import time
from types import SimpleNamespace
from typing import Tuple, Optional, List
import aiosqlite
import discord
from discord.ext import commands

DB_PATH = "levels.sqlite3"

# XP thresholds → levels (0–4)
# tweak as you like
LEVEL_THRESHOLDS = [0, 50, 150, 300, 600]  # xp required to be >= this to reach that level index

DAILY_BONUS_XP = 10
DAILY_BONUS_COOLDOWN = 20 * 60 * 60  # 20 hours

# Hack success base XP
EASY_BASE_XP = 8
HARD_BASE_XP = 15

# Speed bonus caps
EASY_BEST_SECONDS = 25
HARD_BEST_SECONDS = 40
SPEED_BONUS_MAX = 10  # extra XP at best times

# Perk/cooldown
P3_COOLDOWN_SECONDS = 24 * 60 * 60  # once per day

class UserStore:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    async def init_tables(self):
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            xp INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 0,
            last_login_epoch REAL DEFAULT NULL,
            PRIMARY KEY (user_id, guild_id)
        )""")
        await self.db.execute("""
        CREATE TABLE IF NOT EXISTS perk_meta (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            last_p3_epoch REAL DEFAULT NULL,
            PRIMARY KEY (user_id, guild_id)
        )""")
        await self.db.commit()

    async def get_or_create_user(self, user_id: int, guild_id: int) -> SimpleNamespace:
        cur = await self.db.execute(
            "SELECT xp, level, last_login_epoch FROM users WHERE user_id=? AND guild_id=?",
            (int(user_id), int(guild_id))
        )
        row = await cur.fetchone()
        await cur.close()
        if row:
            xp, level, last_login = row
            return SimpleNamespace(user_id=user_id, guild_id=guild_id, xp=int(xp), level=int(level), last_login_epoch=last_login)
        await self.db.execute(
            "INSERT INTO users (user_id, guild_id, xp, level, last_login_epoch) VALUES (?,?,?,?,?)",
            (int(user_id), int(guild_id), 0, 0, None)
        )
        await self.db.commit()
        return SimpleNamespace(user_id=user_id, guild_id=guild_id, xp=0, level=0, last_login_epoch=None)

    async def update_user(self, user_id: int, guild_id: int, *, xp: Optional[int]=None, level: Optional[int]=None, last_login_epoch: Optional[float]=None):
        state = await self.get_or_create_user(user_id, guild_id)
        xp = state.xp if xp is None else int(xp)
        level = state.level if level is None else int(level)
        last_login_epoch = state.last_login_epoch if last_login_epoch is None else last_login_epoch
        await self.db.execute(
            "UPDATE users SET xp=?, level=?, last_login_epoch=? WHERE user_id=? AND guild_id=?",
            (xp, level, last_login_epoch, int(user_id), int(guild_id))
        )
        await self.db.commit()

    async def recompute_level(self, xp: int) -> int:
        lvl = 0
        for i, threshold in enumerate(LEVEL_THRESHOLDS):
            if xp >= threshold:
                lvl = i
        # clamp to 4
        return min(lvl, 4)

    async def top_users(self, guild_id: int, limit: int = 10) -> List[SimpleNamespace]:
        cur = await self.db.execute(
            "SELECT user_id, xp, level FROM users WHERE guild_id=? ORDER BY xp DESC, level DESC LIMIT ?",
            (int(guild_id), int(limit))
        )
        rows = await cur.fetchall()
        await cur.close()
        out = []
        for uid, xp, level in rows:
            out.append(SimpleNamespace(user_id=int(uid), guild_id=int(guild_id), xp=int(xp), level=int(level)))
        return out

    # Perk p3 meta
    async def get_last_p3(self, user_id: int, guild_id: int) -> Optional[float]:
        cur = await self.db.execute("SELECT last_p3_epoch FROM perk_meta WHERE user_id=? AND guild_id=?", (int(user_id), int(guild_id)))
        row = await cur.fetchone()
        await cur.close()
        if row:
            return row[0]
        return None

    async def set_last_p3(self, user_id: int, guild_id: int, when: float):
        await self.db.execute(
            "INSERT INTO perk_meta (user_id, guild_id, last_p3_epoch) VALUES (?,?,?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET last_p3_epoch=excluded.last_p3_epoch",
            (int(user_id), int(guild_id), float(when))
        )
        await self.db.commit()


class LevelsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: aiosqlite.Connection = None  # type: ignore
        self.store: UserStore = None  # type: ignore

    async def cog_load(self):
        self.db = await aiosqlite.connect(DB_PATH)
        await self.db.execute("PRAGMA journal_mode=WAL;")
        await self.db.execute("PRAGMA synchronous=NORMAL;")
        self.store = UserStore(self.db)
        await self.store.init_tables()

    async def cog_unload(self):
        if self.db:
            await self.db.close()

    # ---------- XP/Level Logic ----------

    async def record_online(self, member: discord.Member):
        """Daily login bonus."""
        st = await self.store.get_or_create_user(member.id, member.guild.id)
        now = time.time()
        applied = 0
        leveled = False
        if (st.last_login_epoch is None) or (now - float(st.last_login_epoch) >= DAILY_BONUS_COOLDOWN):
            new_xp = st.xp + DAILY_BONUS_XP
            new_level = await self.store.recompute_level(new_xp)
            leveled = new_level > st.level
            await self.store.update_user(member.id, member.guild.id, xp=new_xp, level=new_level, last_login_epoch=now)
            st.xp, st.level, st.last_login_epoch = new_xp, new_level, now
            applied = DAILY_BONUS_XP
        return st, applied, leveled

    async def record_hack_success(self, member: discord.Member, *, difficulty: str, duration_sec: float):
        """Award XP for a successful hack. Returns (state, applied_xp, leveled, note)."""
        base = EASY_BASE_XP if difficulty == "easy" else HARD_BASE_XP
        best = EASY_BEST_SECONDS if difficulty == "easy" else HARD_BEST_SECONDS

        # Simple linear speed bonus: if you solve in <= best sec, +SPEED_BONUS_MAX; linearly down to +0 at 2*best
        bonus = 0
        if duration_sec <= 2 * best:
            # map [2*best .. best] -> [0 .. SPEED_BONUS_MAX]
            ratio = max(0.0, min(1.0, (2 * best - duration_sec) / best))
            bonus = int(round(SPEED_BONUS_MAX * ratio))

        applied = base + bonus
        note = f"(+{bonus} speed bonus)" if bonus > 0 else ""

        st = await self.store.get_or_create_user(member.id, member.guild.id)
        new_xp = st.xp + applied
        new_level = await self.store.recompute_level(new_xp)
        leveled = new_level > st.level
        await self.store.update_user(member.id, member.guild.id, xp=new_xp, level=new_level)
        st.xp, st.level = new_xp, new_level
        return st, applied, leveled, note

    async def add_xp_delta(self, member: discord.Member, delta: int, *, note: str = ""):
        """Add or subtract XP, clamp at >= 0, recompute level."""
        st = await self.store.get_or_create_user(member.id, member.guild.id)
        new_xp = max(0, st.xp + int(delta))
        new_level = await self.store.recompute_level(new_xp)
        await self.store.update_user(member.id, member.guild.id, xp=new_xp, level=new_level)
        st.xp, st.level = new_xp, new_level
        return st

# ---------- Perk P3 Daily Cooldown ----------

    async def perk_can_use_p3(self, member: discord.Member):
        last = await self.store.get_last_p3(member.id, member.guild.id)
        now = time.time()
        if last is None:
            return True, 0
        elapsed = now - float(last)
        if elapsed >= P3_COOLDOWN_SECONDS:
            return True, 0
        return False, P3_COOLDOWN_SECONDS - elapsed

    async def perk_mark_p3_used(self, member: discord.Member):
        await self.store.set_last_p3(member.id, member.guild.id, time.time())

    # ---------- Commands ----------

    @commands.command(name="rank")
    async def rank_cmd(self, ctx: commands.Context):
        st = await self.store.get_or_create_user(ctx.author.id, ctx.guild.id)
        await ctx.send(f"🛰️ **{ctx.author.display_name}** — Level **{st.level}**, XP **{st.xp}**")

    @commands.command(name="leaderboard")
    async def leaderboard_cmd(self, ctx: commands.Context):
        top = await self.store.top_users(ctx.guild.id, limit=10)
        if not top:
            return await ctx.send("No records yet.")
        lines = []
        for i, row in enumerate(top, start=1):
            member = ctx.guild.get_member(row.user_id)
            name = member.display_name if member else f"User {row.user_id}"
            lines.append(f"{i}. **{name}** — Level {row.level} • {row.xp} XP")
        await ctx.send("🏆 **Top Operatives**\n" + "\n".join(lines))

    # Admin helpers
    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="xp")
    async def xp_admin(self, ctx: commands.Context, action: str, member: discord.Member, amount: int):
        action = action.lower()
        if action == "add":
            st = await self.add_xp_delta(member, amount, note="admin add")
            await ctx.send(f"✅ Added {amount} XP to {member.mention} → Level {st.level}, {st.xp} XP")
        elif action == "set":
            st = await self.store.get_or_create_user(member.id, ctx.guild.id)
            new_xp = max(0, int(amount))
            new_level = await self.store.recompute_level(new_xp)
            await self.store.update_user(member.id, ctx.guild.id, xp=new_xp, level=new_level)
            await ctx.send(f"✅ Set {member.mention} to {new_xp} XP → Level {new_level}")
        else:
            await ctx.send("Usage: `\\xp add @user <amount>` or `\\xp set @user <amount>`")

    @commands.has_guild_permissions(administrator=True)
    @commands.command(name="level")
    async def level_admin(self, ctx: commands.Context, action: str, member: discord.Member, amount: int):
        if action.lower() != "set":
            return await ctx.send("Usage: `\\level set @user <level>`")
        lvl = max(0, min(4, int(amount)))
        st = await self.store.get_or_create_user(member.id, ctx.guild.id)
        await self.store.update_user(member.id, ctx.guild.id, xp=st.xp, level=lvl)
        await ctx.send(f"✅ Set {member.mention} to **Level {lvl}**")

async def setup(bot: commands.Bot):
    await bot.add_cog(LevelsCog(bot))
