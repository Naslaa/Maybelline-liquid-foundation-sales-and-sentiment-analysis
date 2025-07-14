from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import pandas as pd
import time
import os

# Flexible extraction functions (name, price, image, ingredients from before)
def extract_name(soup):
    for tag in soup.select('h1, h2'):
        text = tag.get_text(strip=True)
        if len(text) > 4:
            return text
    return "N/A"

def extract_price(soup):
    for tag in soup.select('span, div'):
        txt = tag.get_text(strip=True).lower()
        if "$" in txt or "usd" in txt:
            return txt
    return "N/A"

def extract_image(soup):
    try:
        img_tag = soup.select_one('img[src*="product"]')
        return img_tag['src']
    except:
        return "N/A"

def extract_ingredients(soup):
    for tag in soup.select('div, section, p'):
        if 'ingredient' in tag.get_text(strip=True).lower():
            return tag.get_text(separator=' ', strip=True)
    return "N/A"

def extract_shades(soup):
    shade_candidates = set()

    selectors = []
    selectors.extend(soup.find_all(lambda tag: tag.has_attr('class') and any('shade' in c.lower() for c in tag['class'])))
    selectors.extend(soup.find_all(lambda tag: tag.has_attr('id') and 'shade' in tag['id'].lower()))
    selectors.extend(soup.find_all(lambda tag: tag.has_attr('aria-label') and 'shade' in tag['aria-label'].lower()))
    selectors.extend(soup.find_all(lambda tag: tag.has_attr('title') and 'shade' in tag['title'].lower()))

    for elem in selectors:
        for descendant in elem.descendants:
            if hasattr(descendant, 'get_text'):
                txt = descendant.get_text(strip=True)
                if txt:
                    shade_candidates.add(txt)
            elif descendant.has_attr('alt'):
                shade_candidates.add(descendant['alt'])
            elif descendant.has_attr('title'):
                shade_candidates.add(descendant['title'])

    shades = list(filter(lambda x: x.strip() != '', shade_candidates))
    return shades if shades else ["N/A"]

# -------------------- NEW: Extract sales proxies --------------------

def extract_sales_proxies(soup):
    # Number of reviews from rating summary or review count text
    num_reviews = "N/A"
    review_count_tags = soup.find_all(string=lambda text: text and ("review" in text.lower() or "rating" in text.lower()))
    for text in review_count_tags:
        # Try to extract digits from text like "123 Reviews" or "4.5 stars (200 Reviews)"
        import re
        matches = re.findall(r'(\d[\d,]*)', text)
        if matches:
            num_reviews = matches[0].replace(',', '')
            break

    # Bestseller tag detection (look for keyword in text)
    bestseller = any("bestseller" in s.lower() for s in soup.stripped_strings)

    # Stock status heuristic
    stock_status = "In stock"
    stock_out_indicators = ["out of stock", "sold out", "unavailable"]
    page_text = " ".join(soup.stripped_strings).lower()
    for phrase in stock_out_indicators:
        if phrase in page_text:
            stock_status = "Out of stock"
            break

    return {
        "number_of_reviews": num_reviews,
        "bestseller": bestseller,
        "stock_status": stock_status
    }

# -------------------- NEW: Extract reviews (first page) --------------------

def extract_reviews(soup):
    reviews_data = []

    # Find review containers - heuristic: look for elements containing "review" in class or id
    review_containers = soup.find_all(lambda tag: tag.has_attr('class') and any('review' in c.lower() for c in tag['class']))

    for container in review_containers:
        # Extract star rating (heuristic: look for aria-label or alt or title or text with 'star')
        star_rating = "N/A"
        rating_tag = container.find(lambda tag: tag.has_attr('aria-label') and 'star' in tag['aria-label'].lower())
        if not rating_tag:
            rating_tag = container.find('img', alt=lambda alt: alt and 'star' in alt.lower())
        if rating_tag:
            star_rating = rating_tag.get('aria-label') or rating_tag.get('alt')

        # Extract review text
        review_text = container.get_text(separator=' ', strip=True)

        # Extract review date (look for date patterns or elements with 'date' in class/id)
        review_date = "N/A"
        date_tag = container.find(lambda tag: tag.has_attr('class') and 'date' in tag['class'][0].lower())
        if date_tag:
            review_date = date_tag.get_text(strip=True)

        # Reviewer location or name (look for class/id with 'author', 'name', or 'location')
        reviewer = "N/A"
        reviewer_tag = container.find(lambda tag: tag.has_attr('class') and any(x in tag['class'][0].lower() for x in ['author', 'name', 'location']))
        if reviewer_tag:
            reviewer = reviewer_tag.get_text(strip=True)

        # Verified purchase (look for text 'verified purchase' nearby)
        verified = any("verified purchase" in s.lower() for s in container.stripped_strings)

        # Helpful votes (look for text like 'X people found this helpful')
        helpful_votes = "N/A"
        for s in container.stripped_strings:
            if "found this helpful" in s.lower():
                import re
                m = re.search(r'(\d+)', s)
                if m:
                    helpful_votes = m.group(1)
                    break

        reviews_data.append({
            "star_rating": star_rating,
            "review_text": review_text,
            "review_date": review_date,
            "reviewer": reviewer,
            "verified_purchase": verified,
            "helpful_votes": helpful_votes
        })

    return reviews_data

# -------------------- Main scraping function --------------------

def scrape_product(driver, url):
    driver.get(url)
    time.sleep(5)  # Wait for JS to load

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    product_info = {
        "url": url,
        "name": extract_name(soup),
        "price": extract_price(soup),
        "type": "Foundation",
        "shades": extract_shades(soup),
        "image": extract_image(soup),
        "ingredients": extract_ingredients(soup),
    }

    sales_proxies = extract_sales_proxies(soup)
    reviews = extract_reviews(soup)

    # Flatten reviews into strings for CSV; you might want to save raw JSON separately for deep analysis
    reviews_summary = []
    for r in reviews:
        snippet = f"{r['star_rating']} | {r['review_text'][:100]} | {r['review_date']} | Verified: {r['verified_purchase']} | Helpful: {r['helpful_votes']}"
        reviews_summary.append(snippet)
    product_info.update(sales_proxies)
    product_info["reviews"] = " || ".join(reviews_summary) if reviews_summary else "N/A"

    return product_info

# -------------------- Runner --------------------

if __name__ == "__main__":
    options = Options()
    options.headless = False
    driver = webdriver.Chrome(options=options)

    product_urls = [
        # Add your product URLs here
    ]

    results = []
    output_file = "maybelline_products_with_reviews.csv"
    os.makedirs("output", exist_ok=True)
    output_path = os.path.join("output", output_file)

    for url in product_urls:
        try:
            print(f"Scraping: {url}")
            data = scrape_product(driver, url)
            results.append(data)

            # Save incrementally
            df = pd.DataFrame(results)
            df.to_csv(output_path, index=False)
            print(f"Saved {len(results)} products to {output_path}")
        except Exception as e:
            print(f"Error scraping {url}: {e}")

    driver.quit()
    print("Scraping complete!")
