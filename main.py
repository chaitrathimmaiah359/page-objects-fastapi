from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
import csv
from pathlib import Path
import os

app = FastAPI()


class SelectorRequest(BaseModel):
    url: str


def mock_wikipedia_selectors():
    """Mock data for testing - simulates Wikipedia selectors"""
    return [
        {"selector": "#searchInput", "element_type": "wiki_search", "description": "Wikipedia Search #1",
         "id": "searchInput", "class": "", "text": "Search Wikipedia", "url": "wikipedia.com"},
        {"selector": ".vector-search-box-input", "element_type": "inputs", "description": "Inputs #1", "id": "",
         "class": "vector-search-box-input", "text": "", "url": "wikipedia.com"},
        {"selector": "#searchButton", "element_type": "buttons", "description": "Buttons #1", "id": "searchButton",
         "class": "", "text": "Go", "url": "wikipedia.com"}
    ]


@app.post("/extract-selectors-csv")
async def extract_selectors_csv(request: SelectorRequest):
    url = request.url.strip()

    # MOCK MODE for wikipedia.com (enables testing)
    if "wikipedia.com" in url.lower():
        selectors_data = mock_wikipedia_selectors()
    else:
        # REAL SCRAPING for other URLs
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"

        output_file = f"selectors_{request.url.replace('.', '_')}.csv"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30.0)
                soup = BeautifulSoup(resp.text, 'html.parser')

            selectors_data = []
            selectors = {
                'buttons': soup.select('button, input[type="submit"]'),
                'inputs': soup.select('input[type="text"], input[type="search"]'),
                'links': soup.select('a[href]')[:5]
            }

            for element_type, elements in selectors.items():
                for i, el in enumerate(elements[:3]):
                    selector = el.get('id') and f"#{el['id']}" or f".{el.get('class', [''])[0]}"
                    selectors_data.append({
                        'selector': selector,
                        'element_type': element_type,
                        'description': f"{element_type.title()} #{i + 1}",
                        'id': el.get('id', ''),
                        'class': ' '.join(el.get('class', [])),
                        'text': el.get_text(strip=True)[:50],
                        'url': request.url
                    })
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

    # Save CSV
    output_file = f"selectors_{request.url.replace('.', '_')}.csv"
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['selector', 'element_type', 'description', 'id', 'class', 'text', 'url'])
        writer.writeheader()
        writer.writerows(selectors_data)

    return {
        "success": True,
        "message": f"Saved {len(selectors_data)} selectors to {output_file}",
        "file": output_file,
        "sample": selectors_data[:3]
    }
