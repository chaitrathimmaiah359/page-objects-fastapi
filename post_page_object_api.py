from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import aiohttp
from bs4 import BeautifulSoup
from pathlib import Path
import uvicorn
from urllib.parse import urljoin, urlparse

app = FastAPI(title="Locator Management API with URL Scraping")

# JSON file to store locators
LOCATORS_FILE = Path("locators.json")


class Locator(BaseModel):
    xpath: Optional[str] = None
    css: Optional[str] = None
    attribute: Optional[Dict[str, str]] = None
    priority: int = 1


class LocatorSet(BaseModel):
    element_name: str
    tag: str = "div"
    locators: List[Locator] = []
    class_name: Optional[str] = None
    url: Optional[str] = None


class UrlScrapingRequest(BaseModel):
    url: str
    element_name: str
    tag: str = "div"
    class_name: Optional[str] = None


# Load/save locators
def load_locators() -> Dict[str, LocatorSet]:
    if LOCATORS_FILE.exists():
        with open(LOCATORS_FILE, 'r') as f:
            data = json.load(f)
            # Convert dicts to Locator objects
            for element_name, locator_set in data.items():
                locator_set['locators'] = [Locator(**loc) for loc in locator_set['locators']]
            return {k: LocatorSet(**v) for k, v in data.items()}
    return {}


def save_locators(locators: Dict[str, LocatorSet]):
    data = {k: {
        'element_name': v.element_name,
        'tag': v.tag,
        'locators': [l.dict() for l in v.locators],
        'class_name': v.class_name,
        'url': v.url
    } for k, v in locators.items()}
    with open(LOCATORS_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_locator_store():
    return load_locators()


# Generate locators from HTML element
def generate_locators(element, element_name: str) -> List[Locator]:
    locators = []

    # 1. CSS Selector (highest priority)
    css = f"{element.name}"
    if element.get('id'):
        css += f"#{element.get('id')}"
    if element.get('class'):
        css += "." + ".".join(element.get('class', []))
    locators.append(Locator(css=css, priority=3))

    # 2. XPath fallback
    xpath = element.get('xpath', f"//{element.name}")
    locators.append(Locator(xpath=xpath, priority=2))

    # 3. Attributes fallback (data-testid, name, etc.)
    for attr in ['data-testid', 'data-test', 'name', 'aria-label']:
        if element.get(attr):
            locators.append(Locator(attribute={attr: element[attr]}, priority=1))

    return locators


async def scrape_url_and_find_element(url: str, element_name: str, tag: str = "div", class_name: Optional[str] = None):
    """Scrape URL and auto-generate locators for specified element"""
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')

            # Find element by tag and class
            selector = f"{tag}"
            if class_name:
                selector += f".{class_name}"

            elements = soup.select(selector)
            if not elements:
                raise HTTPException(status_code=404, detail=f"No {tag} elements with class '{class_name}' found")

            # Use first matching element
            element = elements[0]

            # Generate locators
            locators = generate_locators(element, element_name)

            return LocatorSet(
                element_name=element_name,
                tag=tag,
                locators=locators,
                class_name=class_name,
                url=url
            )


@app.post("/locators/from-url/", response_model=Dict[str, LocatorSet])
async def create_locators_from_url(
        request: UrlScrapingRequest,
        locators_store: Dict[str, LocatorSet] = Depends(get_locator_store)
):
    """Create locators by scraping URL and finding element"""
    locator_set = await scrape_url_and_find_element(
        request.url, request.element_name, request.tag, request.class_name
    )

    # Sort by priority and save
    locator_set.locators.sort(key=lambda x: x.priority, reverse=True)
    locators_store[request.element_name] = locator_set
    save_locators(locators_store)

    return locators_store


@app.get("/locators/{element_name}/scrape", response_model=LocatorSet)
async def scrape_and_get_locators(
        element_name: str,
        url: str = Query(...),
        tag: str = Query("div"),
        class_name: Optional[str] = Query(None)
):
    """One-shot: Scrape URL and return locators immediately"""
    locator_set = await scrape_url_and_find_element(url, element_name, tag, class_name)
    locator_set.locators.sort(key=lambda x: x.priority, reverse=True)
    return locator_set


# Existing endpoints (unchanged)
@app.post("/locators/")
async def add_locator(locator_set: LocatorSet, locators_store: Dict = Depends(get_locator_store)):
    locators_store[locator_set.element_name] = locator_set
    locator_set.locators.sort(key=lambda x: x.priority, reverse=True)
    save_locators(locators_store)
    return locators_store


@app.get("/locators/{element_name}", response_model=LocatorSet)
async def get_locators(element_name: str, locators_store: Dict = Depends(get_locator_store)):
    if element_name not in locators_store:
        raise HTTPException(status_code=404, detail="Element not found")
    return locators_store[element_name]


@app.get("/locators/{element_name}/selector")
async def get_primary_selector(element_name: str, locators_store: Dict = Depends(get_locator_store)):
    if element_name not in locators_store:
        raise HTTPException(status_code=404, detail="Element not found")

    locator_set = locators_store[element_name]
    primary_locator = locator_set.locators[0]

    selector_parts = [locator_set.tag]
    if locator_set.class_name:
        selector_parts.append(f".{locator_set.class_name}")
    if primary_locator.css:
        selector_parts.append(primary_locator.css)

    return {
        "element_name": element_name,
        "primary_selector": "".join(selector_parts),
        "full_locator_set": locator_set
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)
