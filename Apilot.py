import plugins
import requests
import re
import json
import os
from urllib.parse import urlparse
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from channel import channel
from common.log import logger
from plugins import *
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io
import base64
import tempfile

BASE_URL_VVHAN = "https://api.vvhan.com/api/"
BASE_URL_ALAPI = "https://v3.alapi.cn/api/"


@plugins.register(
    name="Apilot",
    desire_priority=888,  # 提高优先级
    hidden=False,
    desc="A plugin to handle specific keywords and provide news, weather, and other utilities",
    version="0.3",  # 更新版本号
    author="vision",
)
class Apilot(Plugin):
    def __init__(self):
        super().__init__()
        try:
            self.conf = super().load_config()
            self.condition_2_and_3_cities = None  # 天气查询，存储重复城市信息，Initially set to None
            if not self.conf:
                logger.warn("[Apilot] inited but alapi_token not found in config")
                self.alapi_token = None  # Setting a default value for alapi_token
                self.morning_news_text_enabled = False
            else:
                logger.info("[Apilot] inited and alapi_token loaded successfully")
                self.alapi_token = self.conf["alapi_token"]
                try:
                    self.morning_news_text_enabled = self.conf["morning_news_text_enabled"]
                except:
                    self.morning_news_text_enabled = False
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[Apilot] Plugin initialized successfully")
        except Exception as e:
            logger.error(f"[Apilot] init failed: {e}")
            raise Exception(f"[Apilot] init failed: {e}")

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type not in [ContextType.TEXT]:
            return
        content = e_context["context"].content.strip()
        logger.debug("[Apilot] on_handle_context. content: %s" % content)

        if content == "早报":
            news = self.get_morning_news(self.alapi_token, self.morning_news_text_enabled)
            # 检查结果是否为本地文件路径（图片生成的结果）
            if news and os.path.isfile(news):
                reply = self.create_reply(ReplyType.IMAGE_PATH, news)
            else:
                # 保持原来的逻辑，检查是否为有效URL
                reply_type = ReplyType.IMAGE_URL if self.is_valid_url(news) else ReplyType.TEXT
                reply = self.create_reply(reply_type, news)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return
        if content == "摸鱼":
            moyu = self.get_moyu_calendar()
            # 检查结果是否为本地文件路径
            if moyu and os.path.isfile(moyu):
                reply = self.create_reply(ReplyType.IMAGE_PATH, moyu)
            else:
                # 如果不是本地文件，检查是否为有效URL
                reply_type = ReplyType.IMAGE_URL if self.is_valid_url(moyu) else ReplyType.TEXT
                reply = self.create_reply(reply_type, moyu)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        if content == "摸鱼视频":
            moyu = self.get_moyu_calendar_video()
            reply_type = ReplyType.VIDEO_URL if self.is_valid_url(moyu) else ReplyType.TEXT
            reply = self.create_reply(reply_type, moyu)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        if content == "八卦":
            bagua = self.get_mx_bagua()
            # 检查结果是否为本地文件路径
            if bagua and os.path.isfile(bagua):
                reply = self.create_reply(ReplyType.IMAGE_PATH, bagua)
            else:
                # 如果不是本地文件，检查是否为有效URL
                reply_type = ReplyType.IMAGE_URL if self.is_valid_url(bagua) else ReplyType.TEXT
                reply = self.create_reply(reply_type, bagua)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        if content.startswith("快递"):
            # Extract the part after "快递"
            tracking_number = content[2:].strip()

            tracking_number = tracking_number.replace('：', ':')  # 替换可能出现的中文符号
            # Check if alapi_token is available before calling the function
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "快递请求失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                # Check if the tracking_number starts with "SF" for Shunfeng (顺丰) Express
                if tracking_number.startswith("SF"):
                    # Check if the user has included the last four digits of the phone number
                    if ':' not in tracking_number:
                        reply = self.create_reply(ReplyType.TEXT, "顺丰快递需要补充寄/收件人手机号后四位，格式：SF12345:0000")
                        e_context["reply"] = reply
                        e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
                        return  # End the function here

                # Call query_express_info function with the extracted tracking_number and the alapi_token from config
                content = self.query_express_info(self.alapi_token, tracking_number)
                reply = self.create_reply(ReplyType.TEXT, content)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        horoscope_match = re.match(r'^([\u4e00-\u9fa5]{2}座)$', content)
        if horoscope_match:
            if content in ZODIAC_MAPPING:
                zodiac_english = ZODIAC_MAPPING[content]
                content = self.get_horoscope(self.alapi_token, zodiac_english)
                reply = self.create_reply(ReplyType.TEXT, content)
            else:
                reply = self.create_reply(ReplyType.TEXT, "请重新输入星座名称")
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        hot_trend_match = re.search(r'(.{1,6})热榜$', content)
        if hot_trend_match:
            hot_trends_type = hot_trend_match.group(1).strip()  # 提取匹配的组并去掉可能的空格
            content = self.get_hot_trends(hot_trends_type)
            reply = self.create_reply(ReplyType.TEXT, content)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        # 查字典功能
        word_match = re.match(r'^查字典\s+(.+)$', content)
        if word_match:
            word = word_match.group(1)
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "查字典功能失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                word_info = self.get_word_info(self.alapi_token, word)
                reply = self.create_reply(ReplyType.TEXT, word_info)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        # 黄金价格查询
        if content == "黄金":
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "黄金价格查询失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                gold_price = self.get_gold_price(self.alapi_token)
                reply = self.create_reply(ReplyType.TEXT, gold_price)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

        # 油价查询
        oil_match = re.match(r'^(.{2,7}?)(?:省|市)?油价$', content)
        if oil_match:
            province = oil_match.group(1)
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "油价查询失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                oil_price = self.get_oil_price(self.alapi_token, province)
                reply = self.create_reply(ReplyType.TEXT, oil_price)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return            

        # 天气查询
        weather_match = re.match(r'^(?:(.{2,7}?)(?:市|县|区|镇)?|(\d{7,9}))(:?今天|明天|后天|7天|七天)?(?:的)?天气$', content)
        if weather_match:
            city_or_id = weather_match.group(1) or weather_match.group(2)
            date = weather_match.group(3)
            if not self.alapi_token:
                self.handle_error("alapi_token not configured", "天气请求失败")
                reply = self.create_reply(ReplyType.TEXT, "请先配置alapi的token")
            else:
                content = self.get_weather(self.alapi_token, city_or_id, date, content)
                reply = self.create_reply(ReplyType.TEXT, content)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            return

    def get_help_text(self, verbose=False, **kwargs):
        short_help_text = " 发送特定指令以获取早报、热榜、查询天气、星座运势、快递信息等！"

        if not verbose:
            return short_help_text

        help_text = "📚 发送关键词获取特定信息！\n"

        # 娱乐和信息类
        help_text += "\n🎉 娱乐与资讯：\n"
        help_text += "  🌅 早报: 发送"早报"获取早报。\n"
        help_text += "  🌴 摸鱼: 发送"摸鱼"获取摸鱼人日历。\n"
        help_text += "  🔥 热榜: 发送"xx热榜"查看支持的热榜。\n"
        help_text += "  🔥 八卦: 发送"八卦"获取明星八卦。\n"

        # 查询类
        help_text += "\n🔍 查询工具：\n"
        help_text += "  🌤️ 天气: 发送"城市+天气"查天气，如"北京天气"。\n"
        help_text += "  📦 快递: 发送"快递+单号"查询快递状态。如"快递112345655"\n"
        help_text += "  🌌 星座: 发送星座名称查看今日运势，如"白羊座"。\n"

        return help_text

    def get_morning_news(self, alapi_token, morning_news_text_enabled):
        if not alapi_token:
            url = BASE_URL_VVHAN + "60s?type=json"
            payload = "format=json"
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            try:
                morning_news_info = self.make_request(url, method="POST", headers=headers, data=payload)
                if isinstance(morning_news_info, dict) and morning_news_info['success']:
                    # 提取并格式化新闻
                    news_list = ["{}. {}".format(idx, news) for idx, news in enumerate(morning_news_info["data"][:-1], 1)]
                    title = f"☕ {morning_news_info['data']['date']}  今日早报"
                    formatted_news = "\n".join(news_list)
                    weiyu = morning_news_info["data"][-1].strip()
                    full_text = f"{formatted_news}\n\n{weiyu}"
                    
                    # 转换为图片
                    img_path = self.text_to_image(full_text, title=title)
                    if img_path:
                        return img_path
                    else:
                        # 如果转换失败，尝试从API获取的图片URL下载图片
                        img_url = morning_news_info.get('imgUrl', '')
                        if img_url and self.is_valid_image_url(img_url):
                            downloaded_img = self.download_image(img_url)
                            if downloaded_img:
                                return downloaded_img
                        # 如果下载也失败，最后才返回图片URL
                        return img_url
                else:
                    return self.handle_error(morning_news_info, '早报信息获取失败，可配置"alapi token"切换至 Alapi 服务，或者稍后再试')
            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")
        else:
            url = BASE_URL_ALAPI + "zaobao"
            data = {
                "token": alapi_token,
                "format": "json"
            }
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            try:
                morning_news_info = self.make_request(url, method="POST", headers=headers, data=data)
                if isinstance(morning_news_info, dict) and morning_news_info.get('code') == 200:
                    img_url = morning_news_info['data']['image']
                    
                    # 整理新闻为有序列表
                    news_list = morning_news_info['data']['news']
                    title = f"☕ {morning_news_info['data']['date']}  今日早报"
                    formatted_news = "\n".join([f"{i+1}. {news}" for i, news in enumerate(news_list)])
                    weiyu = morning_news_info['data']['weiyu']
                    full_text = f"{formatted_news}\n\n{weiyu}"
                    
                    # 转换为图片
                    img_path = self.text_to_image(full_text, title=title)
                    if img_path:
                        return img_path
                    else:
                        # 如果文本转图片失败，尝试下载API提供的图片URL
                        if img_url and self.is_valid_image_url(img_url):
                            downloaded_img = self.download_image(img_url)
                            if downloaded_img:
                                return downloaded_img
                        # 如果下载也失败，最后才返回图片URL
                        return img_url
                else:
                    return self.handle_error(morning_news_info, "早报获取失败，请检查 token 是否有误")
            except Exception as e:
                return self.handle_error(e, "早报获取失败")

    def get_moyu_calendar(self):
        url = BASE_URL_VVHAN + "moyu?type=json"
        payload = "format=json"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        moyu_calendar_info = self.make_request(url, method="POST", headers=headers, data=payload)
        # 验证请求是否成功
        if isinstance(moyu_calendar_info, dict) and moyu_calendar_info['success']:
            moyu_pic_url = moyu_calendar_info['url']
            if self.is_valid_image_url(moyu_pic_url):
                # 尝试下载图片
                downloaded_img = self.download_image(moyu_pic_url)
                if downloaded_img:
                    return downloaded_img
            # 如果下载失败或URL无效，返回URL
            return moyu_pic_url
        else:
            url = "https://dayu.qqsuu.cn/moyuribao/apis.php?type=json"
            payload = "format=json"
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            moyu_calendar_info = self.make_request(url, method="POST", headers=headers, data=payload)
            if isinstance(moyu_calendar_info, dict) and moyu_calendar_info['code'] == 200:
                moyu_pic_url = moyu_calendar_info['data']
                if self.is_valid_image_url(moyu_pic_url):
                    # 尝试下载图片
                    downloaded_img = self.download_image(moyu_pic_url)
                    if downloaded_img:
                        return downloaded_img
                    # 如果下载失败，返回URL
                    return moyu_pic_url
                else:
                    return "周末无需摸鱼，愉快玩耍吧"
            else:
                return "暂无可用"摸鱼"服务，认真上班"

    def get_moyu_calendar_video(self):
        url = "https://dayu.qqsuu.cn/moyuribaoshipin/apis.php?type=json"
        payload = "format=json"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        moyu_calendar_info = self.make_request(url, method="POST", headers=headers, data=payload)
        logger.debug(f"[Apilot] moyu calendar video response: {moyu_calendar_info}")
        # 验证请求是否成功
        if isinstance(moyu_calendar_info, dict) and moyu_calendar_info['code'] == 200:
            moyu_video_url = moyu_calendar_info['data']
            if self.is_valid_image_url(moyu_video_url):
                return moyu_video_url

        # 未成功请求到视频时，返回提示信息
        return "视频版没了，看看文字版吧"

    def get_horoscope(self, alapi_token, astro_sign: str, time_period: str = "today"):
        if not alapi_token:
            url = BASE_URL_VVHAN + "horoscope"
            params = {
                'type': astro_sign,
                'time': time_period
            }
            try:
                horoscope_data = self.make_request(url, "GET", params=params)
                if isinstance(horoscope_data, dict) and horoscope_data['success']:
                    data = horoscope_data['data']

                    result = (
                        f"{data['title']} ({data['time']}):\n\n"
                        f"💡【每日建议】\n宜：{data['todo']['yi']}\n忌：{data['todo']['ji']}\n\n"
                        f"📊【运势指数】\n"
                        f"总运势：{data['index']['all']}\n"
                        f"爱情：{data['index']['love']}\n"
                        f"工作：{data['index']['work']}\n"
                        f"财运：{data['index']['money']}\n"
                        f"健康：{data['index']['health']}\n\n"
                        f"🍀【幸运提示】\n数字：{data['luckynumber']}\n"
                        f"颜色：{data['luckycolor']}\n"
                        f"星座：{data['luckyconstellation']}\n\n"
                        f"✍【简评】\n{data['shortcomment']}\n\n"
                        f"📜【详细运势】\n"
                        f"总运：{data['fortunetext']['all']}\n"
                        f"爱情：{data['fortunetext']['love']}\n"
                        f"工作：{data['fortunetext']['work']}\n"
                        f"财运：{data['fortunetext']['money']}\n"
                        f"健康：{data['fortunetext']['health']}\n"
                    )

                    return result

                else:
                    return self.handle_error(horoscope_data, '星座信息获取失败，可配置"alapi token"切换至 Alapi 服务，或者稍后再试')

            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")
        else:
            # 使用 ALAPI 的 URL 和提供的 token
            url = BASE_URL_ALAPI + "star"
            payload = f"token={alapi_token}&star={astro_sign}"
            headers = {'Content-Type': "application/x-www-form-urlencoded"}
            try:
                horoscope_data = self.make_request(url, method="POST", headers=headers, data=payload)
                if isinstance(horoscope_data, dict) and horoscope_data.get('code') == 200:
                    data = horoscope_data['data']['day']

                    # 格式化并返回 ALAPI 提供的星座信息
                    result = (
                        f"📅 日期：{data['date']}\n\n"
                        f"💡【每日建议】\n宜：{data['yi']}\n忌：{data['ji']}\n\n"
                        f"📊【运势指数】\n"
                        f"总运势：{data['all']}\n"
                        f"爱情：{data['love']}\n"
                        f"工作：{data['work']}\n"
                        f"财运：{data['money']}\n"
                        f"健康：{data['health']}\n\n"
                        f"🔔【提醒】：{data['notice']}\n\n"
                        f"🍀【幸运提示】\n数字：{data['lucky_number']}\n"
                        f"颜色：{data['lucky_color']}\n"
                        f"星座：{data['lucky_star']}\n\n"
                        f"✍【简评】\n总运：{data['all_text']}\n"
                        f"爱情：{data['love_text']}\n"
                        f"工作：{data['work_text']}\n"
                        f"财运：{data['money_text']}\n"
                        f"健康：{data['health_text']}\n"
                    )
                    return result
                else:
                    return self.handle_error(horoscope_data, "星座获取信息获取失败，请检查 token 是否有误")
            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")

    def get_hot_trends(self, hot_trends_type):
        # 查找映射字典以获取API参数
        hot_trends_type_en = hot_trend_types.get(hot_trends_type, None)
        if hot_trends_type_en is not None:
            url = BASE_URL_VVHAN + "hotlist/" + hot_trends_type_en
            try:
                data = self.make_request(url, "GET", {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                })
                if isinstance(data, dict) and data['success'] == True:
                    output = []
                    topics = data['data']
                    output.append(f'更新时间：{data["update_time"]}\n')
                    for i, topic in enumerate(topics[:15], 1):
                        hot = topic.get('hot', '无热度参数, 0')
                        formatted_str = f"{i}. {topic['title']} ({hot} 浏览)\nURL: {topic['url']}\n"
                        output.append(formatted_str)
                    return "\n".join(output)
                else:
                    return self.handle_error(data, "热榜获取失败，请稍后再试")
            except Exception as e:
                return self.handle_error(e, "出错啦，稍后再试")
        else:
            supported_types = "/".join(hot_trend_types.keys())
            final_output = (
                f"👉 已支持的类型有：\n\n    {supported_types}\n"
                f"\n📝 请按照以下格式发送：\n    类型+热榜  例如：微博热榜"
            )
            return final_output

    def query_express_info(self, alapi_token, tracking_number, com="", order="asc"):
        url = BASE_URL_ALAPI + "kd"
        payload = f"token={alapi_token}&number={tracking_number}&com={com}&order={order}"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}

        try:
            response_json = self.make_request(url, method="POST", headers=headers, data=payload)

            if not isinstance(response_json, dict) or response_json is None:
                return f"查询失败：api响应为空"
            code = response_json.get("code", None)
            if code != 200:
                msg = response_json.get("msg", "未知错误")
                self.handle_error(msg, f"错误码{code}")
                return f"查询失败，{msg}"
            data = response_json.get("data", None)
            formatted_result = [
                f"快递编号：{data.get('nu')}",
                f"快递公司：{data.get('com')}",
                f"状态：{data.get('status_desc')}",
                "状态信息："
            ]
            for info in data.get("info"):
                time_str = info.get('time')[5:-3]
                formatted_result.append(f"{time_str} - {info.get('status_desc')}\n    {info.get('content')}")

            return "\n".join(formatted_result)

        except Exception as e:
            return self.handle_error(e, "快递查询失败")

    def get_word_info(self, alapi_token, word):
        url = BASE_URL_ALAPI + "word"
        params = {
            "token": alapi_token,
            "word": word
        }
        try:
            response = requests.get(url, params=params)
            response_json = response.json()
            logger.debug(f"[Apilot] Word API response: {response_json}")
            if response_json.get("success"):
                data = response_json.get("data")
                if data:
                    word_info = data[0]  # 假设返回的第一个结果是我们需要的
                    formatted_output = (
                        f"字: {word_info['word']}\n"
                        f"拼音: {word_info['pinyin']}\n"
                        f"笔画: {word_info['strokes']}\n"
                        f"部首: {word_info['radical']}\n"
                        f"释义: {word_info['explanation']}\n"
                    )
                    return formatted_output
                else:
                    return f"未找到 {word} 的字典信息"
            else:
                error_message = response_json.get("message", "未知错误")
                return f"查询字典信息失败，API 返回错误：{error_message}"
        except Exception as e:
            logger.error(f"[Apilot] Failed to fetch word info: {e}")
            return f"查询字典信息失败，错误信息：{e}"

    def get_gold_price(self, alapi_token):
        url = BASE_URL_ALAPI + "gold"
        params = {
            "token": alapi_token
        }
        try:
            response = requests.get(url, params=params)
            response_json = response.json()
            logger.debug(f"[Apilot] Gold API response: {response_json}")
            if response_json.get("success"):
                data = response_json.get("data")
                if data:
                    formatted_output = []
                    for item in data:
                        formatted_output.append(
                            f"名称: {item['name']}\n"
                            f"买入价: {item['buy_price']} 元\n"
                            f"卖出价: {item['sell_price']} 元\n"
                            f"最高价: {item['high_price']} 元\n"
                            f"最低价: {item['low_price']} 元\n"
                        )
                    return "\n".join(formatted_output)
                else:
                    return "获取黄金价格失败，返回数据为空"
            else:
                error_message = response_json.get("message", "未知错误")
                return f"获取黄金价格失败，API 返回错误：{error_message}"
        except Exception as e:
            logger.error(f"[Apilot] Failed to fetch gold price: {e}")
            return f"获取黄金价格失败，错误信息：{e}"

    def get_oil_price(self, alapi_token, province):
        url = BASE_URL_ALAPI + "oil"
        params = {
            "token": alapi_token
        }
        try:
            response = requests.get(url, params=params)
            response_json = response.json()
            logger.debug(f"[Apilot] Oil API response: {response_json}")
            if response_json.get("success"):
                data = response_json.get("data")
                if data:
                    for item in data:
                        if item["province"] == province:
                            formatted_output = (
                                f"省份: {item['province']}\n"
                                f"89号汽油: {item['o89']} 元/升\n"
                                f"92号汽油: {item['o92']} 元/升\n"
                                f"95号汽油: {item['o95']} 元/升\n"
                                f"98号汽油: {item['o98']} 元/升\n"
                                f"0号柴油: {item['o0']} 元/升\n"
                            )
                            return formatted_output
                    return f"未找到 {province} 的油价信息"
                else:
                    return "获取油价信息失败，返回数据为空"
            else:
                error_message = response_json.get("message", "未知错误")
                return f"获取油价信息失败，API 返回错误：{error_message}"
        except Exception as e:
            logger.error(f"[Apilot] Failed to fetch oil price: {e}")
            return f"获取油价信息失败，错误信息：{e}"            

    def get_weather(self, alapi_token, city_or_id: str, date: str, content):
        url = BASE_URL_ALAPI + 'tianqi'
        isFuture = date in ['明天', '后天', '7天', '七天']
        if isFuture:
            url = BASE_URL_ALAPI + 'tianqi/seven'
        # 判断使用id还是city请求api
        if city_or_id.isnumeric():  # 判断是否为纯数字，也即是否为 city_id
            params = {
                'city_id': city_or_id,
                'token': alapi_token
            }
        else:
            city_info = self.check_multiple_city_ids(city_or_id)
            if city_info:
                data = city_info['data']
                formatted_city_info = "\n".join(
                    [f"{idx + 1}) {entry['province']}--{entry['leader']}, ID: {entry['city_id']}"
                     for idx, entry in enumerate(data)]
                )
                return f"查询 <{city_or_id}> 具有多条数据：\n{formatted_city_info}\n请使用id查询，发送"id天气""

            params = {
                'city': city_or_id,
                'token': alapi_token
            }
        try:
            weather_data = self.make_request(url, "GET", params=params)
            if not isinstance(weather_data, dict) or weather_data.get('success') is not True:
                error_message = weather_data.get('message', '未知错误')
                return self.handle_error(weather_data, f"获取天气信息失败，API 返回错误：{error_message}")

            data = weather_data.get('data')
            if data is None:
                return "获取天气信息失败，返回数据为空。可能的原因：\n1. 查询的城市无效。\n2. 查询的日期格式不被支持（例如"七天"可能不被支持）。\n3. API 返回数据为空。"

            # 处理天气数据
            if isFuture:
                formatted_output = []
                for num, d in enumerate(data):
                    if num == 0:
                        formatted_output.append(f"🏙️ 城市: {d['city']} ({d['province']})\n")
                    if date == '明天' and num != 1:
                        continue
                    if date == '后天' and num != 2:
                        continue
                    basic_info = [
                        f"🕒 日期: {d['date']}",
                        f"🌥️ 天气: 🌤️{d['wea_day']}| 🌙{d['wea_night']}",
                        f"🌡️ 温度: 🌤️{d['temp_day']}℃| 🌙{d['temp_night']}℃",
                        f"🌅 日出/日落: {d['sunrise']} / {d['sunset']}",
                    ]
                    for i in d['index']:
                        basic_info.append(f"{i['name']}: {i['level']}")
                    formatted_output.append("\n".join(basic_info) + '\n')
                return "\n".join(formatted_output)

            update_time = data['update_time']
            dt_object = datetime.strptime(update_time, "%Y-%m-%d %H:%M:%S")
            formatted_update_time = dt_object.strftime("%m-%d %H:%M")
            formatted_output = []
            basic_info = (
                f"🏙️ 城市: {data['city']} ({data['province']})\n"
                f"🕒 更新时间: {formatted_update_time}\n"
                f"🌤️ 天气: {data['weather']}\n"
                f"🌡️ 温度: 当前 {data['temp']}℃, 最低 {data['min_temp']}℃, 最高 {data['max_temp']}℃\n"
                f"🌬️ 风向: {data['wind']}, 风速: {data['wind_speed']}\n"
                f"💧 湿度: {data['humidity']}\n"
                f"🌅 日出/日落: {data['sunrise']} / {data['sunset']}\n"
                f"😷 空气质量: {data['air']} (PM2.5: {data['air_pm25']})\n"
            )
            formatted_output.append(basic_info)

            # 生活指数
            index_info = "💡 生活指数:\n"
            for index in data.get('index', []):
                index_info += f"  - {index['name']}: {index['level']} ({index['content']})\n"
            formatted_output.append(index_info)

            # 未来 10 小时天气预报
            future_weather_info = "⏳ 未来 10 小时天气预报:\n"
            current_time = datetime.strptime(data['update_time'], "%Y-%m-%d %H:%M:%S")
            ten_hours_later = current_time + timedelta(hours=10)
            for hour_data in data.get('hour', []):
                forecast_time = datetime.strptime(hour_data['time'], "%Y-%m-%d %H:%M:%S")
                if current_time <= forecast_time <= ten_hours_later:
                    future_weather_info += f"  - {forecast_time.strftime('%H:%M')} - {hour_data['wea']} - {hour_data['temp']}℃\n"
            formatted_output.append(future_weather_info)

            # 空气质量详细信息
            aqi_info = "😷 空气质量详细信息:\n"
            aqi_data = data.get('aqi', {})
            aqi_info += (
                f"  - 空气质量指数: {aqi_data.get('air', 'N/A')} ({aqi_data.get('air_level', 'N/A')})\n"
                f"  - PM2.5: {aqi_data.get('pm25', 'N/A')}\n"
                f"  - PM10: {aqi_data.get('pm10', 'N/A')}\n"
                f"  - CO: {aqi_data.get('co', 'N/A')}\n"
                f"  - NO2: {aqi_data.get('no2', 'N/A')}\n"
                f"  - SO2: {aqi_data.get('so2', 'N/A')}\n"
                f"  - O3: {aqi_data.get('o3', 'N/A')}\n"
                f"  - 建议: {aqi_data.get('air_tips', 'N/A')}\n"
            )
            formatted_output.append(aqi_info)

            # Alarm Info
            if data.get('alarm'):
                alarm_info = "⚠️ 预警信息:\n"
                for alarm in data['alarm']:
                    alarm_info += (
                        f"🔴 标题: {alarm['title']}\n"
                        f"🟠 等级: {alarm['level']}\n"
                        f"🟡 类型: {alarm['type']}\n"
                        f"🟢 提示: \n{alarm['tips']}\n"
                        f"🔵 内容: \n{alarm['content']}\n\n"
                    )
                formatted_output.append(alarm_info)

            return "\n".join(formatted_output)
        except Exception as e:
            return self.handle_error(e, "获取天气信息失败")

    def get_mx_bagua(self):
        url = "https://dayu.qqsuu.cn/mingxingbagua/apis.php?type=json"
        payload = "format=json"
        headers = {'Content-Type': "application/x-www-form-urlencoded"}
        bagua_info = self.make_request(url, method="POST", headers=headers, data=payload)
        # 验证请求是否成功
        if isinstance(bagua_info, dict) and bagua_info['code'] == 200:
            bagua_pic_url = bagua_info["data"]
            if self.is_valid_image_url(bagua_pic_url):
                # 尝试下载图片
                downloaded_img = self.download_image(bagua_pic_url)
                if downloaded_img:
                    return downloaded_img
                # 如果下载失败，返回URL
                return bagua_pic_url
            else:
                return "周末不更新，请微博吃瓜"
        else:
            logger.error(f"错误信息：{bagua_info}")
            return "暂无明星八卦，吃瓜莫急"

    def make_request(self, url, method="GET", headers=None, params=None, data=None, json_data=None):
        try:
            if method.upper() == "GET":
                response = requests.request(method, url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = requests.request(method, url, headers=headers, data=data, json=json_data)
            else:
                return {"success": False, "message": "Unsupported HTTP method"}

            # 检查响应状态码
            if response.status_code != 200:
                logger.error(f"[Apilot] API request failed with status code: {response.status_code}")
                return {"success": False, "message": f"HTTP Error: {response.status_code}", "status_code": response.status_code}

            try:
                # 尝试解析 JSON 数据
                response_json = response.json()
                logger.debug(f"[Apilot] API response: {response_json}")
                return response_json
            except json.JSONDecodeError as e:
                # 如果解析失败，记录完整的返回内容
                logger.error(f"[Apilot] Failed to parse JSON response: {e}\nResponse text: {response.text}")
                return {"success": False, "message": f"JSON Decode Error: {e}", "response_text": response.text}
        except requests.RequestException as e:
            logger.error(f"[Apilot] API request failed: {e}")
            return {"success": False, "message": str(e)}

    def create_reply(self, reply_type, content):
        reply = Reply()
        reply.type = reply_type
        reply.content = content
        return reply

    def handle_error(self, error, message):
        logger.error(f"{message}，错误信息：{error}")
        return message

    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def is_valid_image_url(self, url):
        try:
            response = requests.head(url)  # Using HEAD request to check the URL header
            return response.status_code == 200
        except requests.RequestException as e:
            return False

    def download_image(self, image_url):
        """从URL下载图片并保存到本地临时文件
        
        Args:
            image_url: 图片URL
            
        Returns:
            str: 临时文件路径，如果下载失败则返回None
        """
        try:
            response = requests.get(image_url, stream=True, timeout=15)
            if response.status_code == 200:
                # 获取文件扩展名
                content_type = response.headers.get('Content-Type', '')
                if 'image/jpeg' in content_type or 'image/jpg' in content_type:
                    ext = '.jpg'
                elif 'image/png' in content_type:
                    ext = '.png'
                elif 'image/gif' in content_type:
                    ext = '.gif'
                else:
                    ext = '.jpg'  # 默认使用jpg
                
                # 创建临时文件
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        temp_file.write(chunk)
                temp_file.close()
                logger.info(f"[Apilot] 图片下载成功，保存至: {temp_file.name}")
                return temp_file.name
            else:
                logger.error(f"[Apilot] 图片下载失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"[Apilot] 图片下载异常: {e}")
            return None

    def load_city_conditions(self):
        if self.condition_2_and_3_cities is None:
            try:
                json_file_path = os.path.join(os.path.dirname(__file__), 'duplicate-citys.json')
                with open(json_file_path, 'r', encoding='utf-8') as f:
                    self.condition_2_and_3_cities = json.load(f)
            except Exception as e:
                return self.handle_error(e, "加载condition_2_and_3_cities.json失败")

    def check_multiple_city_ids(self, city):
        self.load_city_conditions()
        city_info = self.condition_2_and_3_cities.get(city, None)
        if city_info:
            return city_info
        return None

    def text_to_image(self, text, title=None, font_path=None, width=800, padding=20, line_spacing=10, background_color=(255, 255, 255), title_color=(31, 120, 180), text_color=(0, 0, 0)):
        """将文本转换为图片

        Args:
            text: 要转换的文本内容
            title: 标题文本，默认为None
            font_path: 字体路径，默认为None，使用默认字体
            width: 图片宽度，默认800像素
            padding: 内边距，默认20像素
            line_spacing: 行间距，默认10像素
            background_color: 背景颜色，默认白色
            title_color: 标题颜色，默认蓝色
            text_color: 正文颜色，默认黑色

        Returns:
            临时图片文件的路径
        """
        try:
            # 使用默认字体
            if font_path is None or not os.path.exists(font_path):
                # 尝试常见的中文字体路径
                common_fonts = [
                    "/System/Library/Fonts/PingFang.ttc",  # macOS
                    "C:/Windows/Fonts/msyh.ttc",  # Windows
                    "C:/Windows/Fonts/simhei.ttf",  # Windows
                    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Linux
                ]
                
                for f in common_fonts:
                    if os.path.exists(f):
                        font_path = f
                        break
            
            # 创建字体对象
            try:
                title_font = ImageFont.truetype(font_path, 28) if font_path else ImageFont.load_default()
                body_font = ImageFont.truetype(font_path, 20) if font_path else ImageFont.load_default()
            except Exception as e:
                logger.error(f"加载字体失败: {e}，使用默认字体")
                title_font = ImageFont.load_default()
                body_font = ImageFont.load_default()
            
            # 计算行宽和总高度
            lines = []
            current_y = padding
            
            # 添加标题
            if title:
                lines.append(("title", title))
                title_bbox = title_font.getbbox(title)
                title_height = title_bbox[3] - title_bbox[1]
                current_y += title_height + line_spacing * 2
            
            # 分行处理文本
            for line in text.split('\n'):
                if not line.strip():  # 空行处理
                    current_y += line_spacing
                    lines.append(("empty", ""))
                    continue
                
                # 计算一行能容纳的文字数
                char_width_avg = body_font.getbbox("测试")[2] / 2  # 简单估算平均字符宽度
                max_chars_per_line = int((width - padding * 2) / char_width_avg)
                
                # 如果单行长度超过最大宽度，拆分
                if len(line) > max_chars_per_line:
                    for i in range(0, len(line), max_chars_per_line):
                        sub_line = line[i:i+max_chars_per_line]
                        lines.append(("text", sub_line))
                        char_bbox = body_font.getbbox(sub_line)
                        char_height = char_bbox[3] - char_bbox[1]
                        current_y += char_height + line_spacing
                else:
                    lines.append(("text", line))
                    char_bbox = body_font.getbbox(line)
                    char_height = char_bbox[3] - char_bbox[1]
                    current_y += char_height + line_spacing
            
            # 创建图像，高度根据文本内容动态确定
            height = current_y + padding
            image = Image.new('RGB', (width, height), background_color)
            draw = ImageDraw.Draw(image)
            
            # 绘制文本
            current_y = padding
            for line_type, line_text in lines:
                if line_type == "empty":
                    current_y += line_spacing
                    continue
                
                if line_type == "title":
                    draw.text((padding, current_y), line_text, font=title_font, fill=title_color)
                    title_bbox = title_font.getbbox(line_text)
                    title_height = title_bbox[3] - title_bbox[1]
                    current_y += title_height + line_spacing * 2
                    
                    # 标题下划线
                    draw.line([(padding, current_y - line_spacing), 
                            (width - padding, current_y - line_spacing)], 
                            fill=title_color, width=2)
                else:
                    draw.text((padding, current_y), line_text, font=body_font, fill=text_color)
                    char_bbox = body_font.getbbox(line_text)
                    char_height = char_bbox[3] - char_bbox[1]
                    current_y += char_height + line_spacing
            
            # 添加轻微的阴影效果
            blurred = image.filter(ImageFilter.GaussianBlur(radius=1))
            image = Image.blend(blurred, image, alpha=0.8)
            
            # 保存到临时文件
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
            image.save(temp_file.name)
            temp_file.close()
            
            return temp_file.name
        except Exception as e:
            logger.error(f"生成图片失败: {e}")
            return None


ZODIAC_MAPPING = {
    '白羊座': 'aries',
    '金牛座': 'taurus',
    '双子座': 'gemini',
    '巨蟹座': 'cancer',
    '狮子座': 'leo',
    '处女座': 'virgo',
    '天秤座': 'libra',
    '天蝎座': 'scorpio',
    '射手座': 'sagittarius',
    '摩羯座': 'capricorn',
    '水瓶座': 'aquarius',
    '双鱼座': 'pisces'
}

hot_trend_types = {
    "微博": "wbHot",
    "虎扑": "huPu",
    "知乎": "zhihuHot",
    "知乎日报": "zhihuDay",
    "哔哩哔哩": "bili",
    "36氪": "36Ke",
    "抖音": "douyinHot",
    "IT": "itNews",
    "虎嗅": "huXiu",
    "产品经理": "woShiPm",
    "头条": "toutiao",
    "百度": "baiduRD",
    "豆瓣": "douban",
}