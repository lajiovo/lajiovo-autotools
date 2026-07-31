import asyncio
import datetime
import hashlib
import json
import os
import random
import re
import sys
import botpy
from botpy import logging
from botpy.ext.cog_yaml import read
from botpy.message import GroupMessage

# 读取配置文件，不存在时使用备用配置
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
if os.path.exists(config_path):
    test_config = read(config_path)
    APP_ID = test_config["appid"]
    APP_SECRET = test_config["secret"]
else:
    APP_ID = ""
    APP_SECRET = ""

# 数据持久化文件路径（与脚本同目录）
DATA_FILE_PATH = os.path.join(os.path.dirname(__file__), "botdata.json")

_log = logging.get_logger()

# ==================== 安全的 SDK 兼容补丁 (Patch) ====================
try:
    from botpy.connection import ConnectionState
    if not hasattr(ConnectionState, "parse_group_message_create"):
        def parse_group_message_create(self, payload):
            _message = GroupMessage(self.api, payload.get("id", None), payload.get("d", {}))
            self._dispatch("group_message_create", _message)
        ConnectionState.parse_group_message_create = parse_group_message_create
except Exception:
    pass
# ====================================================================


class MyClient(botpy.Client):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 用于自动保存收到的第一个群 OpenID
        self.default_group_id = None
        
        # ---------------- 内存数据库 ----------------
        self.op_list = set()
        self.user_stats = {}

        # 启动时先加载持久化数据
        self.load_data()

    # ------------------ 数据持久化 (JSON) ------------------
    def load_data(self):
        """从同目录下的 botdata.json 读取数据"""
        default_op = "3A771844DA3A1352AA130920DA0F685A"
        if os.path.exists(DATA_FILE_PATH):
            try:
                with open(DATA_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.op_list = set(data.get("op_list", []))
                    self.user_stats = data.get("user_stats", {})
                    _log.info(f"✅ 成功从 {DATA_FILE_PATH} 加载数据！")
            except Exception as e:
                _log.error(f"❌ 读取 {DATA_FILE_PATH} 失败: {e}，将使用初始数据。")
                self.op_list = {default_op}
                self.user_stats = {}
        else:
            _log.info(f"ℹ️ 未找到 {DATA_FILE_PATH}，正在进行首次初始化...")
            self.op_list = {default_op}
            self.user_stats = {}

        # 确保默认的初始 OP 必定存在
        self.op_list.add(default_op)
        self.save_data()

    def save_data(self):
        """将当前数据写入 botdata.json"""
        try:
            data = {
                "op_list": list(self.op_list),
                "user_stats": self.user_stats
            }
            with open(DATA_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            _log.info(f"💾 数据已成功保存至 {DATA_FILE_PATH}")
        except Exception as e:
            _log.error(f"❌ 保存数据到 {DATA_FILE_PATH} 失败: {e}")

    async def on_ready(self):
        _log.info(f"robot 「{self.robot.name}」 已成功上线！")
        # 机器人上线后启动控制台后台监听任务
        asyncio.create_task(self.console_input_loop())

    # ------------------ 控制台手动发送消息逻辑 ------------------
    async def console_input_loop(self):
        """后台异步监听控制台手动输入"""
        loop = asyncio.get_running_loop()
        print("\n==================================================")
        print("【控制台手动发消息模式已就绪】")
        print("💡 提示: 收到第一个群消息后，将自动锁定该群作为默认发送目标。")
        print("1. 直接输入文字 -> 自动发送到默认群")
        print("2. 输入 <群OpenID> <发送内容> -> 发送到指定群")
        print("==================================================\n")

        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            line = line.strip()

            if not line:
                continue

            if line.lower() in ["exit", "quit"]:
                _log.info("接收到退出指令，保存数据并退出...")
                self.save_data()
                os._exit(0)

            target_group_id = None
            send_content = ""

            parts = line.split(maxsplit=1)

            # 如果用户输入的第一个参数看起来像指定的群 OpenID
            if len(parts) == 2 and len(parts[0]) > 20:
                target_group_id = parts[0]
                send_content = parts[1]
            else:
                # 默认模式：使用保存的第一个群消息 ID
                if not self.default_group_id:
                    print("❌ 当前尚未收到任何群消息，无法获取默认群 OpenID！请先在群里发一条消息，或手工指定群 ID。")
                    continue
                target_group_id = self.default_group_id
                send_content = line

            try:
                await self.api.post_group_message(
                    group_openid=target_group_id,
                    msg_type=0,
                    content=send_content
                )
                print(f"✅ [控制台已发送至群 {target_group_id}]: {send_content}")
                _log.info(f"[控制台主动发送] 目标群: {target_group_id} | 内容: {send_content}")
            except Exception as e:
                print(f"❌ 发送失败，原因: {e}")

    # ------------------ 玩家数据初始化 ------------------
    def _get_user_data(self, sender_openid: str):
        if sender_openid not in self.user_stats:
            self.user_stats[sender_openid] = {
                "coins": 0,
                "exp": 0,
                "counts": 0,
                "salvage_counts": 0,
                "fish_bag": {},
                "dock": {}
            }
        return self.user_stats[sender_openid]

    # ------------------ 钓鱼小游戏 ------------------
    def play_fishing(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        user_data["counts"] += 1

        pool = [
            ("junk", "破旧的破鞋", 20, 1, 1, 0.2, 0.8),
            ("junk", "缠人的水草", 20, 1, 1, 0.1, 0.5),
            ("fish", "小鲫鱼", 25, 10, 5, 0.3, 1.2),
            ("fish", "大鲤鱼", 15, 25, 12, 1.5, 4.5),
            ("fish", "肥美的大鲢鱼", 10, 40, 20, 3.0, 8.0),
            ("fish", "金光闪闪的金鱼", 5, 80, 40, 0.2, 0.6),
            ("legend", "深海大白鲨", 3, 200, 100, 150.0, 400.0),
            ("box", "沉没的神秘宝箱", 2, 350, 150, 5.0, 10.0),
        ]

        items, weights = zip(*[((item[0], item[1], item[3], item[4], item[5], item[6]), item[2]) for item in pool])
        chosen = random.choices(items, weights=weights, k=1)[0]
        item_type, item_name, base_coin, base_exp, min_w, max_w = chosen

        weight = round(random.uniform(min_w, max_w), 2)
        multiplier = max(1.0, weight / min_w) if item_type == "fish" else 1.0
        earned_coins = int(base_coin * multiplier)
        earned_exp = int(base_exp * multiplier)

        user_data["coins"] += earned_coins
        user_data["exp"] += earned_exp
        user_data["fish_bag"][item_name] = user_data["fish_bag"].get(item_name, 0) + 1

        # 更新后自动存盘
        self.save_data()

        if item_type == "junk":
            prefix = "🗑️ 哎呀，好像钩到了什么假东西..."
            detail = f"钓到了 【{item_name}】 ({weight}kg)！"
        elif item_type == "legend":
            prefix = "💥 杆子差点折断！出现了不可思议的巨物！"
            detail = f"捕获了传说中的 【{item_name}】 (重达 {weight}kg)！"
        elif item_type == "box":
            prefix = "✨ 啪嗒！打捞上了一个带有古老纹路的宝箱！"
            detail = f"得到了 【{item_name}】！"
        else:
            prefix = "🌊 水花四溅！鱼儿上钩了！"
            detail = f"钓到了 【{item_name}】 ({weight}kg)！"

        return (
            f"{prefix}\n"
            f"🎯 结果：{detail}\n"
            f"💰 收益：金币 +{earned_coins} | 经验 +{earned_exp}\n"
            f"📊 资产：现有金币 {user_data['coins']} | 累积经验 {user_data['exp']}"
        )

    # ------------------ 舰船打捞小游戏 ------------------
    def play_salvage(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        user_data["salvage_counts"] = user_data.get("salvage_counts", 0) + 1

        ship_pool = [
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

        rarity_colors = {
            "N": "⚪ 普通(N)",
            "R": "🔵 稀有(R)",
            "SR": "🟣 精锐(SR)",
            "SSR": "🟡 超稀有(SSR)",
            "海上传奇": "🌈 海上传奇"
        }

        ships, weights = zip(*[((s[0], s[1], s[3], s[4], s[5]), s[2]) for s in ship_pool])
        chosen = random.choices(ships, weights=weights, k=1)[0]
        rarity, ship_name, earned_coins, earned_exp, quote = chosen

        user_data["coins"] += earned_coins
        user_data["exp"] += earned_exp
        user_data["dock"][ship_name] = user_data["dock"].get(ship_name, 0) + 1

        # 更新后自动存盘
        self.save_data()

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

    # ------------------ 查看个人背包 / 船坞 ------------------
    def get_user_assets(self, sender_openid: str) -> str:
        user_data = self._get_user_data(sender_openid)
        bag = user_data["fish_bag"]
        dock = user_data["dock"]

        bag_str = "\n".join([f"  - {k}: {v} 次" for k, v in bag.items()]) if bag else "  - 无"
        dock_str = "\n".join([f"  - {k}: {v} 艘" for k, v in dock.items()]) if dock else "  - 尚无舰船"

        return (
            f"🎒 【指挥官个人资源库】\n"
            f"钓鱼次数：{user_data['counts']} 次 | 打捞次数：{user_data.get('salvage_counts', 0)} 次\n"
            f"当前金币：{user_data['coins']} | 总经验：{user_data['exp']}\n"
            f"-------------------\n"
            f"🐟 鱼类/水产图鉴：\n{bag_str}\n"
            f"-------------------\n"
            f"⚓ 舰队船坞：\n{dock_str}"
        )

    def get_rank(self) -> str:
        """全局经验排行榜"""
        if not self.user_stats:
            return "🏆 暂时还没有人参与钓鱼打捞排名！"

        sorted_users = sorted(self.user_stats.items(), key=lambda x: x[1]["exp"], reverse=True)[:5]
        rank_lines = []
        for idx, (uid, stats) in enumerate(sorted_users, 1):
            short_id = uid[:6] + "..." if len(uid) > 6 else uid
            rank_lines.append(f"第 {idx} 名: 用户[{short_id}] - 经验:{stats['exp']} | 金币:{stats['coins']} | 舰船数:{sum(stats['dock'].values())}")

        return "🏆 【指挥官综合排行榜 TOP 5】\n" + "\n".join(rank_lines)

    # ------------------ # 开头的群指令处理 ------------------
    async def process_command(self, content: str, sender_openid: str, raw_message: GroupMessage) -> str:
        cmd_text = content[1:].strip()
        parts = cmd_text.split()
        cmd = parts[0].lower() if parts else ""

        # 1. 帮助指令
        if cmd in ["帮助", "help"]:
            return (
                "🤖 【常用指令列表】\n"
                "#op @某人 - 赋予指定用户 OP 权限(限OP)\n"
                "#打捞 - 舰船打捞 ⚓\n"
                "#钓鱼 - 挥竿钓鱼小游戏 🎣\n"
                "#船坞 / #背包 / #鱼库 - 查看个人资产与搜集图鉴\n"
                "#排行榜 / #钓鱼排名 - 查看玩家排行榜 TOP5\n"
                "#帮助 / #help - 查看功能菜单\n"
                "#ping - 检查机器人状态\n"
                "#运势 - 获取今日专属运势\n"
                "#roll [上限] - 掷骰子（默认 1-100）\n"
                "#时间 - 查看当前服务器时间"
            )

        # 2. #hi 指令（隐藏彩蛋）
        elif cmd == "hi":
            if sender_openid in self.op_list:
                return "👑 欢迎，尊贵的管理员！当前系统运行正常，全局权限已就位。"
            else:
                return "👋 你好呀！今天也是充满活力的一天，快去试试 #钓鱼 或 #打捞 吧！"

        # 3. #op 指令（提权逻辑）
        elif cmd == "op":
            if sender_openid not in self.op_list:
                return "❌ 权限不足！只有现有的 OP 管理员才能执行此指令。"

            target_id = None
            mentions = getattr(raw_message, "mentions", [])
            if mentions:
                target_id = getattr(mentions[0], "member_openid", None) or getattr(mentions[0], "id", None)

            if not target_id:
                at_match = re.search(r"<@!([A-Za-z0-9]+)>", content)
                if at_match:
                    target_id = at_match.group(1)

            if not target_id and len(parts) > 1:
                target_id = parts[1].strip()

            if not target_id:
                return "⚠️ 请 @某人 或提供目标 OpenID，例如：`#op @用户`"

            target_id = target_id.upper()
            if target_id in self.op_list:
                return f"ℹ️ 用户 [{target_id[:6]}...] 本就已经是 OP 管理员。"

            self.op_list.add(target_id)
            self.save_data()  # 变更权限后存盘
            _log.info(f"[OP设置成功] 用户 {sender_openid} 已将 {target_id} 提权为 OP")
            return f"✅ 提权成功！用户 [{target_id[:6]}...] 已正式成为 OP 管理员。"

        # 4. 打捞
        elif cmd in ["打捞", "搜救", "捞船"]:
            return self.play_salvage(sender_openid)

        # 5. 钓鱼功能
        elif cmd in ["钓鱼", "fish"]:
            return self.play_fishing(sender_openid)

        # 6. 查看船坞/资产
        elif cmd in ["船坞", "背包", "鱼库", "仓库"]:
            return self.get_user_assets(sender_openid)

        # 7. 排行榜
        elif cmd in ["排行榜", "钓鱼排名", "打捞排名", "钓鱼榜"]:
            return self.get_rank()

        # 8. Ping 测试
        elif cmd == "ping":
            return "Pong! 机器人正常运行中 ⚡"

        # 9. 今日运势
        elif cmd in ["运势", "抽签"]:
            today_str = datetime.date.today().strftime("%Y%m%d")
            seed_source = f"{sender_openid}_{today_str}"
            hash_value = int(hashlib.md5(seed_source.encode('utf-8')).hexdigest(), 16)
            
            fortunes = [
                ("大吉 🌸", "运气爆棚，今天适合做重要的决定！"),
                ("中吉 🍀", "平平淡淡才是真，今天会有意想不到的惊喜。"),
                ("小吉 🌿", "小有收获，保持好心情。"),
                ("吉 🌟", "一切顺利，按部就班即可。"),
                ("末吉 🍂", "放平心态，多注意休息。"),
                ("凶 ⚠️", "今天宜低调做事，少说多看哦~")
            ]
            
            result_fortune, desc = fortunes[hash_value % len(fortunes)]
            luck_num = (hash_value % 100) + 1
            return f"🔮 【今日运势】\n结果：{result_fortune}\n幸运指数：{luck_num}%\n点评：{desc}"

        # 10. Roll 掷骰子
        elif cmd == "roll":
            max_num = 100
            if len(parts) > 1 and parts[1].isdigit():
                max_num = max(1, int(parts[1]))
            roll_val = random.randint(1, max_num)
            return f"🎲 掷骰子结果 (1-{max_num})：{roll_val}"

        # 11. 当前时间
        elif cmd in ["时间", "time"]:
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return f"🕒 当前服务器时间：\n{now_str}"

        # 未知的 # 指令
        else:
            return f"未知指令：#{cmd}\n输入 #帮助 查看支持的指令列表。"

    # ------------------ 群消息基础交互 ------------------
    async def _handle_group_msg(self, message: GroupMessage, event_name: str):
        content = getattr(message, "content", "").strip()
        group_id = getattr(message, "group_openid", "")
        msg_id = getattr(message, "id", "")
        author = getattr(message, "author", None)
        sender_openid = getattr(author, "member_openid", "未知用户") if author else "未知用户"
        
        # 统一大写处理，防止大小写敏感导致 OP 匹配失败
        sender_openid = sender_openid.upper()

        if not self.default_group_id and group_id:
            self.default_group_id = group_id
            print(f"\n🎯 [已抓取并锁定第一个群 OpenID]: {self.default_group_id}")
            print("👉 现在你可以直接在控制台输入消息回车，自动发送到该群！\n")

        _log.info(f"[{event_name}] 群聊消息 | 群ID: {group_id} | 发送者OpenID: {sender_openid} | 内容: {content}")

        if content.startswith("#"):
            reply_text = await self.process_command(content, sender_openid, message)
            try:
                await self.api.post_group_message(
                    group_openid=group_id,
                    msg_type=0,
                    msg_id=msg_id,
                    content=reply_text
                )
                _log.info(f"[指令响应] 已回复群 [{group_id}]:\n{reply_text}")
            except Exception as e:
                _log.error(f"指令回复失败: {e}")

    # ------------------ 事件监听 ------------------
    async def on_group_at_message_create(self, message: GroupMessage):
        """群聊 @ 机器人事件"""
        await self._handle_group_msg(message, "on_group_at_message_create")

    async def on_group_message_create(self, message: GroupMessage):
        """群聊普通消息事件"""
        await self._handle_group_msg(message, "on_group_message_create")


if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client = MyClient(intents=intents)
    client.run(appid=APP_ID, secret=APP_SECRET)
