import asyncio
from io import BytesIO
import random
import re

from curl_cffi.requests import AsyncSession, Response
from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid
from PIL import Image
import numpy as np

from embykeeper.config import config
from embykeeper.utils import show_exception, get_proxy_str

from ..lock import pornemby_alert
from . import Monitor

JAVDATABASE_URL = "https://www.javdatabase.com"


class _PornembyExamResultMonitor(Monitor):
    name = "Pornemby 科举答案"
    chat_keyword = r"问题\d*：(.*?)\n+答案为：([ABCD])\n+([A-Z-\d]+)"
    additional_auth = ["pornemby_pack"]
    allow_edit = True

    async def on_trigger(self, message: Message, key, reply):
        self.log.info(f"本题正确答案为 {key[1]} ({key[2]}).")


class _PornembyExamAnswerMonitor(Monitor):
    name = "Pornemby 科举"
    chat_user = [
        "pornemby_question_bot",
        "PronembyTGBot2_bot",
        "PronembyTGBot3_bot",
        "PornembyBot",
        "Porn_Emby_Bot",
        "Porn_Emby_Scriptbot",
    ]
    chat_keyword = (
        r"问题\d*：根据以上封面图，猜猜是什么番号？\n+A:(.*)\n+B:(.*)\n+C:(.*)\n+D:(.*)\n(?!\n*答案)"
    )
    additional_auth = ["pornemby_pack"]
    allow_edit = True

    key_map = {
        "A": ["A", "🅰"],
        "B": ["B", "🅱"],
        "C": ["C", "🅲"],
        "D": ["D", "🅳"],
    }

    async def use_cfsolver(self):
        from embykeeper.cloudflare import get_cf_clearance

        if self.proxy:
            if self.proxy.scheme != "socks5":
                self.log.warning(f"站点验证解析仅支持 SOCKS5 代理，由于当前代理协议不支持, 将尝试不使用代理.")
                self.proxy = None
            else:
                self.log.info(
                    f"验证码解析将使用代理, 可能导致解析失败, 若失败请使用"
                    '"use_proxy = false" 以禁用该站点的代理.'
                )
        try:
            cf_clearance, useragent = await get_cf_clearance(JAVDATABASE_URL, self.proxy)
            if not cf_clearance:
                self.log.warning(f"Cloudflare 验证码解析失败.")
                return False
            else:
                self.cf_clearance = cf_clearance
                self.useragent = useragent
                return True
        except Exception as e:
            self.log.warning(f"Cloudflare 验证码解析时出现错误.")
            show_exception(e, regular=False)
            return False

    async def init(self):
        self.proxy = config.proxy
        self.useragent = None
        self.cf_clearance = None
        for _ in range(3):
            try:
                if self.useragent:
                    headers = {"User-Agent": self.useragent}
                else:
                    headers = None
                if self.cf_clearance:
                    cookies = {"cf_clearance": self.cf_clearance}
                else:
                    cookies = None
                async with AsyncSession(
                    proxy=get_proxy_str(self.proxy),
                    impersonate="chrome",
                    timeout=10.0,
                    allow_redirects=True,
                    headers=headers,
                    cookies=cookies,
                ) as session:
                    resp: Response = await session.get(JAVDATABASE_URL)
                    if resp.status_code == 403 and (
                        "cf-wrapper" in resp.text or "Just a moment" in resp.text
                    ):
                        if self.cf_clearance:
                            self.log.warning("初始化失败: Javdatabase 在 Cloudflare 验证码解析后依然有验证")
                            return False
                        self.log.info("Javdatabase 存在 Cloudflare 保护，正在尝试解析.")
                        await self.use_cfsolver()
                        continue
                    elif not resp.ok:
                        self.log.warning(f"初始化失败: Javdatabase 返回状态码错误: {resp.status_code}.")
                        return False
                    return True
            except Exception as e:
                self.log.warning(f"初始化失败: 无法连接 Javdatabase: {e.__class__.__name__}: {str(e)}")
                return False

    async def get_cover_image_javdatabase(self, code: str):
        # 添加重试次数
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with AsyncSession(
                    proxy=get_proxy_str(self.proxy),
                    impersonate="chrome",
                    timeout=10.0,
                    allow_redirects=True,
                ) as session:
                    detail_url = f"{JAVDATABASE_URL}/movies/{code.lower()}/"
                    resp: Response = await session.get(detail_url)
                    if resp.status_code != 200:
                        self.log.warning(
                            f"获取影片详情失败: 网址访问错误: {detail_url} ({resp.status_code})."
                        )
                        retry_count += 1
                        if retry_count < max_retries:
                            self.log.info(f"正在进行第 {retry_count + 1} 次重试...")
                            continue
                        return None
                    html = resp.text
                    pattern = f'<div id="thumbnailContainer".*({JAVDATABASE_URL}//covers/thumb/.*/.*.webp)'
                    match = re.search(pattern, html)
                    if not match:
                        self.log.warning(f"获取封面图片失败: 未找到图片: {detail_url} ({resp.status_code}).")
                        return None
                    img_url = match.group(1)
                    # 下载封面图片
                    img_response = await session.get(img_url)
                    if img_response.status_code == 200:
                        return BytesIO(img_response.content)
                    else:
                        self.log.warning(
                            f"获取封面图片失败: 网址访问错误: {img_url} ({img_response.status_code})."
                        )
                        return None

            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    self.log.info(
                        f"获取封面图片失败，正在进行第 {retry_count + 1} 次重试: {e.__class__.__name__}: {str(e)}"
                    )
                    continue
                self.log.warning(f"获取封面图片失败: {e.__class__.__name__}: {str(e)}")
                show_exception(e)
                return None

            # 如果执行到这里说明成功获取了图片，直接返回
            break

        return None

    async def get_cover_image_r18_dev(self, code: str):
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                async with AsyncSession(
                    proxy=get_proxy_str(self.proxy),
                    timeout=10.0,
                    allow_redirects=True,
                    impersonate="chrome110",
                ) as session:
                    # 先获取 content_id
                    detail_url = f"https://r18.dev/videos/vod/movies/detail/-/dvd_id={code.lower()}/json"
                    # 获取 content_id
                    resp: Response = await session.get(detail_url)
                    if resp.status_code != 200:
                        self.log.warning(
                            f"获取影片详情失败: 网址访问错误: {detail_url} ({resp.status_code})."
                        )
                        retry_count += 1
                        if retry_count < max_retries:
                            self.log.info(f"正在进行第 {retry_count + 1} 次重试...")
                            continue
                        return None
                    detail_json = resp.json()
                    content_id = detail_json.get("content_id")
                    if not content_id:
                        self.log.warning(f"获取影片详情失败: 无法获取 content_id: {detail_url}")
                        return None

                    # 获取封面图片 URL
                    combined_url = f"https://r18.dev/videos/vod/movies/detail/-/combined={content_id}/json"
                    resp: Response = await session.get(combined_url)
                    if resp.status_code != 200:
                        self.log.warning(
                            f"获取封面详情失败: 网址访问错误: {combined_url} ({resp.status_code})."
                        )
                        return None
                    combined_json = resp.json()
                    jacket_url = combined_json.get("jacket_thumb_url")
                    if not jacket_url:
                        self.log.warning(f"获取封面详情失败: 无法获取封面URL: {combined_url}")
                        return None

                    # 下载封面图片
                    img_response = await session.get(jacket_url)
                    if img_response.status_code == 200:
                        return BytesIO(img_response.content)
                    else:
                        self.log.warning(
                            f"获取封面图片失败: 网址访问错误: {jacket_url} ({img_response.status_code})."
                        )
                        return None

            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    self.log.info(
                        f"获取封面图片失败，正在进行第 {retry_count + 1} 次重试: {e.__class__.__name__}: {str(e)}"
                    )
                    continue
                self.log.warning(f"获取封面图片失败: {e.__class__.__name__}: {str(e)}")
                show_exception(e)
                return None

        return None

    def compare_images(self, img1_bytes: BytesIO, img2_bytes: BytesIO) -> float:
        try:
            img1 = Image.open(img1_bytes).convert("RGB").resize((100, 100))
            img2 = Image.open(img2_bytes).convert("RGB").resize((100, 100))

            arr1 = np.array(img1)
            arr2 = np.array(img2)
            mse = np.mean((arr1 - arr2) ** 2)

            similarity = 1 / (1 + mse)
            return similarity
        except Exception as e:
            self.log.debug(f"图片比较失败: {e}")
            return 0

    async def on_trigger(self, message: Message, key, reply):
        if not message.photo or not message.reply_markup:
            return
        if pornemby_alert.get(self.client.me.id, False):
            self.log.info(f"由于风险急停不作答.")
            return
        if random.random() > self.config.get("possibility", 1.0):
            self.log.info(f"由于概率设置不作答.")
            return

        question_photo = await message.download(in_memory=True)

        codes = [re.sub(r"-\w$", "", k) for k in key]

        async def get_cover_with_timeout(code):
            try:
                return code, await asyncio.wait_for(self.get_cover_image_javdatabase(code), timeout=10)
            except asyncio.TimeoutError:
                self.log.debug(f"获取 {code} 封面超时")
                return code, None

        cover_tasks = [get_cover_with_timeout(code) for code in codes]
        covers = await asyncio.gather(*cover_tasks)
        max_similarity = -1
        best_code = None
        for code, cover in covers:
            if cover is None:
                continue
            question_photo.seek(0)
            cover.seek(0)
            similarity = self.compare_images(question_photo, cover)
            self.log.debug(f"番号 {code} 相似度: {similarity:.4f}")
            if similarity > max_similarity:
                max_similarity = similarity
                best_code = code
        if best_code:
            result = ["A", "B", "C", "D"][codes.index(best_code)]
            self.log.info(f"选择相似度最高的番号: {best_code} ({result}) (相似度: {max_similarity:.4f})")
            buttons = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            answer_options = self.key_map[result]
            for button_text in buttons:
                if any((o in button_text) for o in answer_options):
                    try:
                        await message.click(button_text)
                    except (TimeoutError, MessageIdInvalid):
                        pass
                    break
            else:
                self.log.info(f"点击失败: 未找到匹配的按钮文本 {result}.")
        else:
            self.log.warning("未找到匹配的封面图片")


class PornembyExamMonitor:
    class PornembyExamResultMonitor(_PornembyExamResultMonitor):
        chat_name = "Pornemby"

    class PornembyExamAnswerMonitor(_PornembyExamAnswerMonitor):
        chat_name = "Pornemby"
