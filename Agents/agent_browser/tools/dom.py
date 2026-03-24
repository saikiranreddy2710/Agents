"""DOM tool — Extract structured information from the page DOM."""
from __future__ import annotations
import time
from typing import Any, Dict, List, Optional


async def dom(
    page,
    action: str = "text",
    selector: Optional[str] = None,
    attribute: Optional[str] = None,
    max_length: int = 5000,
) -> Dict[str, Any]:
    """
    Extract DOM information from the page.

    Args:
        page:       Playwright page object
        action:     What to extract:
                      "text"       → visible text content of page/element
                      "html"       → inner HTML of element
                      "attribute"  → specific attribute value
                      "links"      → all links on page
                      "inputs"     → all input fields
                      "buttons"    → all clickable buttons
                      "structure"  → simplified DOM structure summary
                      "exists"     → check if selector exists
                      "count"      → count matching elements
        selector:   CSS selector (optional, defaults to full page)
        attribute:  Attribute name for "attribute" action
        max_length: Max characters to return for text/html

    Returns:
        {"success": bool, "action": str, "data": any, "error": str|None}
    """
    start = time.time()

    try:
        if action == "text":
            if selector:
                elements = page.locator(selector)
                count = await elements.count()
                if count == 0:
                    return {"success": False, "action": action, "data": None,
                            "error": f"No elements found for selector: {selector}"}
                text = await elements.first.inner_text()
            else:
                text = await page.inner_text("body")
            return {
                "success": True, "action": action,
                "data": text[:max_length],
                "truncated": len(text) > max_length,
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "html":
            if selector:
                element = page.locator(selector).first
                html = await element.inner_html()
            else:
                html = await page.content()
            return {
                "success": True, "action": action,
                "data": html[:max_length],
                "truncated": len(html) > max_length,
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "attribute":
            if not selector or not attribute:
                return {"success": False, "action": action, "data": None,
                        "error": "selector and attribute are required for 'attribute' action"}
            element = page.locator(selector).first
            value = await element.get_attribute(attribute)
            return {
                "success": True, "action": action,
                "data": value,
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "links":
            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim().substring(0, 100),
                    href: a.href,
                    aria_label: a.getAttribute('aria-label') || ''
                })).filter(l => l.href && !l.href.startsWith('javascript:'))
            """)
            return {
                "success": True, "action": action,
                "data": links[:100],  # Max 100 links
                "count": len(links),
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "inputs":
            inputs = await page.evaluate("""
                () => Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
                    tag: el.tagName.toLowerCase(),
                    type: el.type || '',
                    name: el.name || '',
                    id: el.id || '',
                    placeholder: el.placeholder || '',
                    value: el.value ? el.value.substring(0, 50) : '',
                    aria_label: el.getAttribute('aria-label') || '',
                    visible: el.offsetParent !== null
                }))
            """)
            return {
                "success": True, "action": action,
                "data": inputs,
                "count": len(inputs),
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "buttons":
            buttons = await page.evaluate("""
                () => Array.from(document.querySelectorAll(
                    'button, [role="button"], input[type="submit"], input[type="button"], a.btn'
                )).map(el => ({
                    text: el.innerText.trim().substring(0, 100),
                    aria_label: el.getAttribute('aria-label') || '',
                    class: el.className.substring(0, 100),
                    id: el.id || '',
                    disabled: el.disabled || false,
                    visible: el.offsetParent !== null
                })).filter(b => b.visible)
            """)
            return {
                "success": True, "action": action,
                "data": buttons[:50],  # Max 50 buttons
                "count": len(buttons),
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "structure":
            # Simplified DOM structure for LLM context
            structure = await page.evaluate("""
                () => {
                    const important = ['h1','h2','h3','h4','nav','main','header','footer',
                                       'form','button','input','a','[role]'];
                    const els = document.querySelectorAll(important.join(','));
                    return Array.from(els).slice(0, 50).map(el => ({
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText.trim().substring(0, 80),
                        role: el.getAttribute('role') || '',
                        id: el.id || '',
                        class: el.className.substring(0, 60)
                    }));
                }
            """)
            return {
                "success": True, "action": action,
                "data": structure,
                "url": page.url,
                "title": await page.title(),
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "exists":
            if not selector:
                return {"success": False, "action": action, "data": False,
                        "error": "selector is required for 'exists' action"}
            count = await page.locator(selector).count()
            return {
                "success": True, "action": action,
                "data": count > 0,
                "count": count,
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        elif action == "count":
            if not selector:
                return {"success": False, "action": action, "data": 0,
                        "error": "selector is required for 'count' action"}
            count = await page.locator(selector).count()
            return {
                "success": True, "action": action,
                "data": count,
                "duration_ms": int((time.time() - start) * 1000), "error": None,
            }

        else:
            return {
                "success": False, "action": action, "data": None,
                "error": f"Unknown action: '{action}'. Use: text|html|attribute|links|inputs|buttons|structure|exists|count",
            }

    except Exception as e:
        return {
            "success": False, "action": action, "data": None,
            "duration_ms": int((time.time() - start) * 1000),
            "error": str(e),
        }
