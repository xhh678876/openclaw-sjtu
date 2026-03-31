#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上海交通大学食堂信息与菜单查询工具

功能：
  - 查询闵行校区各食堂基本信息（位置、营业时间、特色窗口）
  - 菜单查询（当前为静态数据，未来可接入动态源）
  - AI 友好的食堂推荐

调研发现：
  - 后勤保障部 (https://houqin.sjtu.edu.cn) 主要发布新闻和通知，无每日菜单接口
  - hq.sjtu.edu.cn 已跳转至 houqin.sjtu.edu.cn
  - 食堂菜单主要通过以下渠道获取：
    * 各食堂入口处的实体公告牌/电子屏
    * 「交我办」App 中的后勤服务模块
    * 各食堂窗口微信点餐小程序（部分窗口）
    * 「上海交通大学后勤」微信公众号（偶尔推送特色菜）
  - 未发现可直接爬取的公开菜单 API

数据来源：
  - 校园生活指南: https://ourhome.sjtu.edu.cn/article/1057
  - 后勤保障中心: https://houqin.sjtu.edu.cn
  - 校友网餐饮介绍等公开资料
"""

import sys
import json
import random
from datetime import datetime, date

# ============================================================
# 食堂数据 - 闵行校区
# 数据来源: 校园生活指南 + 后勤官网 + 公开分享
# ============================================================

CANTEENS = [
    {
        "name": "第一餐饮大楼",
        "short_name": "一餐",
        "campus": "闵行",
        "location": "西一区北面，靠近包玉刚图书馆",
        "hours": {
            "早餐": "6:30-9:00",
            "午餐": "11:00-13:00",
            "晚餐": "17:00-19:00",
        },
        "floors": {
            "1F": "学生大众餐厅",
            "2F": "教工餐厅、自选餐厅",
        },
        "windows": [
            "川味窗口", "陕西美食", "养生锅", "五芳斋", "糖水粥铺",
            "低脂低糖窗口", "无碘盐窗口",
        ],
        "nearby": ["清真餐厅", "麦当劳", "Timo咖啡", "思源面包", "蔬果店"],
        "features": ["早餐种类丰富", "有特殊饮食窗口（低脂/无碘盐）", "靠近包图，学习间隙吃饭方便"],
        "price_range": "8-20元",
        "rating": 4.0,
        "best_for": ["早餐", "特殊饮食需求", "快速用餐"],
        "popular_dishes": ["川味麻辣烫", "五芳斋粽子", "养生汤"],
    },
    {
        "name": "第二餐饮大楼",
        "short_name": "二餐",
        "campus": "闵行",
        "location": "东一区与东二区之间，靠近东上中下院教学楼",
        "hours": {
            "早餐": "6:30-9:00",
            "午餐": "11:00-13:00",
            "晚餐": "17:00-19:30",
            "小吃广场": "10:00-21:00",
        },
        "floors": {
            "1F-东": "小吃广场（吉祥馄饨、石锅菜、辛拉面、麻辣烫、酸菜鱼等）",
            "1F-西": "西餐厅（奶茶、烤盘饭、木桶饭、韩式拌饭）",
            "2F": "教工食堂 + 大众餐厅（含新疆餐厅）",
            "3F": "绿园餐厅（麻辣香锅、铁板烧、自选小碗菜）",
        },
        "windows": [
            "吉祥馄饨", "石锅菜", "辛拉面", "麻辣烫", "酸菜鱼",
            "奶茶铺", "烤盘饭", "木桶饭", "韩式拌饭",
            "新疆餐厅", "麻辣香锅", "铁板烧",
        ],
        "nearby": [],
        "features": ["校内最受欢迎", "选择最多", "新疆餐厅独具特色", "三楼自选香锅广受好评"],
        "price_range": "10-35元",
        "rating": 4.5,
        "best_for": ["午餐", "丰富选择", "聚餐"],
        "popular_dishes": ["烤羊肉串(新疆)", "牛奶饭(新疆)", "麻辣香锅(3F)", "吉祥馄饨"],
    },
    {
        "name": "第三餐饮大楼",
        "short_name": "三餐",
        "campus": "闵行",
        "location": "东三宿舍区对面，临近捭阖塘",
        "hours": {
            "早餐": "6:30-9:00",
            "午餐": "11:00-13:00",
            "晚餐": "17:00-19:00",
            "小吃广场": "10:00-20:30",
        },
        "floors": {
            "1F": "学生餐厅（木桶饭、各类点心、特殊窗口）",
            "2F": "小吃广场（黄焖鸡、烤肉饭、麻辣香锅、铁板烧）",
        },
        "windows": ["木桶饭", "黄焖鸡", "烤肉饭", "麻辣香锅", "铁板烧"],
        "nearby": ["捭阖坊便民一条街", "瑞幸咖啡"],
        "features": ["靠近东区宿舍", "捭阖坊小吃街是夜宵好去处", "瑞幸咖啡就在旁边"],
        "price_range": "8-25元",
        "rating": 3.8,
        "best_for": ["东区住宿学生", "夜宵（捭阖坊）"],
        "popular_dishes": ["黄焖鸡米饭", "烤肉饭", "麻辣香锅"],
    },
    {
        "name": "第四餐饮大楼",
        "short_name": "四餐",
        "campus": "闵行",
        "location": "李政道图书馆对面，靠近研究生宿舍和理科群楼",
        "hours": {
            "早餐": "6:30-9:00",
            "午餐": "11:00-13:00",
            "晚餐": "17:00-19:00",
        },
        "floors": {
            "1F": "风味餐厅（烤鸭饭、热凉皮、口袋鸡柳、铁板饭）",
            "2F": "自选小菜、鸭血粉丝、农家菜、吉姆丽德西餐厅",
        },
        "windows": ["烤鸭饭", "热凉皮", "口袋鸡柳", "铁板饭", "鸭血粉丝", "农家菜", "西餐厅"],
        "nearby": ["全家便利店", "交佼咖啡", "水果店"],
        "features": ["靠近理科群楼，理工科同学首选", "旁有全家和咖啡店", "西餐厅适合改善伙食"],
        "price_range": "8-30元",
        "rating": 4.2,
        "best_for": ["研究生", "理工科同学", "西餐"],
        "popular_dishes": ["烤鸭饭", "鸭血粉丝汤", "铁板牛肉饭"],
    },
    {
        "name": "第五餐饮大楼",
        "short_name": "五餐",
        "campus": "闵行",
        "location": "闵行校区南区",
        "hours": {
            "午餐": "11:00-13:00",
            "晚餐": "17:00-19:00",
        },
        "floors": {"1F": "综合餐厅"},
        "windows": [],
        "nearby": [],
        "features": ["南区学生就近用餐"],
        "price_range": "8-18元",
        "rating": 3.5,
        "best_for": ["南区住宿学生"],
        "popular_dishes": [],
    },
    {
        "name": "哈乐餐厅",
        "short_name": "哈乐",
        "campus": "闵行",
        "location": "西一区宿舍区内部",
        "hours": {
            "午餐": "11:00-13:00",
            "晚餐": "17:00-19:00",
        },
        "floors": {"1F": "打菜 + 农家小碗菜"},
        "windows": ["打菜窗口", "农家小碗菜"],
        "nearby": ["思源美食一条街（烤冷面、牛肉汤、烧烤等）"],
        "features": ["农家风味", "土豆泥和煎饺是招牌", "旁边思源美食街选择丰富"],
        "price_range": "6-15元",
        "rating": 4.0,
        "best_for": ["性价比", "农家菜", "西区住宿学生"],
        "popular_dishes": ["土豆泥", "煎饺", "小碗农家菜"],
    },
    {
        "name": "玉兰苑",
        "short_name": "玉兰苑",
        "campus": "闵行",
        "location": "闵行校区内",
        "hours": {
            "营业时间": "视商户而定",
        },
        "floors": {},
        "windows": ["统禾", "厝内小眷村"],
        "nearby": [],
        "features": ["商业化餐饮", "厝内小眷村奶茶广受欢迎"],
        "price_range": "15-40元",
        "rating": 3.8,
        "best_for": ["奶茶", "改善伙食"],
        "popular_dishes": ["厝内小眷村奶茶", "统禾套餐"],
    },
]


def get_canteen_list(campus=None):
    """
    获取食堂列表

    Args:
        campus: 校区过滤，默认返回全部。目前仅有闵行校区数据

    Returns:
        list[dict]: 食堂信息列表
    """
    canteens = CANTEENS
    if campus:
        canteens = [c for c in canteens if c.get("campus", "") == campus]
    return canteens


def get_canteen_menu(canteen_name=None):
    """
    获取食堂菜单

    当前实现: 返回各食堂窗口和特色菜信息（静态数据）
    未来接入: 可通过交我办App接口或食堂小程序获取每日菜单

    Args:
        canteen_name: 食堂名称或简称，None 则返回全部

    Returns:
        dict: 菜单信息
    """
    if canteen_name:
        # 支持简称匹配
        matched = [
            c for c in CANTEENS
            if canteen_name in c["name"] or canteen_name == c["short_name"]
        ]
        if not matched:
            return {
                "error": f"未找到「{canteen_name}」，可用: {', '.join(c['short_name'] for c in CANTEENS)}",
                "available": [c["short_name"] for c in CANTEENS],
            }
        canteens = matched
    else:
        canteens = CANTEENS

    menus = []
    for c in canteens:
        menu_info = {
            "name": c["name"],
            "short_name": c["short_name"],
            "windows": c.get("windows", []),
            "popular_dishes": c.get("popular_dishes", []),
            "price_range": c.get("price_range", ""),
            "hours": c.get("hours", {}),
            "realtime_menu": False,
            "note": "每日具体菜单请查看食堂入口处公告或交我办App",
        }
        if c.get("floors"):
            menu_info["floor_details"] = c["floors"]
        menus.append(menu_info)

    return {
        "date": date.today().strftime("%Y-%m-%d"),
        "menus": menus,
        "data_source": "静态数据（基于公开资料整理）",
        "tip": "如需每日实时菜单，建议查看食堂入口公告或关注「上海交通大学后勤」微信公众号",
    }


def get_canteen_recommendation(meal_type=None):
    """
    AI 友好的食堂推荐

    Args:
        meal_type: 用餐类型 ('breakfast', 'lunch', 'dinner', 'snack', None)

    Returns:
        dict: 推荐信息，包含多维度推荐
    """
    now = datetime.now()
    hour = now.hour
    is_weekend = now.weekday() >= 5

    # 自动判断用餐时段
    if not meal_type:
        if hour < 9:
            meal_type = "breakfast"
        elif hour < 14:
            meal_type = "lunch"
        elif hour < 17:
            meal_type = "snack"
        else:
            meal_type = "dinner"

    meal_names = {
        "breakfast": "早餐",
        "lunch": "午餐",
        "dinner": "晚餐",
        "snack": "下午茶/小吃",
    }

    recommendations = {
        "meal_type": meal_names.get(meal_type, meal_type),
        "time": now.strftime("%H:%M"),
        "categories": {},
    }

    # 按类别推荐
    if meal_type == "breakfast":
        recommendations["categories"] = {
            "🥇 首推": {
                "canteen": "一餐",
                "reason": "早餐种类最丰富，包子、粥、豆浆、油条、煎饼一应俱全",
            },
            "🏃 赶时间": {
                "canteen": "就近食堂",
                "reason": "各食堂早餐品类相近，选最近的节省时间",
            },
        }
    elif meal_type == "lunch":
        recommendations["categories"] = {
            "🥇 选择丰富": {
                "canteen": "二餐",
                "reason": "三层楼+十余个窗口，总有你想吃的",
                "must_try": "3F绿园麻辣香锅 / 2F新疆餐厅烤羊肉串",
            },
            "💰 性价比": {
                "canteen": "哈乐",
                "reason": "农家小碗菜便宜量足，土豆泥和煎饺是灵魂",
            },
            "🍛 理工科友好": {
                "canteen": "四餐",
                "reason": "靠近理科群楼和李图，烤鸭饭和鸭血粉丝值得一试",
            },
            "🥗 健康饮食": {
                "canteen": "一餐",
                "reason": "低脂低糖窗口，养生锅暖胃又健康",
            },
        }
    elif meal_type == "dinner":
        recommendations["categories"] = {
            "🥇 正餐推荐": {
                "canteen": "二餐",
                "reason": "小吃广场营业到21:00，晚餐不慌",
            },
            "🍜 想吃面食": {
                "canteen": "三餐",
                "reason": "黄焖鸡、烤肉饭，配上瑞幸咖啡完美",
            },
            "🌙 加餐夜宵": {
                "canteen": "捭阖坊（三餐旁）",
                "reason": "便民一条街，烤冷面、烧烤、牛肉汤，夜宵圣地",
            },
        }
    elif meal_type == "snack":
        recommendations["categories"] = {
            "🧋 奶茶": {
                "canteen": "玉兰苑",
                "reason": "厝内小眷村，校内奶茶天花板",
            },
            "☕ 咖啡": {
                "canteen": "瑞幸(三餐旁) / Timo(一餐旁) / 交佼(四餐旁)",
                "reason": "校内咖啡选择不少",
            },
            "🍞 面包糕点": {
                "canteen": "思源面包(一餐旁)",
                "reason": "新鲜出炉，下午茶好搭档",
            },
        }

    # 添加随机一条趣味建议
    fun_tips = [
        "💡 选择困难症？闭眼去二餐，不会错",
        "💡 考试周推荐包图联楼 + 四餐，学习吃饭两不误",
        "💡 下雨天就去离宿舍最近的食堂，别纠结了",
        "💡 想省钱就去哈乐，想犒劳自己就去二餐3F麻辣香锅",
        "💡 新疆餐厅的牛奶饭，吃过的都说绝",
        "💡 周末人少，是去探索新窗口的好时机",
    ]
    recommendations["fun_tip"] = random.choice(fun_tips)

    return recommendations


def _print_canteen_list():
    """终端输出食堂列表"""
    canteens = get_canteen_list()
    print(f"\n🍽️  上海交通大学闵行校区食堂")
    print("=" * 60)
    for c in canteens:
        stars = "⭐" * int(c.get("rating", 0)) + ("½" if c.get("rating", 0) % 1 >= 0.5 else "")
        print(f"\n🏠 {c['name']}（{c['short_name']}）{stars}")
        print(f"   📍 位置: {c['location']}")
        print(f"   💰 价格: {c.get('price_range', '未知')}")
        if c.get("hours"):
            for label, time in c["hours"].items():
                print(f"   🕐 {label}: {time}")
        if c.get("features"):
            print(f"   ✨ 特色: {' | '.join(c['features'])}")
        if c.get("popular_dishes"):
            print(f"   🔥 招牌: {', '.join(c['popular_dishes'])}")
        if c.get("nearby"):
            print(f"   🏪 周边: {', '.join(c['nearby'])}")
    print()


def _print_canteen_menu():
    """终端输出菜单信息"""
    # 如果指定了食堂名
    canteen_name = sys.argv[2] if len(sys.argv) > 2 else None
    result = get_canteen_menu(canteen_name)

    if "error" in result:
        print(f"❌ {result['error']}")
        return

    print(f"\n🍽️  食堂菜单信息 ({result['date']})")
    print("=" * 60)
    for menu in result["menus"]:
        print(f"\n🏠 {menu['name']}（{menu['short_name']}）")
        if menu.get("hours"):
            for label, time in menu["hours"].items():
                print(f"   🕐 {label}: {time}")
        if menu.get("floor_details"):
            print(f"   🏢 楼层详情:")
            for floor, desc in menu["floor_details"].items():
                print(f"      {floor}: {desc}")
        if menu["windows"]:
            print(f"   🪟 窗口: {', '.join(menu['windows'])}")
        if menu["popular_dishes"]:
            print(f"   🔥 招牌: {', '.join(menu['popular_dishes'])}")
        print(f"   💰 价格: {menu['price_range']}")
    print(f"\n📌 {result['tip']}")
    print()


def _print_recommendation():
    """终端输出推荐"""
    rec = get_canteen_recommendation()
    print(f"\n🎯 食堂推荐 — {rec['meal_type']}时段 ({rec['time']})")
    print("=" * 60)
    for category, info in rec["categories"].items():
        print(f"\n{category}")
        print(f"   🏠 推荐: {info['canteen']}")
        print(f"   💬 理由: {info['reason']}")
        if info.get("must_try"):
            print(f"   🔥 必点: {info['must_try']}")
    print(f"\n{rec['fun_tip']}")
    print()


def main():
    if len(sys.argv) < 2:
        print("用法: python3 sjtu_canteen.py <命令> [食堂名]")
        print()
        print("命令:")
        print("  list       - 查看所有食堂信息")
        print("  menu       - 查看菜单 (可加食堂名: menu 二餐)")
        print("  recommend  - 获取用餐推荐")
        sys.exit(1)

    cmd = sys.argv[1].lower()
    try:
        if cmd == "list":
            _print_canteen_list()
        elif cmd == "menu":
            _print_canteen_menu()
        elif cmd in ("recommend", "rec"):
            _print_recommendation()
        else:
            print(f"❌ 未知命令: {cmd}")
            print("可用命令: list / menu / recommend")
            sys.exit(1)
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
