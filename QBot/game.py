import random
import datetime
import hashlib

class GameSystem:
    # 稀有度权重与排序优先级表
    RARITY_ORDER = {"海上传奇": 1, "SSR": 2, "SR": 3, "R": 4, "N": 5}

    # 1. 舰船稀有度及基础战力配置表
    SHIP_RARITY_MAP = {
        # N 级 (基础战力 20)
        "小天鹅": ("N", 20), "利安得": ("N", 20), "奥马哈": ("N", 20),
        "卡辛": ("N", 20), "唐斯": ("N", 20), "罗利": ("N", 20),
        
        # R 级 (基础战力 80)
        "拉菲": ("R", 80), "绫波": ("R", 80), "标枪": ("R", 80),
        "菲尼克斯": ("R", 80), "波特兰": ("R", 80), "宾夕法尼亚": ("R", 80),
        
        # SR 级 (基础战力 300)
        "海伦娜": ("SR", 300), "独角兽": ("SR", 300), "克利夫兰": ("SR", 300),
        "海伦娜·META": ("SR", 300), "雪风": ("SR", 300), "天狼星": ("SR", 300),
        
        # SSR 级 (基础战力 1000)
        "企业": ("SSR", 1000), "胡德": ("SSR", 1000), "赤城": ("SSR", 1000),
        "俾斯麦": ("SSR", 1000), "阿芙乐尔": ("SSR", 1000), "四万十": ("SSR", 1000),
        "提尔皮茨": ("SSR", 1000), "英仙座": ("SSR", 1000), "科本斯": ("SSR", 1000),
        
        # 海上传奇 / UR 级 (基础战力 5000)
        "信浓": ("海上传奇", 5000), "新泽西": ("海上传奇", 5000), "武藏": ("海上传奇", 5000),
        "Z52": ("海上传奇", 5000), "马耳他": ("海上传奇", 5000), "纳希莫夫海军上将": ("海上传奇", 5000),
        "阿尔萨斯": ("海上传奇", 5000), "莫加多尔": ("海上传奇", 5000), "拉斐尔": ("海上传奇", 5000),
        "金狮": ("海上传奇", 5000), "瓦尔帕莱索": ("海上传奇", 5000)
    }

    # 钓鱼物品池配置表
    FISHING_POOL = [
        ("junk", "破旧的破鞋", 20, 1, 1, 0.2, 0.8),
        ("junk", "缠人的水草", 20, 1, 1, 0.1, 0.5),
        ("fish", "小鲫鱼", 25, 20, 10, 0.3, 1.2),
        ("fish", "大鲤鱼", 15, 50, 25, 1.5, 4.5),
        ("fish", "肥美的大鲢鱼", 10, 80, 40, 3.0, 8.0),
        ("fish", "金光闪闪的金鱼", 5, 160, 80, 0.2, 0.6),
        ("legend", "深海大白鲨", 3, 400, 200, 150.0, 400.0),
        ("box", "沉没的神秘宝箱", 2, 700, 300, 5.0, 10.0),
    ]

    # 打捞舰船基础数据池
    SALVAGE_POOL = [
        # N 级
        ("N", "小天鹅", 10, 50, 25, "指挥官，今天也要加油哦！"),
        ("N", "利安得", 10, 50, 25, "请多关照，指挥官。"),
        ("N", "奥马哈", 10, 50, 25, "好嘞！今天去哪里巡逻呢？"),
        ("N", "卡辛", 10, 50, 25, "哈啊……好想一直在宅在家里啊……"),
        ("N", "唐斯", 10, 50, 25, "要来一场痛快的大爆炸吗！"),
        ("N", "罗利", 10, 50, 25, "学习和战斗，我都会努力的！"),
        
        # R 级
        ("R", "拉菲", 4, 120, 60, "拉菲……好困……指挥官，要一起睡觉吗？"),
        ("R", "绫波", 4, 120, 60, "鬼神绫波，参上……desu。"),
        ("R", "标枪", 4, 120, 60, "标枪，充满活力地登场！"),
        ("R", "菲尼克斯", 4, 120, 60, "不死鸟的火力，可别小看了！"),
        ("R", "波特兰", 4, 120, 60, "印第酱今天也是天下第一可爱！"),
        ("R", "宾夕法尼亚", 4, 120, 60, "准备好迎接粉碎性的打击了吗？"),
        
        # SR 级
        ("SR", "海伦娜", 2, 300, 150, "SG雷达已锁定……指挥官，请指示。"),
        ("SR", "独角兽", 2, 300, 150, "哥哥……优酱说想和你玩！"),
        ("SR", "克利夫兰", 2, 300, 150, "嘿！我是克利夫兰，叫我克利夫兄贵也行哦！"),
        ("SR", "海伦娜·META", 2, 300, 150, "过去的一切早已沉寂，现在由我来接管战斗。"),
        ("SR", "雪风", 2, 300, 150, "雪风大人的运势可是无敌的 nanoda！"),
        ("SR", "天狼星", 2, 300, 150, "请尽情使用我这把做功不纯的剑吧，我的骄傲。"),
        
        # SSR 级
        ("SSR", "企业", 0.4, 600, 300, "Enterprise, engage! 叫我企业就好。"),
        ("SSR", "胡德", 0.4, 600, 300, "优雅，是作为皇家淑女的第一要义。"),
        ("SSR", "赤城", 0.4, 700, 350, "啊啊……指挥官大人的味道……好想把你锁进仓库里……"),
        ("SSR", "俾斯麦", 0.4, 600, 300, "为了铁血的荣光！"),
        ("SSR", "阿芙乐尔", 0.3, 600, 300, "愿曙光照亮我们的航道。"),
        ("SSR", "四万十", 0.4, 600, 300, "龙神大人庇佑着这片海域呢~"),
        ("SSR", "提尔皮茨", 0.4, 600, 300, "寂寞的北方女王……今天也为你而战。"),
        ("SSR", "英仙座", 0.4, 600, 300, "治愈的羽翼，随时为你张开。"),
        ("SSR", "科本斯", 0.4, 600, 300, "黑翼之鸟，降临于此！"),

        # UR 级
        ("海上传奇", "信浓", 0.05, 1500, 800, "妾身……乃信浓……梦境与现实的边界，皆由你决断……"),
        ("海上传奇", "新泽西", 0.05, 1500, 800, "Honey~ 最大的黑龙——新泽西打捞成功！惊喜吗？"),
        ("海上传奇", "武藏", 0.05, 1500, 800, "吾乃武藏。指挥官，尽情依靠吾吧。"),
        ("海上传奇", "Z52", 0.05, 1500, 800, "最新锐的驱逐技术，可不是开玩笑的！"),
        ("海上传奇", "马耳他", 0.05, 1500, 800, "日不落的空中堡垒，马耳他向您报到。"),
        ("海上传奇", "纳希莫夫海军上将", 0.05, 1500, 800, "极地的寒冰与烈火，将吞噬一切敌人。"),
        ("海上传奇", "阿尔萨斯", 0.05, 1500, 800, "守护荣光与圣裁，阿尔萨斯参上！"),
        ("海上传奇", "莫加多尔", 0.05, 1500, 800, "嘿嘿……想要看我疯狂的一面吗？"),
        ("海上传奇", "拉斐尔", 0.05, 1500, 800, "大天使的祝福，赐予有准备的灵魂。"),
        ("海上传奇", "金狮", 0.025, 1500, 800, "皇家荷兰的咆哮，在战场上震慑四方！"),
        ("海上传奇", "瓦尔帕莱索", 0.025, 1500, 800, "跨越风暴的海上要塞，在此展现真正的姿态！")
    ]

    def __init__(self, data_manager):
        self.data_mgr = data_manager
        # 初始化 200 艘舰船的随机公共卡池队列
        self.common_pool = []
        self._refill_common_pool()
        
        # 扩展小游戏的临时状态缓存
        self.guess_game_sessions = {}  # {openid: {"target": int, "attempts": int}}
        self.blackjack_sessions = {}   # {openid: {"player_cards": [], "dealer_cards": []}}

    def _generate_one_ship(self):
        """按概率预生成一艘船"""
        ships, weights = zip(*[((s[0], s[1], s[3], s[4], s[5]), s[2]) for s in self.SALVAGE_POOL])
        return random.choices(ships, weights=weights, k=1)[0]

    def _refill_common_pool(self):
        """确保公共卡池维持在 200 艘"""
        while len(self.common_pool) < 200:
            self.common_pool.append(self._generate_one_ship())

    def _pop_ships_from_pool(self, count: int) -> list:
        """从公共卡池头部顺序抽取舰船，抽完后自动在尾部补充"""
        drawn_ships = []
        for _ in range(count):
            ship = self.common_pool.pop(0)
            drawn_ships.append(ship)
        self._refill_common_pool()  # 补满至 200 艘
        return drawn_ships

    def calculate_level(self, exp: int) -> int:
        if exp <= 0:
            return 1
        return int((exp / 100) ** 0.5) + 1

    def calculate_user_power(self, dock: dict) -> int:
        """
        阶梯命座战力计算机制：
        0命(1艘): 100% | 1命(2艘): +20% (120%) | 2命(3艘): +40% (160%)
        3命(4艘): +10% (170%) | 4命(5艘及以上): +20% (190% 封顶)
        计算前 6 艘高战力舰船之和。
        """
        ship_powers = []
        for ship_name, count in dock.items():
            if ship_name in self.SHIP_RARITY_MAP:
                _, base_power = self.SHIP_RARITY_MAP[ship_name]
                
                if count <= 1:
                    multiplier = 1.0
                elif count == 2:
                    multiplier = 1.20
                elif count == 3:
                    multiplier = 1.60
                elif count == 4:
                    multiplier = 1.70
                else: # 5艘及以上达到 4 命上限
                    multiplier = 1.90
                
                power = int(base_power * multiplier)
                ship_powers.append(power)
        
        ship_powers.sort(reverse=True)
        return sum(ship_powers[:6])

    def evaluate_luck(self, salvage_counts: int, dock: dict) -> str:
        if salvage_counts < 5:
            return "尚在观望 (打捞不足 5 次)"

        actual_high_rarity = sum(
            count for ship_name, count in dock.items()
            if ship_name in self.SHIP_RARITY_MAP and self.SHIP_RARITY_MAP[ship_name][0] in ["SSR", "海上传奇"]
        )

        expected_count = salvage_counts * 0.045
        ratio = actual_high_rarity / expected_count if expected_count > 0 else 1.0

        if ratio >= 2.5:
            return f"👑 欧皇本皇 (实际 {actual_high_rarity} 艘 / 期望 {expected_count:.1f} 艘)"
        elif ratio >= 1.5:
            return f"✨ 欧洲人 (实际 {actual_high_rarity} 艘 / 期望 {expected_count:.1f} 艘)"
        elif ratio >= 0.8:
            return f"⚓ 亚洲平民 (实际 {actual_high_rarity} 艘 / 期望 {expected_count:.1f} 艘)"
        elif ratio >= 0.3:
            return f"🌧️ 非洲酋长 (实际 {actual_high_rarity} 艘 / 期望 {expected_count:.1f} 艘)"
        else:
            return f"🗿 纯血非酋 (实际 {actual_high_rarity} 艘 / 期望 {expected_count:.1f} 艘)"

    def handle_command(self, cmd: str, parts: list, sender_openid: str) -> str:
        if cmd in ["帮助", "help"]:
            return ("🤖 【常用指令列表】\n"
                    "#打捞 / #打捞 10 - 从公共卡池抽船 ⚓\n"
                    "#出击@某人 - 比对战力对决 ⚔️\n"
                    "#name [名称] - 修改个人名字 🏷️\n"
                    "#钓鱼 - 挥竿钓鱼小游戏 🎣\n"
                    "#猜数字 [数字/重置] - 猜数字小游戏 🔢\n"
                    "#21点 [要牌/停牌] - 21点扑克对决 ♠️\n"
                    "#猜拳 [石头/剪刀/布] - 快捷猜拳 ✂️\n"
                    "#老虎机 - 摇奖拉霸机 🎰\n"
                    "#赛跑 [1/2/3] - 选选手竞速比赛 🏃\n"
                    "#船坞 / #背包 - 查看资产与船坞\n"
                    "#排行榜 / #战力榜 - 综合排行榜 🏆\n"
                    "#运势 - 今日专属运势 🔮\n"
                    "#roll [上限] - 掷骰子 🎲\n"
                    "#时间 - 服务器时间 🕒")

        elif cmd == "name":
            if len(parts) > 1:
                new_name = " ".join(parts[1:]).strip()
                return self.set_user_name(sender_openid, new_name)
            return "⚠️ 请输入要设置的名称，例如：#name 指挥官阿斯兰"

        elif cmd in ["打捞", "搜救", "捞船"]:
            count = 10 if (len(parts) > 1 and parts[1] == "10") else 1
            return self.play_salvage(sender_openid, count=count)

        elif cmd.startswith("出击"):
            target_str = " ".join(parts[1:]) if len(parts) > 1 else ""
            return self.play_attack(sender_openid, target_str)

        elif cmd in ["钓鱼", "fish"]:
            return self.play_fishing(sender_openid)

        # 新增小游戏指令映射
        elif cmd in ["猜数字", "guess"]:
            arg = parts[1] if len(parts) > 1 else ""
            return self.play_guess_number(sender_openid, arg)

        elif cmd in ["21点", "blackjack"]:
            action = parts[1] if len(parts) > 1 else ""
            return self.play_blackjack(sender_openid, action)

        elif cmd in ["猜拳", "石头剪刀布", "rps"]:
            choice = parts[1] if len(parts) > 1 else ""
            return self.play_rps(sender_openid, choice)

        elif cmd in ["老虎机", "slot", "拉霸"]:
            return self.play_slot_machine(sender_openid)

        elif cmd in ["赛跑", "race", "赛船"]:
            choice = parts[1] if len(parts) > 1 else ""
            return self.play_ship_race(sender_openid, choice)

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
                "name": f"指挥官_{sender_openid[:4]}",
                "coins": 0,
                "exp": 0,
                "counts": 0,
                "salvage_counts": 0,
                "attack_counts": 0,
                "fish_bag": {},
                "dock": {}
            }
        return self.data_mgr.user_stats[sender_openid]

    def set_user_name(self, sender_openid: str, name: str) -> str:
        user_data = self._get_user_data(sender_openid)
        if len(name) > 12:
            return "❌ 名称长度不能超过 12 个字符。"
        user_data["name"] = name
        self.data_mgr.save_data()
        return f"✅ 个人名称已成功修改为：【{name}】！"

    def play_salvage(self, sender_openid: str, count: int = 1) -> str:
        """从 200 艘公共池队列中按顺序抽取"""
        user_data = self._get_user_data(sender_openid)
        user_data["salvage_counts"] = user_data.get("salvage_counts", 0) + count

        rarity_colors = {
            "N": "⚪ N", "R": "🔵 R", "SR": "🟣 SR",
            "SSR": "🟡 SSR", "海上传奇": "🌈 UR"
        }

        # 顺序抽取
        drawn_results = self._pop_ships_from_pool(count)

        total_coins = 0
        total_exp = 0
        ship_lines = []
        has_ur = False
        has_ssr = False

        for rarity, ship_name, earned_coins, earned_exp, quote in drawn_results:
            total_coins += earned_coins
            total_exp += earned_exp
            
            user_data["dock"][ship_name] = user_data["dock"].get(ship_name, 0) + 1
            ship_lines.append((rarity, ship_name, quote))

            if rarity == "海上传奇":
                has_ur = True
            elif rarity == "SSR":
                has_ssr = True

        user_data["coins"] += total_coins
        user_data["exp"] += total_exp
        self.data_mgr.save_data()

        # 格式化单抽文本
        if count == 1:
            rarity, ship_name, quote = ship_lines[0]
            title = "⚓【打捞成功！】"
            if rarity == "海上传奇":
                title = "🌟⚡【彩光大破！超越常理的打捞！】⚡🌟"
            elif rarity == "SSR":
                title = "✨【金色闪耀！超稀有舰船回应唤醒！】✨"

            return (
                f"{title}\n"
                f"🚢 获得舰船：[{rarity_colors[rarity]}] {ship_name}\n"
                f"💬 台词：“{quote}”\n"
                f"-------------------\n"
                f"💰 收益：金币 +{total_coins} | 经验 +{total_exp}\n"
                f"📊 现有：金币 {user_data['coins']} | 经验 {user_data['exp']}"
            )
        # 格式化十连文本 (针对 SSR/UR 打印台词)
        else:
            header = "⚓【十连打捞报告】⚓"
            if has_ur:
                header = "🌟🌈【十连彩光！！海上传奇降临！】🌈🌟"
            elif has_ssr:
                header = "✨🟡【十连金光！获得超稀有舰船！】🟡✨"

            formatted_ship_lines = []
            for rarity, ship_name, quote in ship_lines:
                line = f"• [{rarity_colors[rarity]}] {ship_name}"
                if rarity in ["SSR", "海上传奇"]:
                    line += f"\n  💬 “{quote}”"
                formatted_ship_lines.append(line)

            ship_details = "\n".join(formatted_ship_lines)
            return (
                f"{header}\n"
                f"-------------------\n"
                f"{ship_details}\n"
                f"-------------------\n"
                f"💰 总收益：金币 +{total_coins} | 经验 +{total_exp}\n"
                f"📊 现有：金币 {user_data['coins']} | 累积经验 {user_data['exp']}"
            )

    def play_attack(self, sender_openid: str, target_str: str) -> str:
        """出击比对战力对决逻辑"""
        user_data = self._get_user_data(sender_openid)
        user_data["attack_counts"] = user_data.get("attack_counts", 0) + 1
        my_power = self.calculate_user_power(user_data["dock"])

        # 查找目标玩家
        target_uid = None
        target_data = None
        clean_target = target_str.replace("@", "").strip()

        for uid, udata in self.data_mgr.user_stats.items():
            if uid != sender_openid and (clean_target in udata.get("name", "") or clean_target in uid):
                target_uid = uid
                target_data = udata
                break

        # 如果没找到特定目标，自动匹配战力相近的系统/玩家镜像
        if target_data:
            target_name = target_data.get("name", f"指挥官_{target_uid[:4]}")
            target_power = self.calculate_user_power(target_data.get("dock", {}))
        else:
            target_name = clean_target if clean_target else "神秘黑飞跃舰队"
            # 随机生成一个与玩家战力上下浮动 20% 的敌方战力
            target_power = max(100, int(my_power * random.uniform(0.8, 1.2)))

        # 战斗比对
        if my_power >= target_power: # 胜利
            # 低阶船池子选取
            low_ships = [s for s in self.SALVAGE_POOL if s[0] in ["N", "R", "SR"]]
            chosen = random.choice(low_ships)
            chosen_rarity, chosen_ship = chosen[0], chosen[1]
            
            earned_coins = random.randint(300, 800)
            earned_exp = random.randint(150, 400)

            user_data["dock"][chosen_ship] = user_data["dock"].get(chosen_ship, 0) + 1
            user_data["coins"] += earned_coins
            user_data["exp"] += earned_exp
            self.data_mgr.save_data()

            return (
                f"⚔️【出击大捷！】\n"
                f"👤 双方：{user_data['name']} (战力 {my_power}) VS {target_name} (战力 {target_power})\n"
                f"🎉 战果：成功克敌制胜！\n"
                f"🎁 捞获敌舰：[{chosen_rarity}] {chosen_ship}\n"
                f"💰 战利品：金币 +{earned_coins} | 经验 +{earned_exp}"
            )
        else: # 失败
            lost_coins = random.randint(100, 300)
            user_data["coins"] = max(0, user_data["coins"] - lost_coins)
            self.data_mgr.save_data()

            return (
                f"💥【出击受挫！】\n"
                f"👤 双方：{user_data['name']} (战力 {my_power}) VS {target_name} (战力 {target_power})\n"
                f"😭 战果：战力不敌惨遭击退！\n"
                f"💸 损失：撤退过程中遗失了 {lost_coins} 金币！\n"
                f"📊 现有金币：{user_data['coins']}"
            )

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

    # ==================== 新增小游戏实现 ====================

    def play_guess_number(self, sender_openid: str, arg: str) -> str:
        """1. 猜数字小游戏 (1-100)"""
        user_data = self._get_user_data(sender_openid)
        session = self.guess_game_sessions.get(sender_openid)

        if arg == "重置":
            self.guess_game_sessions[sender_openid] = {"target": random.randint(1, 100), "attempts": 0}
            return "🔄 猜数字游戏已重新开始！目标数字为 1-100 之间的整数，请输入 `#猜数字 [数字]` 进行猜测。"

        if not session:
            session = {"target": random.randint(1, 100), "attempts": 0}
            self.guess_game_sessions[sender_openid] = session

        if not arg or not arg.isdigit():
            return (f"🔢 【猜数字小游戏】\n"
                    f"系统已为你生成 1-100 之间的随机数。\n"
                    f"输入 `#猜数字 50` 进行猜测，输入 `#猜数字 重置` 开启新一局。")

        val = int(arg)
        session["attempts"] += 1
        target = session["target"]

        if val < target:
            return f"📉 太小了！你已经尝试了 {session['attempts']} 次。继续猜："
        elif val > target:
            return f"📈 太大了！你已经尝试了 {session['attempts']} 次。继续猜："
        else:
            attempts = session["attempts"]
            del self.guess_game_sessions[sender_openid]
            
            # 根据尝试次数给出奖励
            earned_coins = max(50, 500 - (attempts - 1) * 50)
            earned_exp = max(20, 200 - (attempts - 1) * 20)
            user_data["coins"] += earned_coins
            user_data["exp"] += earned_exp
            self.data_mgr.save_data()

            return (f"🎉 🎉 恭喜你猜中了！答案就是：{target}\n"
                    f"⏱️ 共尝试了 {attempts} 次！\n"
                    f"💰 结算奖励：金币 +{earned_coins} | 经验 +{earned_exp}\n"
                    f"📊 当前金币：{user_data['coins']}")

    def play_blackjack(self, sender_openid: str, action: str) -> str:
        """2. 21点扑克小游戏"""
        user_data = self._get_user_data(sender_openid)
        session = self.blackjack_sessions.get(sender_openid)

        def card_value(card):
            if card in ['J', 'Q', 'K']:
                return 10
            elif card == 'A':
                return 11
            return int(card)

        def calculate_score(cards):
            score = sum(card_value(c) for c in cards)
            num_aces = cards.count('A')
            while score > 21 and num_aces > 0:
                score -= 10
                num_aces -= 1
            return score

        cards_deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

        if not session or action not in ["要牌", "停牌", "hit", "stand"]:
            # 初始化对局
            p_cards = [random.choice(cards_deck), random.choice(cards_deck)]
            d_cards = [random.choice(cards_deck), random.choice(cards_deck)]
            self.blackjack_sessions[sender_openid] = {"player_cards": p_cards, "dealer_cards": d_cards}
            
            p_score = calculate_score(p_cards)
            return (f"♠️ 【21点桌游开局】\n"
                    f"🎴 你的手牌：{' '.join(p_cards)} (点数: {p_score})\n"
                    f"🃏 庄家明牌：{d_cards[0]} [暗牌]\n"
                    f"-------------------\n"
                    f"请输入 `#21点 要牌` 继续摸牌，或 `#21点 停牌` 进行比牌。")

        p_cards = session["player_cards"]
        d_cards = session["dealer_cards"]

        if action in ["要牌", "hit"]:
            p_cards.append(random.choice(cards_deck))
            p_score = calculate_score(p_cards)
            
            if p_score > 21:
                del self.blackjack_sessions[sender_openid]
                lost = random.randint(50, 150)
                user_data["coins"] = max(0, user_data["coins"] - lost)
                self.data_mgr.save_data()
                return (f"💥 【爆牌了！】\n"
                        f"🎴 你的手牌：{' '.join(p_cards)} (点数: {p_score})\n"
                        f"😭 超过21点直接爆牌输掉本局！\n"
                        f"💸 损失金币：{lost} | 当前金币：{user_data['coins']}")
            else:
                return (f"🎴 你要了一张牌：{' '.join(p_cards)} (点数: {p_score})\n"
                        f"输入 `#21点 要牌` 继续，或 `#21点 停牌` 结算。")

        elif action in ["停牌", "stand"]:
            del self.blackjack_sessions[sender_openid]
            p_score = calculate_score(p_cards)
            d_score = calculate_score(d_cards)

            # 庄家逻辑：小于17点强制补牌
            while d_score < 17:
                d_cards.append(random.choice(cards_deck))
                d_score = calculate_score(d_cards)

            msg = f"🎴 你的最终手牌：{' '.join(p_cards)} ({p_score}点)\n"
            msg += f"🃏 庄家的最终手牌：{' '.join(d_cards)} ({d_score}点)\n"
            msg += "-------------------\n"

            if d_score > 21 or p_score > d_score:
                earned_coins = random.randint(200, 400)
                earned_exp = random.randint(80, 150)
                user_data["coins"] += earned_coins
                user_data["exp"] += earned_exp
                msg += f"🎉 恭喜你赢了庄家！\n💰 收益：金币 +{earned_coins} | 经验 +{earned_exp}"
            elif p_score == d_score:
                msg += "⚖️ 平局！退还本场筹码。"
            else:
                lost = random.randint(100, 200)
                user_data["coins"] = max(0, user_data["coins"] - lost)
                msg += f"😭 庄家胜出！\n💸 损失：金币 -{lost}"

            self.data_mgr.save_data()
            return msg

    def play_rps(self, sender_openid: str, choice: str) -> str:
        """3. 石头剪刀布小游戏"""
        user_data = self._get_user_data(sender_openid)
        options = ["石头", "剪刀", "布"]
        
        if choice not in options:
            return "✂️ 请输入正确的选择，例如：`#猜拳 石头` | `#猜拳 剪刀` | `#猜拳 布`"

        bot_choice = random.choice(options)
        
        if choice == bot_choice:
            result = "平局 ⚖️"
            coin_change = 10
            exp_change = 5
        elif (choice == "石头" and bot_choice == "剪刀") or \
             (choice == "剪刀" and bot_choice == "布") or \
             (choice == "布" and bot_choice == "石头"):
            result = "胜利 🏆"
            coin_change = random.randint(80, 150)
            exp_change = random.randint(40, 80)
        else:
            result = "失败 💥"
            coin_change = -random.randint(30, 80)
            exp_change = 0

        user_data["coins"] = max(0, user_data["coins"] + coin_change)
        user_data["exp"] += exp_change
        self.data_mgr.save_data()

        return (f"✌️ 【石头剪刀布对决】\n"
                f"👤 你出：{choice}\n"
                f"🤖 对方出：{bot_choice}\n"
                f"-------------------\n"
                f"🎯 结果：{result}\n"
                f"💰 变动：金币 {'+' if coin_change >=0 else ''}{coin_change} | 经验 +{exp_change}\n"
                f"📊 现有金币：{user_data['coins']}")

    def play_slot_machine(self, sender_openid: str) -> str:
        """4. 老虎机 / 拉霸机"""
        user_data = self._get_user_data(sender_openid)
        cost = 50
        
        if user_data["coins"] < cost:
            return f"❌ 你的金币不足！摇一次老虎机需要 {cost} 金币。"

        user_data["coins"] -= cost
        symbols = ["🍋", "🍒", "🔔", "⭐", "💎", "🌈"]
        weights = [30, 25, 20, 15, 8, 2] # 概率权重

        reel1 = random.choices(symbols, weights=weights, k=1)[0]
        reel2 = random.choices(symbols, weights=weights, k=1)[0]
        reel3 = random.choices(symbols, weights=weights, k=1)[0]

        result_str = f"🎰 【拉霸老虎机】\n[ {reel1} | {reel2} | {reel3} ]\n-------------------\n"

        if reel1 == reel2 == reel3:
            if reel1 == "🌈":
                win_coins, win_exp = 2000, 1000
                result_str += "🌟🌈【SUPER JACKPOT！全屏彩虹特赏！】🌈🌟\n"
            elif reel1 == "💎":
                win_coins, win_exp = 1000, 500
                result_str += "✨💎【大奖爆发！获得钻石连击！】💎✨\n"
            else:
                win_coins, win_exp = 500, 200
                result_str += "🎉【三连大奖命中！】🎉\n"
        elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
            win_coins, win_exp = 100, 30
            result_str += "✨【二连对子！小有收获】✨\n"
        else:
            win_coins, win_exp = 0, 5
            result_str += "😭 遗憾未中奖，继续加油！\n"

        user_data["coins"] += win_coins
        user_data["exp"] += win_exp
        self.data_mgr.save_data()

        return (f"{result_str}"
                f"💰 结果结算：金币 +{win_coins} (扣除门票{cost}) | 经验 +{win_exp}\n"
                f"📊 剩余金币：{user_data['coins']}")

    def play_ship_race(self, sender_openid: str, choice: str) -> str:
        """5. 舰船赛跑竞技场"""
        user_data = self._get_user_data(sender_openid)
        racers = {
            "1": ("拉菲", "速度型", 0.3),  # 高上限高波动
            "2": ("企业", "稳定型", 0.1),  # 高稳定性
            "3": ("雪风", "爆发型", 0.5)   # 极高随机性
        }

        if choice not in racers:
            return ("🏃【赛船竞技场】\n"
                    "请选择你押注的赛艇选手：\n"
                    "1. 拉菲 (速度型 - 爆发极高但容易瞌睡)\n"
                    "2. 企业 (稳定型 - 航速稳定冲刺有力)\n"
                    "3. 雪风 (爆发型 - 极其看运气的奇迹选手)\n\n"
                    "指令：`#赛跑 1` 或 `#赛跑 2` 或 `#赛跑 3`")

        # 计算跑分
        scores = {}
        for num, (name, rtype, variance) in racers.items():
            base_speed = random.randint(60, 90)
            bonus = random.uniform(-variance, variance) * 50
            scores[num] = round(base_speed + bonus, 1)

        sorted_racers = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_num = sorted_racers[0][0]

        chosen_name = racers[choice][0]
        winner_name = racers[winner_num][0]

        rank_details = "\n".join([f"  第{i+1}名: {racers[n][0]} (成绩: {score}节)" for i, (n, score) in enumerate(sorted_racers)])

        if choice == winner_num:
            earned_coins = 300
            earned_exp = 150
            user_data["coins"] += earned_coins
            user_data["exp"] += earned_exp
            msg = f"🎉 猜中了！你押注的【{chosen_name}】勇夺桂冠！\n💰 获得奖励：金币 +{earned_coins} | 经验 +{earned_exp}"
        else:
            lost = 50
            user_data["coins"] = max(0, user_data["coins"] - lost)
            msg = f"😭 很遗憾！你押注的【{chosen_name}】未能夺冠，冠军是【{winner_name}】！\n💸 扣除报名费：{lost} 金币"

        self.data_mgr.save_data()

        return (f"🏁【海上赛跑比赛结束】\n"
                f"-------------------\n"
                f"📊 比赛成绩榜：\n{rank_details}\n"
                f"-------------------\n"
                f"{msg}\n"
                f"📊 当前金币：{user_data['coins']}")

    # =======================================================

    def get_user_assets(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        bag, dock = user_data["fish_bag"], user_data["dock"]
        salvage_counts = user_data.get("salvage_counts", 0)
        attack_counts = user_data.get("attack_counts", 0)

        user_level = self.calculate_level(user_data["exp"])
        top6_power = self.calculate_user_power(dock)
        luck_rating = self.evaluate_luck(salvage_counts, dock)

        # 船坞按 稀有度优先级 -> 数量（降序） 排序（隐藏命座）
        sorted_dock = sorted(
            dock.items(),
            key=lambda x: (
                self.RARITY_ORDER.get(self.SHIP_RARITY_MAP.get(x[0], ("N", 0))[0], 99),
                -x[1]
            )
        )

        dock_lines = [
            f"  - [{self.SHIP_RARITY_MAP.get(k, ('N', 0))[0]}] {k} x{v}"
            for k, v in sorted_dock
        ]
            
        dock_str = "\n".join(dock_lines) if dock_lines else "  - 尚无舰船"
        bag_str = "\n".join([f"  - {k}: {v} 次" for k, v in bag.items()]) if bag else "  - 无"

        return (
            f"🎒 【{user_data.get('name', '指挥官')} 的资源库】\n"
            f"🎖️ 军衔等级：Lv.{user_level}\n"
            f"💰 金币：{user_data['coins']} | 累积经验：{user_data['exp']}\n"
            f"⚔️ 主力舰队战力：{top6_power} PT\n"
            f"🎲 打捞欧非评级：{luck_rating}\n"
            f"📊 统计：钓鱼 {user_data['counts']} 次 | 打捞 {salvage_counts} 次 | 出击 {attack_counts} 次\n"
            f"-------------------\n"
            f"⚓ 舰队船坞 (按稀有度及数量排序)：\n{dock_str}\n"
            f"-------------------\n"
            f"🐟 鱼类/水产图鉴：\n{bag_str}"
        )

    def get_rank(self) -> str:
        if not self.data_mgr.user_stats:
            return "🏆 暂时还没有人参与排行！"

        # 经验排行
        sorted_exp = sorted(self.data_mgr.user_stats.items(), key=lambda x: x[1]["exp"], reverse=True)[:5]
        exp_lines = [
            f"第 {i} 名: {s.get('name', uid[:6])} - Lv.{self.calculate_level(s['exp'])} | 经验:{s['exp']}"
            for i, (uid, s) in enumerate(sorted_exp, 1)
        ]

        # 战力排行
        sorted_power = sorted(
            self.data_mgr.user_stats.items(),
            key=lambda x: self.calculate_user_power(x[1].get("dock", {})),
            reverse=True
        )[:5]
        power_lines = [
            f"第 {i} 名: {s.get('name', uid[:6])} - 战力:{self.calculate_user_power(s.get('dock', {}))} PT" 
            for i, (uid, s) in enumerate(sorted_power, 1)
        ]

        return (
            f"🏆 【指挥官综合排行榜】\n\n"
            f"⭐ 【主力舰队战力榜 TOP 5】\n" + "\n".join(power_lines) + "\n\n"
            f"🎖️ 【指挥官等级榜 TOP 5】\n" + "\n".join(exp_lines)
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
