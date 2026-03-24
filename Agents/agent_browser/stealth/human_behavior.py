"""
Human Behavior — Mimics human browsing patterns to avoid bot detection.

Techniques:
  - Random delays between actions (Gaussian distribution)
  - Bezier curve mouse movements
  - Natural scroll patterns (variable speed, occasional pauses)
  - Random micro-pauses while typing
  - Occasional "reading" pauses before clicking
"""

from __future__ import annotations

import asyncio
import math
import random
from typing import Any, List, Optional, Tuple

from loguru import logger


class HumanBehavior:
    """
    Injects human-like behavior into browser interactions.

    All delays and movements are randomized within realistic ranges
    to avoid pattern detection by LinkedIn's bot detection systems.
    """

    def __init__(
        self,
        min_delay: float = 0.5,
        max_delay: float = 3.0,
        typing_delay_ms: int = 80,
        reading_speed_wpm: int = 200,
    ):
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.typing_delay_ms = typing_delay_ms
        self.reading_speed_wpm = reading_speed_wpm

    # ── Delays ────────────────────────────────────────────────────────────────

    async def think_pause(self, min_s: float = 0.5, max_s: float = 2.0) -> None:
        """Short pause simulating human thinking before an action."""
        delay = random.gauss((min_s + max_s) / 2, (max_s - min_s) / 4)
        delay = max(min_s, min(max_s, delay))
        await asyncio.sleep(delay)

    async def reading_pause(self, text_length: int = 100) -> None:
        """
        Pause proportional to text length (simulates reading).
        Based on average reading speed of 200 WPM.
        """
        words = text_length / 5  # avg 5 chars per word
        minutes = words / self.reading_speed_wpm
        seconds = minutes * 60
        # Add some randomness
        seconds = seconds * random.uniform(0.7, 1.3)
        seconds = max(0.5, min(8.0, seconds))
        await asyncio.sleep(seconds)

    async def action_delay(self) -> None:
        """Standard delay between actions."""
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)

    async def micro_pause(self) -> None:
        """Very short pause (100-400ms) for micro-interactions."""
        await asyncio.sleep(random.uniform(0.1, 0.4))

    async def page_load_wait(self) -> None:
        """Wait after page load (simulates user orienting themselves)."""
        await asyncio.sleep(random.uniform(1.0, 3.0))

    # ── Mouse Movement ────────────────────────────────────────────────────────

    async def move_to_element(
        self,
        page,
        selector: str,
        steps: int = 20,
    ) -> bool:
        """
        Move mouse to an element using a Bezier curve path.
        More natural than teleporting directly to the element.
        """
        try:
            element = page.locator(selector).first
            box = await element.bounding_box()
            if not box:
                return False

            # Target: center of element with slight randomness
            target_x = box["x"] + box["width"] / 2 + random.uniform(-5, 5)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-5, 5)

            # Get current mouse position (approximate)
            current_x = random.uniform(100, 800)
            current_y = random.uniform(100, 600)

            # Generate Bezier curve points
            points = self._bezier_curve(
                (current_x, current_y),
                (target_x, target_y),
                steps=steps,
            )

            # Move along the curve
            for x, y in points:
                await page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.005, 0.02))

            return True
        except Exception as e:
            logger.debug(f"Mouse move failed (non-critical): {e}")
            return False

    async def human_click(
        self,
        page,
        selector: str,
        move_first: bool = True,
    ) -> bool:
        """
        Click an element with human-like mouse movement and timing.
        """
        try:
            if move_first:
                await self.move_to_element(page, selector)
                await self.micro_pause()

            element = page.locator(selector).first
            await element.click(delay=random.randint(50, 150))
            return True
        except Exception as e:
            logger.debug(f"Human click failed: {e}")
            return False

    # ── Scrolling ─────────────────────────────────────────────────────────────

    async def natural_scroll(
        self,
        page,
        direction: str = "down",
        total_amount: int = 1000,
    ) -> None:
        """
        Scroll naturally with variable speed and occasional pauses.
        Mimics how humans scroll — fast then slow, with reading pauses.
        """
        remaining = total_amount
        while remaining > 0:
            # Variable scroll amount per step
            step = random.randint(100, 300)
            step = min(step, remaining)

            scroll_y = step if direction == "down" else -step
            await page.evaluate(
                f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})"
            )
            remaining -= step

            # Occasional reading pause
            if random.random() < 0.3:
                await asyncio.sleep(random.uniform(0.5, 2.0))
            else:
                await asyncio.sleep(random.uniform(0.1, 0.4))

    async def scroll_and_read(
        self,
        page,
        scroll_amount: int = 2000,
    ) -> None:
        """Scroll through a page as if reading it."""
        await self.natural_scroll(page, "down", scroll_amount)
        await self.reading_pause(scroll_amount // 5)

    # ── Typing ────────────────────────────────────────────────────────────────

    def get_typing_delay(self) -> int:
        """Get a randomized typing delay in ms."""
        base = self.typing_delay_ms
        # Gaussian distribution around base delay
        delay = int(random.gauss(base, base * 0.3))
        return max(30, min(300, delay))

    async def human_type(
        self,
        page,
        selector: str,
        text: str,
        clear_first: bool = True,
    ) -> bool:
        """
        Type text with human-like timing variations.
        Includes occasional typos and corrections (optional).
        """
        try:
            element = page.locator(selector).first
            await element.wait_for(state="visible")

            if clear_first:
                await element.clear()
                await self.micro_pause()

            # Type with variable delays
            for char in text:
                await element.type(char, delay=self.get_typing_delay())

                # Occasional longer pause (thinking)
                if random.random() < 0.05:
                    await asyncio.sleep(random.uniform(0.3, 0.8))

            return True
        except Exception as e:
            logger.debug(f"Human type failed: {e}")
            return False

    # ── Session Behavior ──────────────────────────────────────────────────────

    async def random_idle_action(self, page) -> None:
        """
        Perform a random idle action to appear more human.
        (Move mouse, scroll slightly, etc.)
        """
        action = random.choice(["move_mouse", "scroll_tiny", "pause"])

        if action == "move_mouse":
            x = random.randint(200, 700)
            y = random.randint(200, 500)
            await page.mouse.move(x, y)

        elif action == "scroll_tiny":
            amount = random.randint(50, 150)
            direction = random.choice([1, -1])
            await page.evaluate(f"window.scrollBy(0, {amount * direction})")

        else:
            await asyncio.sleep(random.uniform(0.5, 1.5))

    # ── Bezier Curve ──────────────────────────────────────────────────────────

    def _bezier_curve(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        steps: int = 20,
    ) -> List[Tuple[float, float]]:
        """
        Generate points along a quadratic Bezier curve from start to end.
        Creates a natural curved mouse path.
        """
        # Random control point for curve shape
        cp_x = (start[0] + end[0]) / 2 + random.uniform(-100, 100)
        cp_y = (start[1] + end[1]) / 2 + random.uniform(-100, 100)

        points = []
        for i in range(steps + 1):
            t = i / steps
            # Quadratic Bezier formula
            x = (1 - t) ** 2 * start[0] + 2 * (1 - t) * t * cp_x + t ** 2 * end[0]
            y = (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * cp_y + t ** 2 * end[1]
            points.append((x, y))

        return points
