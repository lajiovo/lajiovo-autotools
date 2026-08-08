import random
import datetime
import hashlib

class GameSystem:
    RARITY_ORDER = {"海上传奇": 1, "SSR": 2, "SR": 3, "R": 4, "N": 5}
    RARITY_TAGS = {"N": "`N`", "R": "`R`", "SR": "`SR`", "SSR": "**SSR**", "海上传奇": "**✨UR✨**"}

    SHIP_RARITY_MAP = {
        "小天鹅": ("N", 20), "利安得": ("N", 20), "奥马哈": ("N", 20), "卡辛": ("N", 20), "唐斯": ("N", 20), "罗利": ("N", 20),
        "拉菲": ("R", 80), "绫波": ("R", 80), "标枪": ("R", 80), "菲尼克斯": ("R", 80), "波特兰": ("R", 80), "宾夕法尼亚": ("R", 80),
        "海伦娜": ("SR", 300), "独角兽": ("SR", 300), "克利夫兰": ("SR", 300), "海伦娜·META": ("SR", 300), "雪风": ("SR", 300), "天狼星": ("SR", 300),
        "企业": ("SSR", 1000), "胡德": ("SSR", 1000), "赤城": ("SSR", 1000), "俾斯麦": ("SSR", 1000), "阿芙乐尔": ("SSR", 1000), "四万十": ("SSR", 1000), "提尔皮茨": ("SSR", 1000), "英仙座": ("SSR", 1000), "科本斯": ("SSR", 1000),
        "信浓": ("海上传奇", 5000), "新泽西": ("海上传奇", 5000), "武藏": ("海上传奇", 5000), "Z52": ("海上传奇", 5000), "马耳他": ("海上传奇", 5000), "纳希莫夫海军上阵": ("海上传奇", 5000), "阿尔萨斯": ("海上传奇", 5000), "莫加多尔": ("海上传奇", 5000), "拉斐尔": ("海上传奇", 5000), "金狮": ("海上传奇", 5000), "瓦尔帕莱索": ("海上传奇", 5000)
    }

    FISHING_POOL = [
        ("junk", "破旧的破鞋", 20, 1, 1, 0.2, 0.8), ("junk", "缠人的水草", 20, 1, 1, 0.1, 0.5),
        ("fish", "小鲫鱼", 25, 20, 10, 0.3, 1.2), ("fish", "大鲤鱼", 15, 50, 25, 1.5, 4.5),
        ("fish", "肥美的大鲢鱼", 10, 80, 40, 3.0, 8.0), ("fish", "金光闪闪的金鱼", 5, 160, 80, 0.2, 0.6),
        ("legend", "深海大白鲨", 3, 400, 200, 150.0, 400.0), ("box", "沉没的神秘宝箱", 2, 700, 300, 5.0, 10.0)
    ]

    SALVAGE_POOL = [
        ("N", "小天鹅", 10, 50, 25, "指挥官，今天也要加油哦！"), ("N", "利安得", 10, 50, 25, "请多关照，指挥官。"),
        ("N", "奥马哈", 10, 50, 25, "好嘞！今天去哪里巡逻呢？"), ("N", "卡辛", 10, 50, 25, "哈啊……好想一直在宅在家里啊……"),
        ("N", "唐斯", 10, 50, 25, "要来一场痛快的大爆炸吗！"), ("N", "罗利", 10, 50, 25, "学习和战斗，我都会努力的！"),
        ("R", "拉菲", 4, 120, 60, "拉菲……好困……指挥官，要一起睡觉吗？"), ("R", "绫波", 4, 120, 60, "鬼神绫波，参上……desu。"),
        ("R", "标枪", 4, 120, 60, "标枪，充满活力地登场！"), ("R", "菲尼克斯", 4, 120, 60, "不死鸟的火力，可别小看了！"),
        ("R", "波特兰", 4, 120, 60, "印第酱今天也是天下第一可爱！"), ("R", "宾夕法尼亚", 4, 120, 60, "准备好迎接粉碎性的打击了吗？"),
        ("SR", "海伦娜", 2, 300, 150, "SG雷达已锁定……指挥官，请指示。"), ("SR", "独角兽", 2, 300, 150, "哥哥……优酱说想和你玩！"),
        ("SR", "克利夫兰", 2, 300, 150, "嘿！我是克利夫兰，叫我克利夫兄贵也行哦！"), ("SR", "海伦娜·META", 2, 300, 150, "过去的一切早已沉寂，现在由我来接管战斗。"),
        ("SR", "雪风", 2, 300, 150, "雪风大人的运势可是无敌的 nanoda！"), ("SR", "天狼星", 2, 300, 150, "请尽情使用我这把做功不纯的剑吧，我的骄傲。"),
        ("SSR", "企业", 0.4, 600, 300, "Enterprise, engage! 叫我企业就好。"), ("SSR", "胡德", 0.4, 600, 300, "优雅，是作为皇家淑女的第一要义。"),
        ("SSR", "赤城", 0.4, 700, 350, "啊啊……指挥官大人的味道……好想把你锁进仓库里……"), ("SSR", "俾斯麦", 0.4, 600, 300, "为了铁血的荣光！"),
        ("SSR", "阿芙乐尔", 0.3, 600, 300, "愿曙光照亮我们的航道。"), ("SSR", "四万十", 0.4, 600, 300, "龙神大人庇佑着这片海域呢~"),
        ("SSR", "提尔皮茨", 0.4, 600, 300, "寂寞的北方女王……今天也为你而战。"), ("SSR", "英仙座", 0.4, 600, 300, "治愈的羽翼，随时为你张开。"),
        ("SSR", "科本斯", 0.4, 600, 300, "黑翼之鸟，降临于此！"),
        ("海上传奇", "信浓", 0.05, 1500, 800, "妾身……乃信浓……梦境与现实的边界，皆由你决断……"), ("海上传奇", "新泽西", 0.05, 1500, 800, "Honey~ 最大的黑龙——新泽西打捞成功！惊喜吗？"),
        ("海上传奇", "武藏", 0.05, 1500, 800, "吾乃武藏。指挥官，尽情依靠吾吧。"), ("海上传奇", "Z52", 0.05, 1500, 800, "最新锐的驱逐技术，可不是开玩笑的！"),
        ("海上传奇", "马耳他", 0.05, 1500, 800, "日不落的空中堡垒，马耳他向您报到。"), ("海上传奇", "纳希莫夫海军上阵", 0.05, 1500, 800, "极地的寒冰与烈火，将吞噬一切敌人。"),
        ("海上传奇", "阿尔萨斯", 0.05, 1500, 800, "守护荣光与圣裁，阿尔萨斯参上！"), ("海上传奇", "莫加多尔", 0.05, 1500, 800, "嘿嘿……想要看我疯狂的一面吗？"),
        ("海上传奇", "拉斐尔", 0.05, 1500, 800, "大天使的祝福，赐予有准备的灵魂。"), ("海上传奇", "金狮", 0.025, 1500, 800, "皇家荷兰的咆哮，在战场上震慑四方！"),
        ("海上传奇", "瓦尔帕莱索", 0.025, 1500, 800, "跨越风暴的海上要塞，在此展现真正的姿态！")
    ]

    def __init__(self, data_manager):
        self.data_mgr = data_manager
        self.common_pool = []
        self._refill_common_pool()
        self.guess_game_sessions = {}
        self.blackjack_sessions = {}

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
                buttons.append({
                    "id": f"btn_{row_idx}_{btn_idx}",
                    "render_data": {
                        "label": btn.get("label", "按钮"),
                        "visited_label": btn.get("label", "按钮"),
                        "style": 1  # 默认蓝色高亮样式
                    },
                    "action": {
                        "type": 2,  # 设置输入框内容并直接发送
                        "permission": {"type": 2},  # 所有人均可使用
                        "data": btn.get("data", "")
                    }
                })
            rows.append({"buttons": buttons})
            
        return {"content": {"rows": rows}}

    @classmethod
    def _msg(cls, content: str, buttons: list = None) -> dict:
        """msg_type = 2: Markdown + Keyboard"""
        res = {
            "msg_type": 2,
            "content": content
        }
        if buttons:
            res["keyboard"] = cls._build_qq_keyboard(buttons)
        return res

    @staticmethod
    def _img_msg(url_or_path: str, content: str = "") -> dict:
        """msg_type = 7: 富媒体 / 图片"""
        return {
            "msg_type": 7,
            "url": url_or_path,
            "file_path": url_or_path,
            "content": content
        }

    @staticmethod
    def _card_msg(title: str, description: str, pic_url: str = "", jump_url: str = "") -> dict:
        """msg_type = 8: 卡片消息"""
        return {
            "msg_type": 8,
            "card": {
                "content": {
                    "title": title,
                    "description": description,
                    "pic_url": pic_url,
                    "url": jump_url
                }
            }
        }
    # =======================================================================

    @staticmethod
    def calculate_level(exp: int) -> int:
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

    def handle_command(self, cmd: str, parts: list, sender_openid: str) -> dict:
        arg = parts[1] if len(parts) > 1 else ""

        # 默认底栏导航按钮
        default_btns = [
            [{"label": "⚓ 单抽打捞", "data": "#打捞"}, {"label": "🚀 十连打捞", "data": "#打捞 10"}],
            [{"label": "🎣 去钓鱼", "data": "#钓鱼"}, {"label": "🎒 查资产", "data": "#船坞"}, {"label": "🔮 算运势", "data": "#运势"}],
            [{"label": "🏆 排行榜", "data": "#排行榜"}, {"label": "🎰 老虎机", "data": "#老虎机"}]
        ]

        if cmd in ["帮助", "help"]:
            help_md = (
                "### 🤖 指令交互中心\n"
                "> 点击下方按钮或直接发送对应指令即可参与交互：\n\n"
                "* **基础功能**：`#打捞` | `#出击@某人` | `#钓鱼` | `#船坞` | `#运势`\n"
                "* **小游戏区**：`#猜数字` | `#21点` | `#猜拳` | `#老虎机` | `#赛跑`"
            )
            return self._msg(help_md, default_btns)

        cmd_map = {
            "name": lambda: self.set_user_name(sender_openid, " ".join(parts[1:]).strip()) if len(parts) > 1 else self._msg("⚠️ 请输入名称，例如：`#name 阿斯兰`"),
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
            "石头剪刀布": lambda: self.play_rps(sender_openid, arg),
            "rps": lambda: self.play_rps(sender_openid, arg),
            "老虎机": lambda: self.play_slot_machine(sender_openid),
            "slot": lambda: self.play_slot_machine(sender_openid),
            "拉霸": lambda: self.play_slot_machine(sender_openid),
            "赛跑": lambda: self.play_ship_race(sender_openid, arg),
            "race": lambda: self.play_ship_race(sender_openid, arg),
            "赛船": lambda: self.play_ship_race(sender_openid, arg),
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

    def _get_user_data(self, sender_openid: str):
        return self.data_mgr.user_stats.setdefault(sender_openid, {
            "name": f"指挥官_{sender_openid[:4]}", "coins": 0, "exp": 0,
            "counts": 0, "salvage_counts": 0, "attack_counts": 0,
            "fish_bag": {}, "dock": {}
        })

    def set_user_name(self, sender_openid: str, name: str) -> dict:
        if len(name) > 12: return self._msg("❌ 名称长度不能超过 12 个字符。")
        self._get_user_data(sender_openid)["name"] = name
        self.data_mgr.save_data()
        return self._msg(f"✅ 个人名称已成功修改为：**【{name}】**！")

    def play_salvage(self, sender_openid: str, count: int = 1) -> dict:
        user_data = self._get_user_data(sender_openid)
        user_data["salvage_counts"] = user_data.get("salvage_counts", 0) + count

        drawn = self._pop_ships_from_pool(count)
        total_coins, total_exp = sum(s[2] for s in drawn), sum(s[3] for s in drawn)

        for _, ship_name, _, _, _ in drawn:
            user_data["dock"][ship_name] = user_data["dock"].get(ship_name, 0) + 1

        user_data["coins"] += total_coins
        user_data["exp"] += total_exp
        self.data_mgr.save_data()

        btns = [[{"label": "⚓ 再打捞一次", "data": f"#打捞 {count}"}, {"label": "🎒 查看船坞", "data": "#船坞"}]]

        if count == 1:
            rarity, ship_name, _, _, quote = drawn[0]
            title = "### ⚓ 打捞成功！"
            if rarity == "海上传奇": title = "### 🌟⚡ 彩光大破！海上传奇降临！ ⚡🌟"
            elif rarity == "SSR": title = "### ✨ 金色闪耀！超稀有舰船回应！ ✨"
            
            md = (f"{title}\n"
                  f"* **获得舰船**：[{self.RARITY_TAGS[rarity]}] **{ship_name}**\n"
                  f"* **台词**：“*{quote}*”\n"
                  f"> 💰 **收益**：金币 `+{total_coins}` | 经验 `+{total_exp}`\n"
                  f"> 📊 **资产**：金币 `{user_data['coins']}` | 经验 `{user_data['exp']}`")
            return self._msg(md, btns)

        has_ur = any(s[0] == "海上传奇" for s in drawn)
        has_ssr = any(s[0] == "SSR" for s in drawn)
        header = "### 🌟🌈 十连彩光！！海上传奇降临！" if has_ur else ("### ✨🟡 十连金光！获得超稀有舰船！" if has_ssr else "### ⚓ 十连打捞报告")

        ship_lines = [
            f"* [{self.RARITY_TAGS[s[0]]}] **{s[1]}**" + (f"\n  > “*{s[4]}*”" if s[0] in ["SSR", "海上传奇"] else "")
            for s in drawn
        ]
        md = f"{header}\n\n" + "\n".join(ship_lines) + f"\n\n> 💰 **总收益**：金币 `+{total_coins}` | 经验 `+{total_exp}`\n> 📊 **当前总计**：金币 `{user_data['coins']}` | 经验 `{user_data['exp']}`"
        return self._msg(md, btns)

    def play_attack(self, sender_openid: str, target_str: str) -> dict:
        user_data = self._get_user_data(sender_openid)
        user_data["attack_counts"] = user_data.get("attack_counts", 0) + 1
        my_power = self.calculate_user_power(user_data["dock"])

        clean_target = target_str.replace("@", "").strip()
        target_data = next((ud for uid, ud in self.data_mgr.user_stats.items() if uid != sender_openid and (clean_target in ud.get("name", "") or clean_target in uid)), None)

        if target_data:
            target_name, target_power = target_data.get("name", "未知目标"), self.calculate_user_power(target_data.get("dock", {}))
        else:
            target_name, target_power = clean_target or "神秘黑飞跃舰队", max(100, int(my_power * random.uniform(0.8, 1.2)))

        if my_power >= target_power:
            chosen = random.choice([s for s in self.SALVAGE_POOL if s[0] in ["N", "R", "SR"]])
            coins, exp = random.randint(300, 800), random.randint(150, 400)
            user_data["dock"][chosen[1]] = user_data["dock"].get(chosen[1], 0) + 1
            user_data["coins"] += coins
            user_data["exp"] += exp
            self.data_mgr.save_data()
            md = (f"### ⚔️ 出击大捷！\n"
                  f"* **对阵双方**：`{user_data['name']}` ({my_power} PT) **VS** `{target_name}` ({target_power} PT)\n"
                  f"* **战果**：🎉 **成功克敌制胜！**\n"
                  f"* **捕获**：[{chosen[0]}] **{chosen[1]}**\n"
                  f"> 💰 **战利品**：金币 `+{coins}` | 经验 `+{exp}`")
        else:
            lost = random.randint(100, 300)
            user_data["coins"] = max(0, user_data["coins"] - lost)
            self.data_mgr.save_data()
            md = (f"### 💥 出击受挫！\n"
                  f"* **对阵双方**：`{user_data['name']}` ({my_power} PT) **VS** `{target_name}` ({target_power} PT)\n"
                  f"* **战果**：😭 **战力不敌惨遭击退！**\n"
                  f"> 💸 **损失**：遗失了 `{lost}` 金币 *(剩余 `{user_data['coins']}`)*")
        return self._msg(md)

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
        self.data_mgr.save_data()

        prefixes = {
            "junk": ("🗑️ 哎呀，好像钩到了什么假东西...", f"钓到了 **【{item_name}】** ({weight}kg)！"),
            "legend": ("💥 杆子差点折断！出现了不可思议的巨物！", f"捕获了传说中的 **【{item_name}】** (重达 `{weight}kg`)！"),
            "box": ("✨ 啪嗒！打捞上了一个带有古老纹路的宝箱！", f"得到了 **【{item_name}】**！")
        }
        prefix, detail = prefixes.get(item_type, ("🌊 水花四溅！鱼儿上钩了！", f"钓到了 **【{item_name}】** ({weight}kg)！"))
        
        md = (f"{prefix}\n"
              f"* **结果**：{detail}\n"
              f"> 💰 **收益**：金币 `+{coins}` | 经验 `+{exp}` *(当前金币: `{user_data['coins']}`)*")
        btns = [[{"label": "🎣 再次挥竿", "data": "#钓鱼"}, {"label": "🐟 查看鱼库", "data": "#背包"}]]
        return self._msg(md, btns)

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
        self.data_mgr.save_data()

        md = (f"### 🎉 恭喜猜中！\n"
              f"* **正确答案**：`{target}`\n"
              f"* **总共尝试**：`{attempts}` 次\n"
              f"> 💰 **奖励**：金币 `+{coins}` | 经验 `+{exp}`")
        return self._msg(md)

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
                self.data_mgr.save_data()
                return self._msg(f"### 💥 爆牌！\n* **最终手牌**：`{' '.join(p_cards)}` (`{p_score}`点)\n> 💸 扣除金币 `{lost}` *(当前: `{user_data['coins']}`)*")
            
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

        self.data_mgr.save_data()
        return self._msg(md, [[{"label": "🎮 再来一局", "data": "#21点"}]])

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
        self.data_mgr.save_data()

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
        self.data_mgr.save_data()

        # 注意：此处去除了可能引发 40011000 的 text 高亮关键字，采用标准纯文本区块格式
        md = (f"### 🎰 拉霸老虎机\n"
              f"```\n[ {r1} | {r2} | {r3} ]\n```\n"
              f"{tip}\n"
              f"> 💰 **结算**：金币 `+{coins}` *(门票-50)* | 经验 `+{exp}`\n"
              f"> 📊 **剩余**：`{user_data['coins']}` 金币")
        btns = [[{"label": "🎰 再拉一次", "data": "#老虎机"}]]
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

        self.data_mgr.save_data()
        md = f"### 🏁 赛船比赛结束\n**📊 比赛成绩榜**：\n{rank_str}\n\n{res}"
        return self._msg(md, race_btns)

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
        if not self.data_mgr.user_stats:
            return self._msg("🏆 暂时还没有人参与排行！")

        stats = self.data_mgr.user_stats.items()
        
        p_rank = sorted(stats, key=lambda x: self.calculate_user_power(x[1].get("dock", {})), reverse=True)[:5]
        p_lines = [f"{i}. **{s.get('name', uid[:6])}** - `{self.calculate_user_power(s.get('dock', {}))} PT`" for i, (uid, s) in enumerate(p_rank, 1)]

        e_rank = sorted(stats, key=lambda x: x[1]["exp"], reverse=True)[:5]
        e_lines = [f"{i}. **{s.get('name', uid[:6])}** - `Lv.{self.calculate_level(s['exp'])}` (*{s['exp']} exp*)" for i, (uid, s) in enumerate(e_rank, 1)]

        md = ("### 🏆 指挥官综合排行榜\n\n"
              "#### ⚔️ 主力战力榜 TOP 5\n" + "\n".join(p_lines) + "\n\n"
              "#### 🎖️ 等级经验榜 TOP 5\n" + "\n".join(e_lines))
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
