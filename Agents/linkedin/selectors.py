"""
LinkedIn Selectors — All CSS selectors for LinkedIn UI elements.

LinkedIn frequently updates its UI. All selectors are centralized here
so the EvolutionAgent can update them in one place when they break.

Each selector has:
  - Primary:   Most reliable selector
  - Fallbacks: Alternative selectors if primary fails
  - Context:   Where this selector is used
"""

from __future__ import annotations
from typing import List


class LinkedInSelectors:
    """
    Centralized CSS selector registry for LinkedIn UI elements.

    Usage:
        sel = LinkedInSelectors()
        connect_btn = sel.CONNECT_BUTTON.primary
        # or try all fallbacks:
        for selector in sel.CONNECT_BUTTON.all:
            if await pc.element_exists(selector):
                await pc.click_selector(selector)
                break
    """

    class Selector:
        """A selector with primary + fallback options."""
        def __init__(self, primary: str, fallbacks: List[str] = None, context: str = ""):
            self.primary = primary
            self.fallbacks = fallbacks or []
            self.context = context

        @property
        def all(self) -> List[str]:
            """All selectors in priority order."""
            return [self.primary] + self.fallbacks

        def __str__(self) -> str:
            return self.primary

    # ── Login Page ────────────────────────────────────────────────────────────

    EMAIL_INPUT = Selector(
        primary="input#username",
        fallbacks=["input[name='session_key']", "input[autocomplete='username']"],
        context="login_page",
    )

    PASSWORD_INPUT = Selector(
        primary="input#password",
        fallbacks=["input[name='session_password']", "input[type='password']"],
        context="login_page",
    )

    LOGIN_BUTTON = Selector(
        primary="button[type='submit'][data-litms-control-urn='login-submit']",
        fallbacks=["button[type='submit']", "button:has-text('Sign in')"],
        context="login_page",
    )

    LOGIN_ERROR = Selector(
        primary="#error-for-password",
        fallbacks=[".alert-error", ".form__error--is-shown"],
        context="login_page",
    )

    # ── Global Navigation ─────────────────────────────────────────────────────

    SEARCH_BAR = Selector(
        primary="input.search-global-typeahead__input",
        fallbacks=["input[placeholder*='Search']", "#global-nav-search input"],
        context="global_nav",
    )

    NAV_HOME = Selector(
        primary="a[href='/feed/']",
        fallbacks=["a[data-link-to='home']"],
        context="global_nav",
    )

    NAV_NETWORK = Selector(
        primary="a[href='/mynetwork/']",
        fallbacks=["a[data-link-to='mynetwork']"],
        context="global_nav",
    )

    NAV_MESSAGING = Selector(
        primary="a[href='/messaging/']",
        fallbacks=["a[data-link-to='messaging']"],
        context="global_nav",
    )

    # ── Profile Page ──────────────────────────────────────────────────────────

    PROFILE_NAME = Selector(
        primary="h1.text-heading-xlarge",
        fallbacks=[".pv-top-card--list li:first-child h1", ".profile-view-grid h1"],
        context="profile_page",
    )

    PROFILE_HEADLINE = Selector(
        primary=".text-body-medium.break-words",
        fallbacks=[".pv-top-card--list-bullet li:first-child", ".pv-top-card__headline"],
        context="profile_page",
    )

    PROFILE_LOCATION = Selector(
        primary=".pv-top-card--list-bullet .text-body-small",
        fallbacks=[".pv-top-card-v2-ctas__text", ".pv-top-card__location"],
        context="profile_page",
    )

    PROFILE_ABOUT = Selector(
        primary="#about ~ .pvs-list__outer-container .visually-hidden",
        fallbacks=[".pv-about-section .pv-about__summary-text", "#about + div"],
        context="profile_page",
    )

    CONNECT_BUTTON = Selector(
        primary="button.pvs-profile-actions__action[aria-label*='Connect']",
        fallbacks=[
            "button[aria-label*='Connect with']",
            "button[aria-label='Connect']",
            ".pv-s-profile-actions button:has-text('Connect')",
            ".pvs-profile-actions button:has-text('Connect')",
        ],
        context="profile_page",
    )

    MESSAGE_BUTTON = Selector(
        primary="button[aria-label*='Message']",
        fallbacks=[
            ".pv-s-profile-actions button:has-text('Message')",
            ".pvs-profile-actions button:has-text('Message')",
            "a[href*='/messaging/thread/']",
        ],
        context="profile_page",
    )

    FOLLOW_BUTTON = Selector(
        primary="button[aria-label*='Follow']",
        fallbacks=[".pvs-profile-actions button:has-text('Follow')"],
        context="profile_page",
    )

    MORE_ACTIONS_BUTTON = Selector(
        primary="button[aria-label='More actions']",
        fallbacks=["button:has-text('More')", ".pvs-profile-actions__overflow-toggle"],
        context="profile_page",
    )

    PENDING_BUTTON = Selector(
        primary="button[aria-label*='Pending']",
        fallbacks=["button[aria-label='Withdraw invitation']", "button:has-text('Pending')"],
        context="profile_page",
    )

    # ── Connection Request Dialog ─────────────────────────────────────────────

    CONNECT_DIALOG = Selector(
        primary=".send-invite__actions",
        fallbacks=[".artdeco-modal[aria-labelledby*='send-invite']", "[data-test-modal]"],
        context="connect_dialog",
    )

    ADD_NOTE_BUTTON = Selector(
        primary="button[aria-label='Add a note']",
        fallbacks=["button:has-text('Add a note')", ".send-invite__free-btn"],
        context="connect_dialog",
    )

    NOTE_TEXTAREA = Selector(
        primary="textarea#custom-message",
        fallbacks=[
            "textarea[name='message']",
            ".send-invite__custom-message textarea",
            ".connect-button-send-invite__custom-message textarea",
        ],
        context="connect_dialog",
    )

    SEND_INVITE_BUTTON = Selector(
        primary="button[aria-label='Send now']",
        fallbacks=[
            "button[aria-label='Send invitation']",
            "button:has-text('Send')",
            ".artdeco-modal__actionbar button.artdeco-button--primary",
        ],
        context="connect_dialog",
    )

    DISMISS_DIALOG = Selector(
        primary="button[aria-label='Dismiss']",
        fallbacks=["button.artdeco-modal__dismiss", "button[data-test-modal-close-btn]"],
        context="connect_dialog",
    )

    # ── Search Results ────────────────────────────────────────────────────────

    SEARCH_RESULT_CARDS = Selector(
        primary=".reusable-search__result-container li",
        fallbacks=[".search-results__list li", ".search-results-container li"],
        context="search_results",
    )

    SEARCH_RESULT_NAME = Selector(
        primary=".entity-result__title-text a span[aria-hidden='true']",
        fallbacks=[".actor-name", ".entity-result__title-line a"],
        context="search_results",
    )

    SEARCH_RESULT_TITLE = Selector(
        primary=".entity-result__primary-subtitle",
        fallbacks=[".subline-level-1", ".entity-result__summary"],
        context="search_results",
    )

    SEARCH_RESULT_COMPANY = Selector(
        primary=".entity-result__secondary-subtitle",
        fallbacks=[".subline-level-2"],
        context="search_results",
    )

    SEARCH_RESULT_LINK = Selector(
        primary="a.app-aware-link[href*='/in/']",
        fallbacks=["a[href*='linkedin.com/in/']"],
        context="search_results",
    )

    SEARCH_NEXT_PAGE = Selector(
        primary="button[aria-label='Next']",
        fallbacks=[".artdeco-pagination__button--next", "button:has-text('Next')"],
        context="search_results",
    )

    # ── Messaging ─────────────────────────────────────────────────────────────

    MESSAGE_COMPOSE = Selector(
        primary=".msg-form__contenteditable",
        fallbacks=[
            "[data-placeholder='Write a message…']",
            "div[role='textbox'][aria-label*='message']",
            ".msg-form__msg-content-container--scrollable",
        ],
        context="messaging",
    )

    MESSAGE_SEND_BUTTON = Selector(
        primary="button.msg-form__send-button",
        fallbacks=[
            "button[aria-label='Send']",
            "button:has-text('Send')",
            ".msg-form__send-btn",
        ],
        context="messaging",
    )

    MESSAGE_THREAD = Selector(
        primary=".msg-s-message-list__event",
        fallbacks=[".msg-s-event-listitem", ".msg-s-message-group"],
        context="messaging",
    )

    # ── Profile Sections ──────────────────────────────────────────────────────

    EXPERIENCE_SECTION = Selector(
        primary="#experience",
        fallbacks=[".pv-experience-section", "section:has(#experience)"],
        context="profile_sections",
    )

    EDUCATION_SECTION = Selector(
        primary="#education",
        fallbacks=[".pv-education-section", "section:has(#education)"],
        context="profile_sections",
    )

    SKILLS_SECTION = Selector(
        primary="#skills",
        fallbacks=[".pv-skill-categories-section", "section:has(#skills)"],
        context="profile_sections",
    )

    EXPERIENCE_ITEMS = Selector(
        primary="#experience ~ .pvs-list__outer-container .pvs-list__paged-list-item",
        fallbacks=[".pv-experience-section li.pv-entity__position-group-pager"],
        context="profile_sections",
    )

    # ── Notifications / Warnings ──────────────────────────────────────────────

    CAPTCHA = Selector(
        primary=".captcha-container",
        fallbacks=["#captcha", "iframe[src*='captcha']", ".recaptcha-checkbox"],
        context="security",
    )

    SECURITY_CHECKPOINT = Selector(
        primary=".checkpoint-challenge",
        fallbacks=["#checkpoint-challenge", ".two-step-challenge"],
        context="security",
    )

    RATE_LIMIT_WARNING = Selector(
        primary=".artdeco-inline-feedback--error",
        fallbacks=[".error-container", "[data-test-error]"],
        context="security",
    )

    # ── Utility ───────────────────────────────────────────────────────────────

    @classmethod
    def get_all(cls) -> dict:
        """Get all selectors as a dict."""
        return {
            name: getattr(cls, name)
            for name in dir(cls)
            if isinstance(getattr(cls, name), cls.Selector)
        }

    @classmethod
    def get_by_context(cls, context: str) -> dict:
        """Get all selectors for a specific context."""
        return {
            name: sel
            for name, sel in cls.get_all().items()
            if sel.context == context
        }
