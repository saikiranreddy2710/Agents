"""
Scraper Agent — Extracts structured data from LinkedIn profiles.

Extracts:
  - Basic info: name, headline, location, about
  - Experience: company, title, duration, description
  - Education: school, degree, field, years
  - Skills: top skills list
  - Contact info (if visible)
  - Mutual connections count
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from loguru import logger

from .base_agent import BaseAgent


class ScraperAgent(BaseAgent):
    """
    Scrapes structured data from a LinkedIn profile page.

    Usage:
        result = await agent.run(pc, context={"profile_url": "https://linkedin.com/in/..."})
        profile_data = result["result"]
    """

    def __init__(self, **kwargs):
        super().__init__(name="ScraperAgent", max_steps=8, **kwargs)
        self._profile_url: str = ""
        self._scraped_data: Dict[str, Any] = {}

    @property
    def goal(self) -> str:
        return f"Scrape profile data from: {self._profile_url}"

    async def run(self, page_controller, context: Optional[Dict] = None) -> Dict[str, Any]:
        ctx = context or {}
        self._profile_url = ctx.get("profile_url", "")
        self._scraped_data = {}
        return await super().run(page_controller, context)

    async def execute_step(
        self,
        page_controller,
        screenshot_b64: str,
        experiences: List[Dict],
        step: int,
    ) -> Dict[str, Any]:
        """Execute one scraping step."""

        # Step 1: Navigate to profile
        if step == 1:
            return await self._navigate_to_profile(page_controller)

        # Step 2: Scrape basic info
        if step == 2:
            return await self._scrape_basic_info(page_controller)

        # Step 3: Scroll and scrape experience
        if step == 3:
            return await self._scrape_experience(page_controller)

        # Step 4: Scrape education
        if step == 4:
            return await self._scrape_education(page_controller)

        # Step 5: Scrape skills
        if step == 5:
            return await self._scrape_skills(page_controller)

        # Step 6: Finalize
        if step >= 6:
            return self._finalize()

        return {"action": "wait", "success": True, "done": False}

    # ── Scraping Steps ────────────────────────────────────────────────────────

    async def _navigate_to_profile(self, pc) -> Dict[str, Any]:
        """Navigate to the profile URL."""
        if not self._profile_url:
            return {
                "action": "navigate",
                "success": False,
                "done": True,
                "abort": True,
                "error": "No profile URL provided",
            }

        self.log_step(f"Navigating to: {self._profile_url}")
        result = await pc.navigate(self._profile_url, timeout=20000)
        await pc.wait_for_load(timeout=10000)
        await asyncio.sleep(2)

        # Check if profile loaded
        profile_loaded = await pc.element_exists(
            ".pv-top-card, .profile-view-grid, h1.text-heading-xlarge"
        )

        return {
            "action": "navigate",
            "success": profile_loaded,
            "done": not profile_loaded,
            "error": "" if profile_loaded else "Profile page did not load",
        }

    async def _scrape_basic_info(self, pc) -> Dict[str, Any]:
        """Scrape name, headline, location, about section."""
        self.log_step("Scraping basic info")

        basic = await pc.run_js("""
            () => {
                const getText = (sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.innerText.trim() : '';
                };

                // Name
                const name = getText('h1.text-heading-xlarge') ||
                             getText('.pv-top-card--list li:first-child') || '';

                // Headline
                const headline = getText('.text-body-medium.break-words') ||
                                 getText('.pv-top-card--list-bullet li') || '';

                // Location
                const location = getText('.pv-top-card--list-bullet .text-body-small') ||
                                 getText('.pb2.pv-top-card-v2-ctas__text') || '';

                // Connections
                const connections = getText('.pv-top-card--list-bullet .t-black--light') || '';

                // About
                const about = getText('#about ~ .pvs-list__outer-container .visually-hidden') ||
                              getText('.pv-about-section .pv-about__summary-text') || '';

                // Profile image
                const imgEl = document.querySelector('.pv-top-card__photo img, .profile-photo-edit__preview');
                const image = imgEl ? imgEl.src : '';

                // Current URL
                const url = window.location.href.split('?')[0];

                return { name, headline, location, connections, about, image, url };
            }
        """) or {}

        self._scraped_data.update(basic)
        self.log_step(f"Basic info: {basic.get('name', 'unknown')} — {basic.get('headline', '')[:50]}")

        return {"action": "scrape_basic", "success": bool(basic.get("name")), "done": False}

    async def _scrape_experience(self, pc) -> Dict[str, Any]:
        """Scroll to and scrape work experience."""
        self.log_step("Scraping experience")

        # Scroll to experience section
        await pc.scroll_to_element("#experience")
        await asyncio.sleep(1)

        experience = await pc.run_js("""
            () => {
                const section = document.querySelector('#experience');
                if (!section) return [];

                const items = section.closest('section')
                    ?.querySelectorAll('.pvs-list__paged-list-item') || [];

                return Array.from(items).slice(0, 5).map(item => {
                    const getText = (sel) => {
                        const el = item.querySelector(sel);
                        return el ? el.innerText.trim() : '';
                    };

                    return {
                        title: getText('.t-bold span[aria-hidden="true"]'),
                        company: getText('.t-14.t-normal span[aria-hidden="true"]'),
                        duration: getText('.t-14.t-normal.t-black--light span[aria-hidden="true"]'),
                        description: getText('.pvs-list__outer-container .t-14 span[aria-hidden="true"]'),
                    };
                }).filter(e => e.title || e.company);
            }
        """) or []

        self._scraped_data["experience"] = experience
        self.log_step(f"Found {len(experience)} experience entries")

        return {"action": "scrape_experience", "success": True, "done": False}

    async def _scrape_education(self, pc) -> Dict[str, Any]:
        """Scroll to and scrape education."""
        self.log_step("Scraping education")

        await pc.scroll_to_element("#education")
        await asyncio.sleep(1)

        education = await pc.run_js("""
            () => {
                const section = document.querySelector('#education');
                if (!section) return [];

                const items = section.closest('section')
                    ?.querySelectorAll('.pvs-list__paged-list-item') || [];

                return Array.from(items).slice(0, 3).map(item => {
                    const getText = (sel) => {
                        const el = item.querySelector(sel);
                        return el ? el.innerText.trim() : '';
                    };
                    return {
                        school: getText('.t-bold span[aria-hidden="true"]'),
                        degree: getText('.t-14.t-normal span[aria-hidden="true"]'),
                        years: getText('.t-14.t-normal.t-black--light span[aria-hidden="true"]'),
                    };
                }).filter(e => e.school);
            }
        """) or []

        self._scraped_data["education"] = education
        self.log_step(f"Found {len(education)} education entries")

        return {"action": "scrape_education", "success": True, "done": False}

    async def _scrape_skills(self, pc) -> Dict[str, Any]:
        """Scroll to and scrape top skills."""
        self.log_step("Scraping skills")

        await pc.scroll_to_element("#skills")
        await asyncio.sleep(1)

        skills = await pc.run_js("""
            () => {
                const section = document.querySelector('#skills');
                if (!section) return [];

                const items = section.closest('section')
                    ?.querySelectorAll('.pvs-list__paged-list-item') || [];

                return Array.from(items).slice(0, 10).map(item => {
                    const el = item.querySelector('.t-bold span[aria-hidden="true"]');
                    return el ? el.innerText.trim() : '';
                }).filter(s => s);
            }
        """) or []

        self._scraped_data["skills"] = skills
        self.log_step(f"Found {len(skills)} skills")

        return {"action": "scrape_skills", "success": True, "done": False}

    def _finalize(self) -> Dict[str, Any]:
        """Finalize and return scraped data."""
        self.log_step(
            f"Scraping complete: {self._scraped_data.get('name', 'unknown')}", "info"
        )
        return {
            "action": "finalize",
            "success": bool(self._scraped_data.get("name")),
            "done": True,
            "result": self._scraped_data,
        }
