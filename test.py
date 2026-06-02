import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

try:
	import requests
except ImportError:
	requests = None

try:
	from bs4 import BeautifulSoup
except ImportError:
	BeautifulSoup = None


DEFAULT_HEADERS = {
	"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_html(url, timeout=20):
	if requests:
		resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
		resp.raise_for_status()
		return resp.text

	req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		content_type = resp.headers.get("Content-Type", "")
		encoding = "utf-8"
		if "charset=" in content_type:
			encoding = content_type.split("charset=")[-1].split(";")[0].strip()
		return resp.read().decode(encoding, errors="replace")


def make_soup(html, url=None):
	if BeautifulSoup:
		return BeautifulSoup(html, "html.parser")
	raise RuntimeError(
		"BeautifulSoup is required to parse HTML. Install it with `pip install beautifulsoup4`."
	)


def normalize_text(text):
	if not text:
		return ""
	text = re.sub(r"\s+", " ", text)
	return text.strip()


def absolute_url(base_url, link):
	if not link:
		return None
	return urllib.parse.urljoin(base_url, link)


def find_price(text):
	if not text:
		return None
	patterns = [r"\b\d+[\.,]?\d*\s*€", r"€\s*\d+[\.,]?\d*", r"\b\d+[\.,]?\d*\s*EUR\b"]
	for pat in patterns:
		match = re.search(pat, text, re.IGNORECASE)
		if match:
			return normalize_text(match.group(0))
	return None


def get_offer_title(element):
	title = None
	for heading in element.find_all(["h1", "h2", "h3", "h4", "h5"], recursive=False):
		title = normalize_text(heading.get_text())
		if title:
			return title
	if element.name == "a":
		title = normalize_text(element.get_text())
		if title:
			return title
	anchor = element.find("a")
	if anchor:
		title = normalize_text(anchor.get_text())
		if title:
			return title
	return normalize_text(element.get_text())


def build_offer(element, base_url):
	title = get_offer_title(element)
	link = None
	first_a = element.find("a")
	if first_a and first_a.has_attr("href"):
		link = absolute_url(base_url, first_a["href"])
	price = find_price(element.get_text())
	image = None
	first_img = element.find("img")
	if first_img and first_img.has_attr("src"):
		image = absolute_url(base_url, first_img["src"])
	return {
		"title": title,
		"url": link,
		"price": price,
		"image": image,
		"description": normalize_text(element.get_text()),
	}


def find_offer_containers(soup):
	regex = re.compile(r"(offert|offre|deal|promo|promozione|coupon|sconto|volantino|catalogo)", re.I)
	containers = []
	for tag_name in ["article", "section", "li", "div", "ul"]:
		for element in soup.find_all(tag_name):
			attrs_text = " ".join(
				str(v) for v in element.attrs.values() if v is not None
			)
			if regex.search(attrs_text) or regex.search(element.get_text()[:200]):
				containers.append(element)

	if not containers:
		for element in soup.find_all(["article", "section", "li", "div"]):
			if len(normalize_text(element.get_text())) < 30:
				continue
			if element.find("a") and element.find("img"):
				containers.append(element)
				if len(containers) >= 30:
					break
	return containers


def extract_offers(html, base_url):
	soup = make_soup(html, base_url)
	containers = find_offer_containers(soup)
	offers = []
	seen = set()
	for element in containers:
		offer = build_offer(element, base_url)
		key = (offer["title"].lower(), offer["url"] or "")
		if not offer["title"]:
			continue
		if key in seen:
			continue
		seen.add(key)
		offers.append(offer)
	return offers


def print_offers(offers, output_json=False):
	if output_json:
		print(json.dumps(offers, indent=2, ensure_ascii=False))
		return
	if not offers:
		print("No offers found.")
		return
	for idx, offer in enumerate(offers, start=1):
		print(f"Offer {idx}:")
		print(f"  Title: {offer['title']}")
		if offer["price"]:
			print(f"  Price: {offer['price']}")
		if offer["url"]:
			print(f"  URL: {offer['url']}")
		if offer["image"]:
			print(f"  Image: {offer['image']}")
		desc = offer.get("description")
		if desc and desc != offer["title"]:
			print(f"  Description: {desc[:200].strip()}")
		print()


def parse_cli_args():
	parser = argparse.ArgumentParser(
		description="Fetch all offers from a Portale Offerte page or any online offers portal."
	)
	parser.add_argument("url", help="The URL of the portal page containing offers")
	parser.add_argument("--json", action="store_true", help="Output results as JSON")
	parser.add_argument("--limit", type=int, default=0, help="Maximum number of offers to print (0 = all)")
	return parser.parse_args()


def main():
	args = parse_cli_args()
	html = fetch_html(args.url)
	offers = extract_offers(html, args.url)
	if args.limit and len(offers) > args.limit:
		offers = offers[: args.limit]
	print_offers(offers, output_json=args.json)


if __name__ == "__main__":
	main()
