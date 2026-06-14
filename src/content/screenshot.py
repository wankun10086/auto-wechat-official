import asyncio
import re
from pathlib import Path
from datetime import datetime
from loguru import logger


class ScreenshotCapture:
    def __init__(self, screenshot_dir="data/screenshots"):
        self.screenshot_dir = Path(screenshot_dir)
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.browser = None
        self.context = None
        self.page = None
        self._pw = None

    async def start(self, headless=True):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        self.browser = await self._pw.chromium.launch(headless=headless)
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 900},
            device_scale_factor=2,
        )
        self.page = await self.context.new_page()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self._pw:
            await self._pw.stop()

    async def capture_url(self, url: str, targets: list = None) -> list:
        if not self.page:
            await self.start()

        await self.page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        if targets is None:
            targets = ["code", "charts", "tables"]
        if "all" in targets:
            targets = ["code", "charts", "tables", "images", "fullpage"]

        results = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if "fullpage" in targets:
            path = await self._capture_fullpage(timestamp)
            if path:
                results.append(path)

        if "code" in targets:
            code_shots = await self._capture_code_blocks(timestamp)
            results.extend(code_shots)

        if "charts" in targets:
            chart_shots = await self._capture_elements(timestamp, "charts")
            results.extend(chart_shots)

        if "tables" in targets:
            table_shots = await self._capture_elements(timestamp, "tables")
            results.extend(table_shots)

        if "images" in targets:
            img_shots = await self._capture_elements(timestamp, "images")
            results.extend(img_shots)

        logger.info(f"共截取 {len(results)} 张图片")
        return results

    async def _capture_fullpage(self, timestamp):
        path = self.screenshot_dir / f"fullpage_{timestamp}.png"
        await self.page.screenshot(path=str(path), full_page=True)
        return {"path": str(path), "description": "页面全文截图", "type": "fullpage"}

    async def _capture_code_blocks(self, timestamp):
        results = []
        code_selectors = [
            "pre code", "pre", ".highlight", ".code-block",
            "[class*=language-]", ".CodeMirror", ".cm-editor",
            "code[class*=lang]",
        ]

        seen = set()
        for sel in code_selectors:
            elements = await self.page.query_selector_all(sel)
            for i, el in enumerate(elements):
                try:
                    box = await el.bounding_box()
                    if not box or box["width"] < 100 or box["height"] < 50:
                        continue
                    key = f"{int(box['x'])}_{int(box['y'])}_{int(box['width'])}"
                    if key in seen:
                        continue
                    seen.add(key)

                    path = self.screenshot_dir / f"code_{timestamp}_{len(results)}.png"
                    await el.screenshot(path=str(path))

                    text = await el.inner_text()
                    lang = ""
                    cls = await el.get_attribute("class") or ""
                    lang_match = re.search(r"language-(\w+)", cls)
                    if lang_match:
                        lang = lang_match.group(1)

                    desc = f"代码块" + (f" ({lang})" if lang else "")
                    if text:
                        first_line = text.strip().split("\n")[0][:60]
                        desc += f": {first_line}"

                    results.append({"path": str(path), "description": desc, "type": "code"})
                except Exception:
                    continue

        return results[:10]

    async def _capture_elements(self, timestamp, element_type):
        results = []

        type_selectors = {
            "charts": ["canvas", "svg[class*=chart]", ".chart", ".graph", "[class*=visualization]", "iframe[src*=chart]"],
            "tables": ["table", ".table", "[role=grid]"],
            "images": ["article img", ".content img", "main img", ".post img"],
        }

        selectors = type_selectors.get(element_type, [])
        seen = set()

        for sel in selectors:
            elements = await self.page.query_selector_all(sel)
            for el in elements:
                try:
                    box = await el.bounding_box()
                    if not box or box["width"] < 80 or box["height"] < 80:
                        continue
                    key = f"{int(box['x'])}_{int(box['y'])}_{int(box['width'])}"
                    if key in seen:
                        continue
                    seen.add(key)

                    path = self.screenshot_dir / f"{element_type}_{timestamp}_{len(results)}.png"
                    await el.screenshot(path=str(path))

                    desc = {"charts": "图表", "tables": "表格", "images": "图片"}.get(element_type, element_type)
                    alt = await el.get_attribute("alt")
                    if alt:
                        desc += f": {alt[:50]}"

                    results.append({"path": str(path), "description": desc, "type": element_type})
                except Exception:
                    continue

        return results[:10]
