import random
import datetime
import hashlib

class GameSystem:
    # 舰船稀有度及战力配置表
    SHIP_RARITY_MAP = {
        "小天鹅": ("N", 20), "利安得": ("N", 20), "奥马哈": ("N", 20),
        "拉菲": ("R", 80), "绫波": ("R", 80), "标枪": ("R", 80),
        "海伦娜": ("SR", 300), "独角兽": ("SR", 300), "克利夫兰": ("SR", 300),
        "企业": ("SSR", 1000), "胡德": ("SSR", 1000), "赤城": ("SSR", 1000),
        "信浓": ("海上传奇", 5000), "新泽西": ("海上传奇", 5000), "武藏": ("海上传奇", 5000)
    }

    # 钓鱼物品池配置表
    FISHING_POOL = [
        ("junk", "破旧的破鞋", 20, 1, 1, 0.2, 0.8),
        ("junk", "缠人的水草", 20, 1, 1, 0.1, 0.5),
        ("fish", "小鲫鱼", 25, 10, 5, 0.3, 1.2),
        ("fish", "大鲤鱼", 15, 25, 12, 1.5, 4.5),
        ("fish", "肥美的大鲢鱼", 10, 40, 20, 3.0, 8.0),
        ("fish", "金光闪闪的金鱼", 5, 80, 40, 0.2, 0.6),
        ("legend", "深海大白鲨", 3, 200, 100, 150.0, 400.0),
        ("box", "沉没的神秘宝箱", 2, 350, 150, 5.0, 10.0),
    ]

    # 打捞舰船池配置表
    SALVAGE_POOL = [
        ("N", "小天鹅", 15, 10, 5, "指挥官，今天也要加油哦！"),
        ("N", "利安得", 15, 10, 5, "请多关照，指挥官。"),
        ("N", "奥马哈", 20, 10, 5, "好嘞！今天去哪里巡逻呢？"),
        ("R", "拉菲", 10, 30, 15, "拉菲……好困……指挥官，要一起睡觉吗？"),
        ("R", "绫波", 10, 30, 15, "鬼神绫波，参上……desu。"),
        ("R", "标枪", 10, 30, 15, "标枪，充满活力地登场！"),
        ("SR", "海伦娜", 5, 80, 40, "SG雷达已锁定……指挥官，请指示。"),
        ("SR", "独角兽", 5, 80, 40, "哥哥……优酱说想和你玩！"),
        ("SR", "克利夫兰", 5, 80, 40, "嘿！我是克利夫兰，叫我克利夫兄贵也行哦！"),
        ("SSR", "企业", 1.5, 200, 100, "Enterprise, engage! 叫我企业就好。"),
        ("SSR", "胡德", 1.5, 200, 100, "优雅，是作为皇家淑女的第一要义。"),
        ("SSR", "赤城", 1.0, 250, 120, "啊啊……指挥官大人的味道……好想把你锁进仓库里……"),
        ("海上传奇", "信浓", 0.3, 500, 300, "妾身……乃信浓……梦境与现实的边界，皆由你决断……"),
        ("海上传奇", "新泽西", 0.3, 500, 300, "Honey~ 最大的黑龙——新泽西打捞成功！惊喜吗？"),
        ("海上传奇", "武藏", 0.4, 500, 300, "吾乃武藏。指挥官，尽情依靠吾吧。")
    ]

    def __init__(self, data_manager):
        self.data_mgr = data_manager

    def handle_command(self, cmd: str, parts: list, sender_openid: str) -> str:
        """接收 main.py 路由过来的非系统级指令并统一处理"""
        if cmd in ["帮助", "help"]:
            return ("🤖 【常用指令列表】\n#打捞 - 舰船打捞 ⚓\n#钓鱼 - 挥竿钓鱼小游戏 🎣\n"
                    "#船坞 / #背包 - 查看个人资产与战力\n#排行榜 / #战力榜 - 查看战力与经验排行榜\n"
                    "#ping - 检查机器人状态\n#运势 - 获取今日专属运势\n#roll [上限] - 掷骰子\n#时间 - 查看服务器时间")
        elif cmd in ["打捞", "搜救", "捞船"]:
            return self.play_salvage(sender_openid)
        elif cmd in ["钓鱼", "fish"]:
            return self.play_fishing(sender_openid)
        elif cmd in ["船坞", "背包", "鱼库", "仓库"]:
            return self.get_user_assets(sender_openid)
        elif cmd in ["排行榜", "钓鱼排名", "打捞排名", "战力榜", "舰队榜"]:
            return self.get_rank()
        elif cmd in ["运势", "抽签"]:
            return self.get_fortune(sender_openid)
        elif cmd == "roll":
            max_num = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 100
            return f"🎲 掷骰子结果 (1-{max(1, max_num)})：{random.randint(1, max(1, max_num))}"
        elif cmd in ["时间", "time"]:
            return f"🕒 当前服务器时间：\n{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        return f"未知指令：#{cmd}\n输入 #帮助 查看指令列表。"

    def _get_user_data(self, sender_openid: str):
        if sender_openid not in self.data_mgr.user_stats:
            self.data_mgr.user_stats[sender_openid] = {
                "coins": 0,
                "exp": 0,
                "counts": 0,
                "salvage_counts": 0,
                "fish_bag": {},
                "dock": {}
            }
        return self.data_mgr.user_stats[sender_openid]

    def calculate_user_power(self, dock: dict) -> int:
        total_power = 0
        for ship_name, count in dock.items():
            if ship_name in self.SHIP_RARITY_MAP:
                _, power_val = self.SHIP_RARITY_MAP[ship_name]
                total_power += power_val * count
        return total_power

    def evaluate_luck(self, salvage_counts: int, dock: dict) -> str:
        if salvage_counts < 5:
            return "尚在观望 (打捞次数不足5次)"

        ssr_ur_count = sum(count for ship_name, count in dock.items() 
                           if ship_name in self.SHIP_RARITY_MAP and self.SHIP_RARITY_MAP[ship_name][0] in ["SSR", "海上传奇"])
        ur_count = sum(count for ship_name, count in dock.items() 
                       if ship_name in self.SHIP_RARITY_MAP and self.SHIP_RARITY_MAP[ship_name][0] == "海上传奇")

        rate = (ssr_ur_count / salvage_counts) * 100

        if ur_count >= 2 or rate >= 20.0:
            return f"👑 欧皇本皇 (高阶舰船率 {rate:.1f}%)"
        elif rate >= 12.0:
            return f"✨ 欧洲人 (高阶舰船率 {rate:.1f}%)"
        elif rate >= 5.0:
            return f"⚓ 亚洲平民 (高阶舰船率 {rate:.1f}%)"
        elif rate >= 2.0:
            return f"🌧️ 非洲酋长 (高阶舰船率 {rate:.1f}%)"
        else:
            return f"🗿 纯血非酋 (高阶舰船率 {rate:.1f}%)"

    def play_fishing(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        user_data["counts"] += 1

        items, weights = zip(*[((item[0], item[1], item[3], item[4], item[5], item[6]), item[2]) for item in self.FISHING_POOL])
        chosen = random.choices(items, weights=weights, k=1)[0]
        item_type, item_name, base_coin, base_exp, min_w, max_w = chosen

        weight = round(random.uniform(min_w, max_w), 2)
        multiplier = max(1.0, weight / min_w) if item_type == "fish" else 1.0
        earned_coins = int(base_coin * multiplier)
        earned_exp = int(base_exp * multiplier)

        user_data["coins"] += earned_coins
        user_data["exp"] += earned_exp
        user_data["fish_bag"][item_name] = user_data["fish_bag"].get(item_name, 0) + 1

        self.data_mgr.save_data()

        if item_type == "junk":
            prefix, detail = "🗑️ 哎呀，好像钩到了什么假东西...", f"钓到了 【{item_name}】 ({weight}kg)！"
        elif item_type == "legend":
            prefix, detail = "💥 杆子差点折断！出现了不可思议的巨物！", f"捕获了传说中的 【{item_name}】 (重达 {weight}kg)！"
        elif item_type == "box":
            prefix, detail = "✨ 啪嗒！打捞上了一个带有古老纹路的宝箱！", f"得到了 【{item_name}】！"
        else:
            prefix, detail = "🌊 水花四溅！鱼儿上钩了！", f"钓到了 【{item_name}】 ({weight}kg)！"

        return (
            f"{prefix}\n"
            f"🎯 结果：{detail}\n"
            f"💰 收益：金币 +{earned_coins} | 经验 +{earned_exp}\n"
            f"📊 资产：现有金币 {user_data['coins']} | 累积经验 {user_data['exp']}"
        )

    def play_salvage(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        user_data["salvage_counts"] = user_data.get("salvage_counts", 0) + 1

        rarity_colors = {
            "N": "⚪ 普通(N)", "R": "🔵 稀有(R)", "SR": "🟣 精锐(SR)",
            "SSR": "🟡 超稀有(SSR)", "海上传奇": "🌈 海上传奇"
        }

        ships, weights = zip(*[((s[0], s[1], s[3], s[4], s[5]), s[2]) for s in self.SALVAGE_POOL])
        chosen = random.choices(ships, weights=weights, k=1)[0]
        rarity, ship_name, earned_coins, earned_exp, quote = chosen

        user_data["coins"] += earned_coins
        user_data["exp"] += earned_exp
        user_data["dock"][ship_name] = user_data["dock"].get(ship_name, 0) + 1

        self.data_mgr.save_data()

        title_prefix = "⚓【打捞成功！】"
        if rarity == "海上传奇":
            title_prefix = "🌟⚡【彩光大破！超越常理的打捞！】⚡🌟"
        elif rarity == "SSR":
            title_prefix = "✨【金色金光！超稀有舰船回应了唤醒！】✨"

        return (
            f"{title_prefix}\n"
            f"🚢 舰船：[{rarity_colors[rarity]}] {ship_name}\n"
            f"💬 台词：“{quote}”\n"
            f"-------------------\n"
            f"💰 收益：金币 +{earned_coins} | 经验 +{earned_exp}\n"
            f"📊 现有：金币 {user_data['coins']} | 经验 {user_data['exp']}"
        )

    def get_user_assets(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        bag, dock = user_data["fish_bag"], user_data["dock"]
        salvage_counts = user_data.get("salvage_counts", 0)

        total_power = self.calculate_user_power(dock)
        luck_rating = self.evaluate_luck(salvage_counts, dock)

        bag_str = "\n".join([f"  - {k}: {v} 次" for k, v in bag.items()]) if bag else "  - 无"
        dock_str = "\n".join([f"  - {k}: {v} 艘" for k, v in dock.items()]) if dock else "  - 尚无舰船"

        return (
            f"🎒 【指挥官个人资源库】\n"
            f"💰 金币：{user_data['coins']} | 累积经验：{user_data['exp']}\n"
            f"⚔️ 舰队总战力：{total_power} PT\n"
            f"🎲 打捞欧非评级：{luck_rating}\n"
            f"📊 钓鱼：{user_data['counts']} 次 | 打捞：{salvage_counts} 次\n"
            f"-------------------\n"
            f"⚓ 舰队船坞：\n{dock_str}\n"
            f"-------------------\n"
            f"🐟 鱼类/水产图鉴：\n{bag_str}"
        )

    def get_rank(self) -> str:
        if not self.data_mgr.user_stats:
            return "🏆 暂时还没有人参与排行！"

        sorted_exp = sorted(self.data_mgr.user_stats.items(), key=lambda x: x[1]["exp"], reverse=True)[:5]
        exp_lines = [f"第 {i} 名: [{uid[:6]}...] - 经验:{s['exp']} | 金币:{s['coins']}" for i, (uid, s) in enumerate(sorted_exp, 1)]

        sorted_power = sorted(
            self.data_mgr.user_stats.items(),
            key=lambda x: self.calculate_user_power(x[1].get("dock", {})),
            reverse=True
        )[:5]
        power_lines = [f"第 {i} 名: [{uid[:6]}...] - 战力:{self.calculate_user_power(s.get('dock', {}))} PT | 舰船数:{sum(s.get('dock', {}).values())}" 
                       for i, (uid, s) in enumerate(sorted_power, 1)]

        return (
            f"🏆 【指挥官综合排行榜】\n\n"
            f"⭐ 【舰队战力排行榜 TOP 5】\n" + "\n".join(power_lines) + "\n\n"
            f"🎖️ 【经验积累排行榜 TOP 5】\n" + "\n".join(exp_lines)
        )

    def get_fortune(self, sender_openid: str) -> str:
        today_str = datetime.date.today().strftime("%Y%m%d")
        hash_value = int(hashlib.md5(f"{sender_openid}_{today_str}".encode('utf-8')).hexdigest(), 16)
        fortunes = [
            ("大吉 🌸", "运气爆棚，今天适合做重要的决定！"),
            ("中吉 🍀", "平平淡淡才是真，今天会有意想不到的惊喜。"),
            ("小吉 🌿", "小有收获，保持好心情。"),
            ("吉 🌟", "一切顺利，按部就班即可。"),
            ("末吉 🍂", "放平心态，多注意休息。"),
            ("凶 ⚠️", "今天宜低调做事，少说多看哦~")
        ]
        result_fortune, desc = fortunes[hash_value % len(fortunes)]
        return f"🔮 【今日运势】\n结果：{result_fortune}\n幸运指数：{(hash_value % 100) + 1}%\n点评：{desc}"
