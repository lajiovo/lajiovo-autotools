import os
import json
import random
import datetime
import hashlib
import itertools

class GameSystem:
    def __init__(self, data_manager):
        self.data_mgr = data_manager
        
        # 1. 动态加载配置文件
        self.config_path = os.path.join(os.path.dirname(__file__), "gameconfig.json")
        self.load_config()

        # 2. 运行时缓存与游戏会话
        self.common_pool = []
        self._refill_common_pool()
        self.guess_game_sessions = {}
        self.blackjack_sessions = {}
        self.bomb_sessions = {}
        self.point24_sessions = {}

    def load_config(self):
        """读取外部 JSON 配置文件"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"❌ 未找到配置文件：{self.config_path}，请确保 gameconfig.json 存在于同目录下。")

        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        self.RARITY_ORDER = cfg.get("rarity_order", {})
        self.RARITY_TAGS = cfg.get("rarity_tags", {})
        self.SHIP_RARITY_MAP = cfg.get("ship_rarity_map", {})
        self.FISHING_POOL = cfg.get("fishing_pool", [])
        self.SALVAGE_POOL = cfg.get("salvage_pool", [])
        self.DUEL_EVENTS = cfg.get("duel_events", [
            "发起了一轮猛烈开火！",
            "巧妙地闪避了所有炮火！",
            "呼叫舰载机完成了空袭！"
        ])

    def _generate_one_ship(self):
        ships, weights = zip(*[((s[0], s[1], s[3], s[4], s[5]), s[2]) for s in self.SALVAGE_POOL])
        return random.choices(ships, weights=weights, k=1)[0]

    def _refill_common_pool(self):
        while len(self.common_pool) < 200:
            self.common_pool.append(self._generate_one_ship())

    def _pop_ships_from_pool(self, count: int) -> list:
        drawn = [self.common_pool.pop(0) for _ in range(count)]
        self._refill_common_pool()
        return drawn

    # ==================== 响应构造器 (适配 QQ 群官方 API 规范) ====================
    @staticmethod
    def _build_qq_keyboard(raw_buttons: list) -> dict:
        """将简化的二维按钮数组转换成标准的 QQ 官方 Inline Keyboard 结构"""
        if not raw_buttons:
            return None
            
        rows = []
        for row_idx, row in enumerate(raw_buttons):
            buttons = []
            for btn_idx, btn in enumerate(row):
                clean_data = str(btn.get("data", "")).replace("@", "").strip()
                buttons.append({
                    "id": f"btn_{row_idx}_{btn_idx}",
                    "render_data": {
                        "label": btn.get("label", "按钮"),
                        "visited_label": btn.get("label", "按钮"),
                        "style": 1  # 默认蓝色高亮样式
                    },
                    "action": {
                        "type": 2,  # 点击后自动发送文本
                        "permission": {"type": 2},  # 所有人可用
                        "data": clean_data
                    }
                })
            rows.append({"buttons": buttons})
            
        return {"content": {"rows": rows}}

    @classmethod
    def _msg(cls, content: str, buttons: list = None) -> dict:
        res = {
            "msg_type": 2,
            "content": content
        }
        if buttons:
            res["keyboard"] = cls._build_qq_keyboard(buttons)
        return res

    def calculate_level(self, exp: int) -> int:
        return 1 if exp <= 0 else int((exp / 100) ** 0.5) + 1

    def calculate_user_power(self, dock: dict) -> int:
        multipliers = {1: 1.0, 2: 1.20, 3: 1.60, 4: 1.70}
        ship_powers = [
            int(self.SHIP_RARITY_MAP[name][1] * multipliers.get(count, 1.90))
            for name, count in dock.items() if name in self.SHIP_RARITY_MAP
        ]
        return sum(sorted(ship_powers, reverse=True)[:6])

    def evaluate_luck(self, salvage_counts: int, dock: dict) -> str:
        if salvage_counts < 5: return "尚在观望 (打捞不足 5 次)"
        actual = sum(v for k, v in dock.items() if k in self.SHIP_RARITY_MAP and self.SHIP_RARITY_MAP[k][0] in ["SSR", "海上传奇"])
        expected = salvage_counts * 0.045
        ratio = actual / expected if expected > 0 else 1.0

        if ratio >= 2.5: luck = "👑 **欧皇本皇**"
        elif ratio >= 1.5: luck = "✨ **欧洲人**"
        elif ratio >= 0.8: luck = "⚓ **亚洲平民**"
        elif ratio >= 0.3: luck = "🌧️ **非洲酋长**"
        else: luck = "🗿 **纯血非酋**"
        return f"{luck} *(实际 {actual} 艘 / 期望 {expected:.1f} 艘)*"

    # ==================== 数据接口适配 (适配 data_mgr 最新结构) ====================
    def _get_user_nickname(self, sender_openid: str) -> str:
        """从 userinfo 读取昵称，若无则自动设默认值"""
        nick = self.data_mgr.get_nickname(sender_openid)
        if not nick:
            info = self.data_mgr.get_user_info(sender_openid)
            nick = info.get("nickname") or info.get("name") or f"指挥官_{sender_openid[:4]}"
        return nick

    def _get_user_data(self, sender_openid: str) -> dict:
        """从 userdata 读取游戏数据，若无则初始化默认字段"""
        data = self.data_mgr.get_user_data(sender_openid)
        
        default_data = {
            "coins": 100, "exp": 0,
            "counts": 0, "salvage_counts": 0, "attack_counts": 0,
            "fish_bag": {}, "dock": {}
        }
        
        updated = False
        for key, val in default_data.items():
            if key not in data:
                data[key] = val
                updated = True
                
        # 同步并将昵称保存在数据副本中方便内部调用
        data["name"] = self._get_user_nickname(sender_openid)
        
        if updated:
            self._save_user_data(sender_openid, data)
        return data

    def _save_user_data(self, sender_openid: str, data: dict):
        """保存游戏数据至 userdata"""
        # 保存前剔除临时或冗余字段（如 name 属于 userinfo）
        save_data = {k: v for k, v in data.items() if k != "name"}
        self.data_mgr.set_user_data(sender_openid, save_data)

    def set_user_name(self, sender_openid: str, name: str) -> dict:
        """修改用户昵称并同步保存至 userinfo"""
        if len(name) > 12: return self._msg("❌ 名称长度不能超过 12 个字符。")
        
        user_info = self.data_mgr.get_user_info(sender_openid)
        user_info["nickname"] = name
        self.data_mgr.set_user_info(sender_openid, user_info)
        
        return self._msg(f"✅ 个人名称已成功修改为：**【{name}】**！")

    # ==================== 指令分发中心 ====================
    def handle_command(self, cmd: str, parts: list, sender_openid: str) -> dict:
        arg = parts[1] if len(parts) > 1 else ""

        default_btns = [
            [{"label": "⚓ 单抽打捞", "data": "#打捞"}, {"label": "🚀 十连打捞", "data": "#打捞 10"}, {"label": "🎣 挥竿钓鱼", "data": "#钓鱼"}],
            [{"label": "🎒 查看船坞", "data": "#船坞"}, {"label": "🔮 今日运势", "data": "#运势"}, {"label": "🏆 战力排行", "data": "#排行榜"}],
            [{"label": "🎮 娱乐小游戏", "data": "#游戏菜单"}]
        ]

        if cmd in ["帮助", "help", "菜单"]:
            help_md = (
                "### 🤖 港区交互指挥中心\n"
                "> 点击下方按钮或输入相应指令即可交互：\n\n"
                "* **⚓ 舰队养成**：`#打捞` | `#出击` | `#钓鱼` | `#船坞` | `#改名 新名字`\n"
                "* **🎲 游艺广场**：`#游戏菜单`（含炸弹人、21点、决斗、24点等）\n"
                "* **📊 数据查询**：`#运势` | `#排行榜` | `#时间`"
            )
            return self._msg(help_md, default_btns)

        if cmd in ["游戏菜单", "小游戏"]:
            game_md = (
                "### 🎮 游艺广场小游戏合集\n"
                "选择你想要挑战的小游戏："
            )
            game_menu_btns = [
                [{"label": "💣 拆弹专家", "data": "#炸弹人"}, {"label": "⚔️ 舰队决斗", "data": "#决斗"}],
                [{"label": "🧮 算术24点", "data": "#24点"}, {"label": "🎰 极速拉霸", "data": "#老虎机"}],
                [{"label": "♠️ 21点扑克", "data": "#21点"}, {"label": "🔢 猜数字", "data": "#猜数字"}],
                [{"label": "✌️ 猜拳对决", "data": "#猜拳"}, {"label": "🏃 舰船赛跑", "data": "#赛跑"}],
                [{"label": "🔙 返回主菜单", "data": "#帮助"}]
            ]
            return self._msg(game_md, game_menu_btns)

        cmd_map = {
            "name": lambda: self.set_user_name(sender_openid, " ".join(parts[1:]).strip()) if len(parts) > 1 else self._msg("⚠️ 请输入名称，例如：`#改名 阿斯兰`"),
            "改名": lambda: self.set_user_name(sender_openid, " ".join(parts[1:]).strip()) if len(parts) > 1 else self._msg("⚠️ 请输入名称，例如：`#改名 阿斯兰`"),
            "打捞": lambda: self.play_salvage(sender_openid, count=10 if arg == "10" else 1),
            "搜救": lambda: self.play_salvage(sender_openid, count=10 if arg == "10" else 1),
            "捞船": lambda: self.play_salvage(sender_openid, count=10 if arg == "10" else 1),
            "钓鱼": lambda: self.play_fishing(sender_openid),
            "fish": lambda: self.play_fishing(sender_openid),
            "猜数字": lambda: self.play_guess_number(sender_openid, arg),
            "guess": lambda: self.play_guess_number(sender_openid, arg),
            "21点": lambda: self.play_blackjack(sender_openid, arg),
            "blackjack": lambda: self.play_blackjack(sender_openid, arg),
            "猜拳": lambda: self.play_rps(sender_openid, arg),
            "rps": lambda: self.play_rps(sender_openid, arg),
            "老虎机": lambda: self.play_slot_machine(sender_openid),
            "slot": lambda: self.play_slot_machine(sender_openid),
            "赛跑": lambda: self.play_ship_race(sender_openid, arg),
            "race": lambda: self.play_ship_race(sender_openid, arg),
            "炸弹人": lambda: self.play_bomb_game(sender_openid, arg),
            "拆弹": lambda: self.play_bomb_game(sender_openid, arg),
            "决斗": lambda: self.play_duel(sender_openid, " ".join(parts[1:]).strip()),
            "24点": lambda: self.play_point24(sender_openid, arg),
            "船坞": lambda: self.get_user_assets(sender_openid),
            "背包": lambda: self.get_user_assets(sender_openid),
            "排行榜": lambda: self.get_rank(),
            "战力榜": lambda: self.get_rank(),
            "运势": lambda: self.get_fortune(sender_openid),
            "roll": lambda: self._msg(f"🎲 掷骰子结果：`{random.randint(1, max(1, int(arg) if arg.isdigit() else 100))}`"),
            "时间": lambda: self._msg(f"🕒 **服务器时间**：\n`{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")
        }

        if cmd.startswith("出击"):
            return self.play_attack(sender_openid, " ".join(parts[1:]) if len(parts) > 1 else "")

        handler = cmd_map.get(cmd)
        return handler() if handler else self._msg(f"❌ 未知指令：`#{cmd}`\n发送 `#帮助` 查看完整指令。", default_btns)

    # ==================== 经典玩法 ====================
    def play_salvage(self, sender_openid: str, count: int = 1) -> dict:
        user_data = self._get_user_data(sender_openid)
        user_data["salvage_counts"] = user_data.get("salvage_counts", 0) + count

        drawn = self._pop_ships_from_pool(count)
        total_coins, total_exp = sum(s[2] for s in drawn), sum(s[3] for s in drawn)

        for _, ship_name, _, _, _ in drawn:
            user_data["dock"][ship_name] = user_data["dock"].get(ship_name, 0) + 1

        user_data["coins"] += total_coins
        user_data["exp"] += total_exp
        self._save_user_data(sender_openid, user_data)

        btns = [[{"label": "⚓ 再打捞一次", "data": f"#打捞 {count}"}, {"label": "🎒 查看船坞", "data": "#船坞"}]]

        if count == 1:
            rarity, ship_name, _, _, quote = drawn[0]
            title = "### ⚓ 打捞成功！"
            if rarity == "海上传奇": title = "### 🌟⚡ 彩光大破！海上传奇降临！ ⚡🌟"
            elif rarity == "SSR": title = "### ✨ 金色闪耀！超稀有舰船回应！ ✨"
            
            md = (f"{title}\n"
                  f"* **获得舰船**：[{self.RARITY_TAGS.get(rarity, rarity)}] **{ship_name}**\n"
                  f"* **台词**：“*{quote}*”\n"
                  f"> 💰 **收益**：金币 `+{total_coins}` | 经验 `+{total_exp}`\n"
                  f"> 📊 **当前**：金币 `{user_data['coins']}` | 经验 `{user_data['exp']}`")
            return self._msg(md, btns)

        has_ur = any(s[0] == "海上传奇" for s in drawn)
        has_ssr = any(s[0] == "SSR" for s in drawn)
        header = "### 🌟🌈 十连彩光！！海上传奇降临！" if has_ur else ("### ✨🟡 十连金光！获得超稀有舰船！" if has_ssr else "### ⚓ 十连打捞报告")

        ship_lines = [
            f"* [{self.RARITY_TAGS.get(s[0], s[0])}] **{s[1]}**" + (f"\n  > “*{s[4]}*”" if s[0] in ["SSR", "海上传奇"] else "")
            for s in drawn
        ]
        md = f"{header}\n\n" + "\n".join(ship_lines) + f"\n\n> 💰 **总收益**：金币 `+{total_coins}` | 经验 `+{total_exp}`\n> 📊 **当前总计**：金币 `{user_data['coins']}` | 经验 `{user_data['exp']}`"
        return self._msg(md, btns)

    def play_attack(self, sender_openid: str, target_str: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        user_data["attack_counts"] = user_data.get("attack_counts", 0) + 1
        my_power = self.calculate_user_power(user_data["dock"])

        clean_target = target_str.replace("@", "").strip()
        
        # 通过 get_user_list 遍历寻找目标玩家数据
        target_data = None
        target_name = clean_target or "深海塞壬巡逻队"
        target_power = 0
        
        if clean_target:
            user_list = self.data_mgr.get_user_list()
            for uid in user_list:
                if uid == sender_openid:
                    continue
                nick = self._get_user_nickname(uid)
                if clean_target in nick or clean_target in uid:
                    target_ud = self._get_user_data(uid)
                    target_name = nick
                    target_power = self.calculate_user_power(target_ud.get("dock", {}))
                    target_data = target_ud
                    break

        if not target_data:
            target_power = max(100, int(my_power * random.uniform(0.8, 1.2)))

        btns = [[{"label": "⚔️ 再次出击", "data": "#出击"}, {"label": "🏆 排行榜", "data": "#排行榜"}]]

        if my_power >= target_power:
            chosen = random.choice([s for s in self.SALVAGE_POOL if s[0] in ["N", "R", "SR"]])
            coins, exp = random.randint(300, 800), random.randint(150, 400)
            user_data["dock"][chosen[1]] = user_data["dock"].get(chosen[1], 0) + 1
            user_data["coins"] += coins
            user_data["exp"] += exp
            self._save_user_data(sender_openid, user_data)
            md = (f"### ⚔️ 出击大捷！\n"
                  f"* **对阵双方**：`{user_data['name']}` ({my_power} PT) **VS** `{target_name}` ({target_power} PT)\n"
                  f"* **战果**：🎉 **成功克敌制胜！**\n"
                  f"* **捕获**：[{chosen[0]}] **{chosen[1]}**\n"
                  f"> 💰 **战利品**：金币 `+{coins}` | 经验 `+{exp}`")
        else:
            lost = random.randint(100, 300)
            user_data["coins"] = max(0, user_data["coins"] - lost)
            self._save_user_data(sender_openid, user_data)
            md = (f"### 💥 出击受挫！\n"
                  f"* **对阵双方**：`{user_data['name']}` ({my_power} PT) **VS** `{target_name}` ({target_power} PT)\n"
                  f"* **战果**：😭 **战力不敌惨遭击退！**\n"
                  f"> 💸 **损失**：遗失了 `{lost}` 金币 *(剩余 `{user_data['coins']}`)*")
        return self._msg(md, btns)

    def play_fishing(self, sender_openid: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        user_data["counts"] += 1

        items, weights = zip(*[((i[0], i[1], i[3], i[4], i[5], i[6]), i[2]) for i in self.FISHING_POOL])
        item_type, item_name, base_coin, base_exp, min_w, max_w = random.choices(items, weights=weights, k=1)[0]

        weight = round(random.uniform(min_w, max_w), 2)
        mult = max(1.0, weight / min_w) if item_type == "fish" else 1.0
        coins, exp = int(base_coin * mult), int(base_exp * mult)

        user_data["coins"] += coins
        user_data["exp"] += exp
        user_data["fish_bag"][item_name] = user_data["fish_bag"].get(item_name, 0) + 1
        self._save_user_data(sender_openid, user_data)

        prefixes = {
            "junk": ("🗑️ 哎呀，好像钩到了什么假东西...", f"钓到了 **【{item_name}】** ({weight}kg)！"),
            "legend": ("💥 杆子差点折断！出现了不可思议的巨物！", f"捕获了传说中的 **【{item_name}】** (重达 `{weight}kg`)！"),
            "box": ("✨ 啪嗒！打捞上了一个带有古老纹路的宝箱！", f"得到了 **【{item_name}】**！")
        }
        prefix, detail = prefixes.get(item_type, ("🌊 水花四溅！鱼儿上钩了！", f"钓到了 **【{item_name}】** ({weight}kg)！"))
        
        md = (f"{prefix}\n"
              f"* **结果**：{detail}\n"
              f"> 💰 **收益**：金币 `+{coins}` | 经验 `+{exp}` *(当前金币: `{user_data['coins']}`)*")
        btns = [[{"label": "🎣 再次挥竿", "data": "#钓鱼"}, {"label": "🐟 查看背包", "data": "#背包"}]]
        return self._msg(md, btns)

    # ==================== 新增小游戏区 ====================
    
    # --- 小游戏 1：💣 拆弹专家 (扫雷式剪线) ---
    def play_bomb_game(self, sender_openid: str, wire: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        session = self.bomb_sessions.get(sender_openid)

        if not session or wire == "重置":
            bomb_wire = random.randint(1, 5)
            self.bomb_sessions[sender_openid] = {"bomb": bomb_wire, "safe": 0}
            md = (f"### 💣 拆弹专家小游戏\n"
                  f"面前有一枚定时炸弹，共有 **5 条引线** (1-5)。\n"
                  f"其中只有 **1 条会引爆**！每剪断一条安全线即可获得累积奖励。\n"
                  f"点击下方按钮选择你要剪断的引线：")
            btns = [[{"label": f"✂️ 剪 {i} 号线", "data": f"#拆弹 {i}"} for i in range(1, 6)]]
            return self._msg(md, btns)

        if not wire.isdigit() or int(wire) not in range(1, 6):
            btns = [[{"label": f"✂️ 剪 {i} 号线", "data": f"#拆弹 {i}"} for i in range(1, 6)]]
            return self._msg("⚠️ 请选择正确的引线编号 (1-5)！", btns)

        chosen = int(wire)
        if chosen == session["bomb"]:
            del self.bomb_sessions[sender_openid]
            loss = random.randint(80, 200)
            user_data["coins"] = max(0, user_data["coins"] - loss)
            self._save_user_data(sender_openid, user_data)
            btns = [[{"label": "💣 再试一次", "data": "#拆弹 重置"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
            return self._msg(f"### 💥 BOOM！引爆了炸弹！\n你剪断了 **{chosen}号线**，不幸触发了爆炸！\n> 💸 **损失**：扣除金币 `{loss}` *(剩余 `{user_data['coins']}`)*", btns)

        session["safe"] += 1
        safe_count = session["safe"]

        if safe_count >= 4:
            del self.bomb_sessions[sender_openid]
            coins, exp = 600, 250
            user_data["coins"] += coins
            user_data["exp"] += exp
            self._save_user_data(sender_openid, user_data)
            btns = [[{"label": "💣 再玩一局", "data": "#拆弹 重置"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
            return self._msg(f"### 🎉 完美拆除！全场安全！\n你成功剪断了所有 safe 引线，完美避开炸弹！\n> 💰 **通关大奖**：金币 `+{coins}` | 经验 `+{exp}`", btns)

        reward_coins = safe_count * 100
        btns = [[{"label": f"✂️ 剪 {i} 号线", "data": f"#拆弹 {i}"} for i in range(1, 6) if i != chosen]]
        return self._msg(f"✨ **咔哒！{chosen}号线安全！**\n当前已成功剪断 `{safe_count}` 条线，奖金池累积：`{reward_coins}` 金币！\n请继续选择下一条引线：", btns)

    # --- 小游戏 2：⚔️ 舰队决斗 ---
    def play_duel(self, sender_openid: str, target_str: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        my_power = self.calculate_user_power(user_data["dock"])

        clean_target = target_str.replace("@", "").strip()
        
        target_name = clean_target or "虚拟训练假人"
        target_power = 0
        
        if clean_target:
            user_list = self.data_mgr.get_user_list()
            for uid in user_list:
                if uid == sender_openid:
                    continue
                nick = self._get_user_nickname(uid)
                if clean_target in nick or clean_target in uid:
                    target_ud = self._get_user_data(uid)
                    target_name = nick
                    target_power = self.calculate_user_power(target_ud.get("dock", {}))
                    break

        if target_power == 0:
            target_power = random.randint(max(50, my_power - 200), my_power + 200)

        p1_hp, p2_hp = 100, 100
        logs = []

        while p1_hp > 0 and p2_hp > 0:
            dmg1 = int(random.randint(15, 35) * (my_power / max(1, target_power)) ** 0.3)
            p2_hp -= dmg1
            event1 = random.choice(self.DUEL_EVENTS)
            logs.append(f"⚔️ **{user_data['name']}** {event1} *(造成 {dmg1} 点伤害)*")
            if p2_hp <= 0: break

            dmg2 = int(random.randint(15, 35) * (target_power / max(1, my_power)) ** 0.3)
            p1_hp -= dmg2
            event2 = random.choice(self.DUEL_EVENTS)
            logs.append(f"🛡️ **{target_name}** {event2} *(造成 {dmg2} 点伤害)*")

        btns = [[{"label": "⚔️ 再决斗一次", "data": "#决斗"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]

        if p1_hp > 0:
            coins, exp = random.randint(150, 300), random.randint(50, 120)
            user_data["coins"] += coins
            user_data["exp"] += exp
            self._save_user_data(sender_openid, user_data)
            md = (f"### 🏆 决斗胜利！\n"
                  f"**【{user_data['name']}】** VS **【{target_name}】**\n\n" +
                  "\n".join(logs[-4:]) +
                  f"\n\n🎉 **最终获胜者**：**{user_data['name']}**！\n"
                  f"> 💰 **奖励**：金币 `+{coins}` | 经验 `+{exp}`")
        else:
            loss = random.randint(50, 100)
            user_data["coins"] = max(0, user_data["coins"] - loss)
            self._save_user_data(sender_openid, user_data)
            md = (f"### 😭 决斗战败！\n"
                  f"**【{user_data['name']}】** VS **【{target_name}】**\n\n" +
                  "\n".join(logs[-4:]) +
                  f"\n\n💀 **最终获胜者**：**{target_name}**！\n"
                  f"> 💸 **损失**：金币 `-{loss}`")

        return self._msg(md, btns)

    # --- 小游戏 3：🧮 24点算术益智 ---
    def play_point24(self, sender_openid: str, answer_expr: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        session = self.point24_sessions.get(sender_openid)

        def solve_24(nums):
            for p in itertools.permutations(nums):
                for ops in itertools.product(['+', '-', '*'], repeat=3):
                    exprs = [
                        f"(({p[0]}{ops[0]}{p[1]}){ops[1]}{p[2]}){ops[2]}{p[3]}",
                        f"({p[0]}{ops[0]}{p[1]}){ops[1]}({p[2]}{ops[2]}{p[3]})"
                    ]
                    for e in exprs:
                        try:
                            if abs(eval(e) - 24) < 1e-5: return True
                        except ZeroDivisionError: pass
            return False

        if not session or answer_expr == "重置":
            while True:
                nums = [random.randint(1, 10) for _ in range(4)]
                if solve_24(nums): break
            self.point24_sessions[sender_openid] = nums
            md = (f"### 🧮 24点智力挑战\n"
                  f"随机数字：`{nums[0]}` , `{nums[1]}` , `{nums[2]}` , `{nums[3]}`\n"
                  f"> 请使用 `+ - * /` 和括号将这 4 个数字计算得出 **24**！\n"
                  f"发送指令格式：`#24点 (a+b)*(c-d)`")
            btns = [[{"label": "🔄 换一组数字", "data": "#24点 重置"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
            return self._msg(md, btns)

        nums = session
        clean_expr = answer_expr.replace(" ", "").replace("x", "*").replace("X", "*")

        for c in clean_expr:
            if c not in "0123456789+-*/()":
                return self._msg("❌ 输入包含非法字符！仅允许数字、`+ - * /` 和 `()` 括号。")

        try:
            val = eval(clean_expr)
            if abs(val - 24) < 1e-5:
                del self.point24_sessions[sender_openid]
                coins, exp = 400, 200
                user_data["coins"] += coins
                user_data["exp"] += exp
                self._save_user_data(sender_openid, user_data)
                btns = [[{"label": "🧮 再来一局", "data": "#24点 重置"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
                return self._msg(f"### 🎉 解题正确！\n算式：`{clean_expr} = 24`\n> 💰 **聪慧奖励**：金币 `+{coins}` | 经验 `+{exp}`", btns)
            else:
                return self._msg(f"❌ 计算结果为 `{val}`，并不是 24 哦！再试一次吧！")
        except Exception:
            return self._msg("❌ 表达式格式错误，无法计算！例如：`#24点 (1+2+3)*4`")

    # ==================== 其他既有小游戏优化 ====================
    def play_guess_number(self, sender_openid: str, arg: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        
        if arg == "重置" or sender_openid not in self.guess_game_sessions:
            self.guess_game_sessions[sender_openid] = {"target": random.randint(1, 100), "attempts": 0}
            if arg == "重置": return self._msg("🔄 **猜数字已重置！** 目标数字为 `1-100` 之间的整数。")

        if not arg or not arg.isdigit():
            md = "### 🔢 猜数字小游戏\n目标数字：`1 - 100`\n直接发送格式 `#猜数字 数字` 进行猜测。"
            btns = [[{"label": "猜 50", "data": "#猜数字 50"}, {"label": "重置对局", "data": "#猜数字 重置"}]]
            return self._msg(md, btns)

        session = self.guess_game_sessions[sender_openid]
        session["attempts"] += 1
        val, target = int(arg), session["target"]

        if val != target:
            tip = "📉 **太小了！**" if val < target else "📈 **太大了！**"
            return self._msg(f"{tip} 已尝试 `{session['attempts']}` 次。")

        attempts = session["attempts"]
        del self.guess_game_sessions[sender_openid]
        coins, exp = max(50, 500 - (attempts - 1) * 50), max(20, 200 - (attempts - 1) * 20)
        user_data["coins"] += coins
        user_data["exp"] += exp
        self._save_user_data(sender_openid, user_data)

        btns = [[{"label": "🔢 再玩一次", "data": "#猜数字 重置"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
        md = (f"### 🎉 恭喜猜中！\n"
              f"* **正确答案**：`{target}`\n"
              f"* **总共尝试**：`{attempts}` 次\n"
              f"> 💰 **奖励**：金币 `+{coins}` | 经验 `+{exp}`")
        return self._msg(md, btns)

    def play_blackjack(self, sender_openid: str, action: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        cards_deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

        def get_score(cards):
            score = sum(10 if c in ['J', 'Q', 'K'] else (11 if c == 'A' else int(c)) for c in cards)
            aces = cards.count('A')
            while score > 21 and aces: score -= 10; aces -= 1
            return score

        session = self.blackjack_sessions.get(sender_openid)
        game_btns = [[{"label": "🃏 要牌 (Hit)", "data": "#21点 要牌"}, {"label": "🛑 停牌 (Stand)", "data": "#21点 停牌"}]]

        if not session or action not in ["要牌", "停牌", "hit", "stand"]:
            session = {"p": [random.choice(cards_deck), random.choice(cards_deck)], "d": [random.choice(cards_deck), random.choice(cards_deck)]}
            self.blackjack_sessions[sender_openid] = session
            md = (f"### ♠️ 21点桌游开局\n"
                  f"* **你的手牌**：`{' '.join(session['p'])}` *(点数: `{get_score(session['p'])}`)*\n"
                  f"* **庄家明牌**：`{session['d'][0]}` `[?]`\n"
                  f"> 请点击下方按钮选择操作：")
            return self._msg(md, game_btns)

        p_cards, d_cards = session["p"], session["d"]

        if action in ["要牌", "hit"]:
            p_cards.append(random.choice(cards_deck))
            p_score = get_score(p_cards)
            if p_score > 21:
                del self.blackjack_sessions[sender_openid]
                lost = random.randint(50, 150)
                user_data["coins"] = max(0, user_data["coins"] - lost)
                self._save_user_data(sender_openid, user_data)
                btns = [[{"label": "🃏 再玩一局", "data": "#21点"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
                return self._msg(f"### 💥 爆牌！\n* **最终手牌**：`{' '.join(p_cards)}` (`{p_score}`点)\n> 💸 扣除金币 `{lost}` *(当前: `{user_data['coins']}`)*", btns)
            
            md = f"🎴 **补牌结果**：`{' '.join(p_cards)}` *(当前点数: `{p_score}`)*"
            return self._msg(md, game_btns)

        del self.blackjack_sessions[sender_openid]
        while get_score(d_cards) < 17: d_cards.append(random.choice(cards_deck))
        p_score, d_score = get_score(p_cards), get_score(d_cards)

        md = f"### ♠️ 21点 结算对局\n* **玩家手牌**：`{' '.join(p_cards)}` (`{p_score}`点)\n* **庄家手牌**：`{' '.join(d_cards)}` (`{d_score}`点)\n\n"

        if d_score > 21 or p_score > d_score:
            coins, exp = random.randint(200, 400), random.randint(80, 150)
            user_data["coins"] += coins
            user_data["exp"] += exp
            md += f"🎉 **恭喜胜出！**\n> 💰 **收益**：金币 `+{coins}` | 经验 `+{exp}`"
        elif p_score == d_score:
            md += "⚖️ **平局！** 退还本局筹码。"
        else:
            lost = random.randint(100, 200)
            user_data["coins"] = max(0, user_data["coins"] - lost)
            md += f"😭 **庄家胜出！**\n> 💸 **损失**：金币 `-{lost}`"

        self._save_user_data(sender_openid, user_data)
        return self._msg(md, [[{"label": "🎮 再来一局", "data": "#21点"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]])

    def play_rps(self, sender_openid: str, choice: str) -> dict:
        options = ["石头", "剪刀", "布"]
        rps_btns = [[{"label": "✊ 石头", "data": "#猜拳 石头"}, {"label": "✌️ 剪刀", "data": "#猜拳 剪刀"}, {"label": "🖐️ 布", "data": "#猜拳 布"}]]

        if choice not in options:
            return self._msg("✂️ 请点击下方按钮选择猜拳手势：", rps_btns)

        user_data = self._get_user_data(sender_openid)
        bot_choice = random.choice(options)
        win_map = {"石头": "剪刀", "剪刀": "布", "布": "石头"}

        if choice == bot_choice:
            res, coins, exp = "⚖️ **平局**", 10, 5
        elif win_map[choice] == bot_choice:
            res, coins, exp = "🏆 **胜利**", random.randint(80, 150), random.randint(40, 80)
        else:
            res, coins, exp = "💥 **失败**", -random.randint(30, 80), 0

        user_data["coins"] = max(0, user_data["coins"] + coins)
        user_data["exp"] += exp
        self._save_user_data(sender_openid, user_data)

        md = (f"### ✌️ 猜拳对决结果\n"
              f"* **出招**：你 **[{choice}]** VS 对方 **[{bot_choice}]**\n"
              f"* **判定**：{res}\n"
              f"> 💰 **变动**：金币 `{coins:+}` | 经验 `+{exp}` *(当前: `{user_data['coins']}`)*")
        return self._msg(md, rps_btns)

    def play_slot_machine(self, sender_openid: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        if user_data["coins"] < 50:
            return self._msg("❌ 你的金币不足！摇一次老虎机需要 `50` 金币。")

        user_data["coins"] -= 50
        symbols, weights = ["🍋", "🍒", "🔔", "⭐", "💎", "🌈"], [30, 25, 20, 15, 8, 2]
        r1, r2, r3 = random.choices(symbols, weights=weights, k=3)

        if (r1, r2, r3) == ("🌈", "🌈", "🌈"):
            coins, exp, tip = 2000, 1000, "🌟🌈 **SUPER JACKPOT！全屏彩虹！** 🌈🌟"
        elif (r1, r2, r3) == ("💎", "💎", "💎"):
            coins, exp, tip = 1000, 500, "✨💎 **钻石连击爆发！** 💎✨"
        elif r1 == r2 == r3:
            coins, exp, tip = 500, 200, "🎉 **三连大奖命中！** 🎉"
        elif r1 in (r2, r3) or r2 == r3:
            coins, exp, tip = 100, 30, "✨ **二连对子！小有收获** ✨"
        else:
            coins, exp, tip = 0, 5, "😭 遗憾未中奖，继续加油！"

        user_data["coins"] += coins
        user_data["exp"] += exp
        self._save_user_data(sender_openid, user_data)

        md = (f"### 🎰 拉霸老虎机\n"
              f"```\n[ {r1} | {r2} | {r3} ]\n```\n"
              f"{tip}\n"
              f"> 💰 **结算**：金币 `+{coins}` *(门票-50)* | 经验 `+{exp}`\n"
              f"> 📊 **剩余**：`{user_data['coins']}` 金币")
        btns = [[{"label": "🎰 再拉一次", "data": "#老虎机"}, {"label": "🎮 游戏菜单", "data": "#游戏菜单"}]]
        return self._msg(md, btns)

    def play_ship_race(self, sender_openid: str, choice: str) -> dict:
        racers = {"1": ("拉菲", 0.3), "2": ("企业", 0.1), "3": ("雪风", 0.5)}
        race_btns = [[{"label": "1号 拉菲", "data": "#赛跑 1"}, {"label": "2号 企业", "data": "#赛跑 2"}, {"label": "3号 雪风", "data": "#赛跑 3"}]]

        if choice not in racers:
            md = "### 🏃 海上赛跑竞技场\n请选择押注选手：\n1. **拉菲** (速度型 - 爆发极高)\n2. **企业** (稳定型 - 航速平稳)\n3. **雪风** (爆发型 - 奇迹选手)"
            return self._msg(md, race_btns)

        user_data = self._get_user_data(sender_openid)
        scores = {k: round(random.randint(60, 90) + random.uniform(-v[1], v[1]) * 50, 1) for k, v in racers.items()}
        sorted_ranks = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        winner_num = sorted_ranks[0][0]
        chosen_name, winner_name = racers[choice][0], racers[winner_num][0]
        rank_str = "\n".join([f"{i+1}. **{racers[n][0]}**：`{score} 节`" for i, (n, score) in enumerate(sorted_ranks)])

        if choice == winner_num:
            coins, exp = 300, 150
            user_data["coins"] += coins
            user_data["exp"] += exp
            res = f"🎉 **猜中了！** 【{chosen_name}】勇夺桂冠！\n> 💰 **奖励**：金币 `+{coins}` | 经验 `+{exp}`"
        else:
            user_data["coins"] = max(0, user_data["coins"] - 50)
            res = f"😭 **遗憾！** 冠军是【{winner_name}】！\n> 💸 **扣除报名费**：`50` 金币"

        self._save_user_data(sender_openid, user_data)
        md = f"### 🏁 赛船比赛结束\n**📊 比赛成绩榜**：\n{rank_str}\n\n{res}"
        return self._msg(md, race_btns)
    # ==================== 查询与面板 ====================
    def get_user_assets(self, sender_openid: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        dock, bag = user_data["dock"], user_data["fish_bag"]

        sorted_dock = sorted(
            dock.items(),
            key=lambda x: (self.RARITY_ORDER.get(self.SHIP_RARITY_MAP.get(x[0], ("N", 0))[0], 99), -x[1])
        )

        dock_str = "\n".join([f"* [{self.RARITY_TAGS.get(self.SHIP_RARITY_MAP.get(k, ('N', 0))[0], 'N')}] **{k}** x{v}" for k, v in sorted_dock]) or "* *暂无舰船*"
        bag_str = "\n".join([f"* **{k}**: `{v}` 次" for k, v in bag.items()]) or "* *空无一物*"

        md = (f"### 🎒 {user_data.get('name', '指挥官')} 的资源库\n"
              f"* **🎖️ 军衔等级**：`Lv.{self.calculate_level(user_data['exp'])}`\n"
              f"* **⚔️ 舰队战力**：`{self.calculate_user_power(dock)} PT`\n"
              f"* **🎲 欧非评级**：{self.evaluate_luck(user_data.get('salvage_counts', 0), dock)}\n"
              f"> 💰 **资产**：金币 `{user_data['coins']}` | 经验 `{user_data['exp']}`\n"
              f"> 📊 **统计**：打捞 `{user_data.get('salvage_counts', 0)}` | 出击 `{user_data.get('attack_counts', 0)}` | 钓鱼 `{user_data['counts']}`\n\n"
              f"#### ⚓ 舰队船坞\n{dock_str}\n\n"
              f"#### 🐟 水产图鉴\n{bag_str}")
        return self._msg(md)

    def get_rank(self) -> dict:
        user_list = self.data_mgr.get_user_list()
        if not user_list:
            return self._msg("🏆 暂时还没有人参与排行！")

        # 汇总所有用户的战力与经验数据
        all_user_stats = []
        for uid in user_list:
            ud = self._get_user_data(uid)
            nick = self._get_user_nickname(uid)
            power = self.calculate_user_power(ud.get("dock", {}))
            exp = ud.get("exp", 0)
            all_user_stats.append({
                "uid": uid,
                "name": nick,
                "power": power,
                "exp": exp,
                "dock": ud.get("dock", {})
            })

        # 战力榜排序
        p_rank = sorted(all_user_stats, key=lambda x: x["power"], reverse=True)[:5]
        p_lines = [f"{i}. **{s['name']}** - `{s['power']} PT`" for i, s in enumerate(p_rank, 1)]

        # 等级经验榜排序
        e_rank = sorted(all_user_stats, key=lambda x: x["exp"], reverse=True)[:5]
        e_lines = [f"{i}. **{s['name']}** - `Lv.{self.calculate_level(s['exp'])}` (*{s['exp']} exp*)" for i, s in enumerate(e_rank, 1)]

        md = ("### 🏆 指挥官综合排行榜\n\n"
              "#### ⚔️ 主力战力榜 TOP 5\n" + ("\n".join(p_lines) or "* 暂无数据 *") + "\n\n"
              "#### 🎖️ 等级经验榜 TOP 5\n" + ("\n".join(e_lines) or "* 暂无数据 *"))
        return self._msg(md)

    def get_fortune(self, sender_openid: str) -> dict:
        today_str = datetime.date.today().strftime("%Y%m%d")
        h = int(hashlib.md5(f"{sender_openid}_{today_str}".encode('utf-8')).hexdigest(), 16)
        fortunes = [
            ("大吉 🌸", "运气爆棚，今天适合做重要的决定！"), ("中吉 🍀", "平平淡淡才是真，今天会有意想不到的惊喜。"),
            ("小吉 🌿", "小有收获，保持好心情。"), ("吉 🌟", "一切顺利，按部就班即可。"),
            ("末吉 🍂", "放平心态，多注意休息。"), ("凶 ⚠️", "今天宜低调做事，少说多看哦~")
        ]
        res, desc = fortunes[h % len(fortunes)]
        md = (f"### 🔮 今日运势\n"
              f"* **签文**：**{res}**\n"
              f"* **幸运指数**：`{(h % 100) + 1}%`\n"
              f"> 💡 *{desc}*")
        return self._msg(md)