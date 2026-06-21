import json
import random
import asyncio
from pathlib import Path
from datetime import datetime
from loguru import logger
from src.config import Config


class WeChatPublisher:
    MP_URL = "https://mp.weixin.qq.com"

    def __init__(self):
        config = Config()
        browser_config = config.get("browser", default={})
        self.headless = browser_config.get("headless", False)
        self.cookie_path = Path(browser_config.get("cookie_path", "data/wechat_cookies.json"))
        self.min_delay = browser_config.get("min_delay", 1.0)
        self.max_delay = browser_config.get("max_delay", 3.0)
        self.screenshot_path = Path(browser_config.get("screenshot_path", "data/screenshots/"))
        self.screenshot_path.mkdir(parents=True, exist_ok=True)
        self.cookie_path.parent.mkdir(parents=True, exist_ok=True)
        self.browser = None
        self.context = None
        self.page = None

    async def _random_delay(self, multiplier=1.0):
        delay = random.uniform(self.min_delay, self.max_delay) * multiplier
        await asyncio.sleep(delay)

    async def _screenshot(self, name):
        path = self.screenshot_path / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        await self.page.screenshot(path=str(path))
        logger.info(f"截图已保存: {path}")

    async def start(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        if self.cookie_path.exists():
            with open(self.cookie_path, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await self.context.add_cookies(cookies)
            logger.info("已加载保存的Cookie")
        self.page = await self.context.new_page()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    async def save_cookies(self):
        cookies = await self.context.cookies()
        with open(self.cookie_path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        logger.info("Cookie已保存")

    async def login(self, force_qr=False):
        await self.page.goto(self.MP_URL, wait_until="networkidle")
        await self._random_delay()

        if not force_qr:
            try:
                await self.page.wait_for_selector(".weui-desktop-account__nickname", timeout=5000)
                logger.info("已登录（Cookie有效）")
                return True
            except Exception:
                logger.info("Cookie已失效，需要扫码登录")

        await self._screenshot("login_page")
        logger.info("=" * 50)
        logger.info("请在浏览器窗口中用微信扫码登录！")
        logger.info("如果看不到二维码，请检查弹出的浏览器窗口")
        logger.info("=" * 50)

        try:
            await self.page.wait_for_url("**/cgi-bin/home**", timeout=120000)
            logger.info("扫码登录成功！")
            await self.save_cookies()
            return True
        except Exception:
            logger.error("登录超时，请重试")
            await self._screenshot("login_timeout")
            return False

    async def is_logged_in(self):
        await self.page.goto(f"{self.MP_URL}/cgi-bin/home", wait_until="networkidle")
        await self._random_delay()
        try:
            await self.page.wait_for_selector(".weui-desktop-account__nickname", timeout=5000)
            return True
        except Exception:
            return False

    async def go_to_drafts(self):
        await self.page.goto(f"{self.MP_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1", wait_until="networkidle")
        await self._random_delay()

    async def publish_draft_via_mass_send(self, draft_media_id=None, confirm_mass_send=False):
        if not confirm_mass_send:
            raise RuntimeError("最终发布需在微信公众号后台手动完成；如确需自动群发，必须显式传入 confirm_mass_send=True")
        try:
            logger.info("开始通过浏览器发布文章...")

            await self.page.goto(
                f"{self.MP_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1",
                wait_until="networkidle",
            )
            await self._random_delay(2)
            await self._screenshot("before_publish")

            publish_btn = self.page.locator("text=群发").first
            await publish_btn.click()
            await self._random_delay()

            await self._screenshot("publish_dialog")
            logger.info("已点击群发按钮")

            confirm_btn = self.page.locator("button:has-text('确定')").first
            await confirm_btn.click()
            await self._random_delay()

            await self._screenshot("after_publish")
            logger.info("文章发布流程完成")
            return True

        except Exception as e:
            logger.error(f"浏览器发布失败: {e}")
            await self._screenshot("publish_error")
            return False

    async def schedule_mass_send(self, publish_time: datetime, confirm_schedule=False):
        if not confirm_schedule:
            raise RuntimeError("定时发送需在微信公众号后台手动完成；如确需自动定时，必须显式传入 confirm_schedule=True")
        try:
            logger.info(f"设置定时发布: {publish_time}")

            await self.page.goto(
                f"{self.MP_URL}/cgi-bin/appmsg?t=media/appmsg_edit_v2&action=edit&isNew=1",
                wait_until="networkidle",
            )
            await self._random_delay(2)

            schedule_btn = self.page.locator("text=定时发送").first
            await schedule_btn.click()
            await self._random_delay()

            time_input = self.page.locator("input[placeholder*='时间']").first
            time_str = publish_time.strftime("%Y-%m-%d %H:%M")
            await time_input.fill(time_str)
            await self._random_delay()

            confirm_btn = self.page.locator("button:has-text('确定')").first
            await confirm_btn.click()
            await self._random_delay()

            await self._screenshot("scheduled")
            logger.info(f"定时发布设置成功: {time_str}")
            return True

        except Exception as e:
            logger.error(f"定时发布设置失败: {e}")
            await self._screenshot("schedule_error")
            return False
