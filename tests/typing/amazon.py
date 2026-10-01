"""Code a caller writes against the Amazon models, which `pyrefly check --expectations` checks."""

from typing import Literal, assert_type

import oxyscraper as oxy

ASIN = "1492056359"
URL = "https://www.amazon.de/dp/1492056359"

product = oxy.AmazonProduct(query=ASIN, domain="de", locale="en_GB", currency="GBP")
assert_type(product.source, Literal["amazon_product"])
assert_type(product.query, str)
assert_type(product.autoselect_variant, bool | None)
search = oxy.AmazonSearch(query="usb c cable", sort_by="featured", min_price=1000)
assert_type(search.refinements, list[str] | None)
payloads: list[oxy.Payload] = [
    product,
    search,
    oxy.AmazonPricing(query=ASIN, start_page=2, pages=3),
    oxy.AmazonSellers(query="A2OL0VKAHK1LYK", geo_location="10001"),
    oxy.AmazonBestsellers(query="172541", currency="EUR", geo_location="DE"),
    oxy.Amazon(url=URL, locale="de_DE", render="html"),
]

oxy.AmazonSearch(query="a", sort_by="newest")  # E: 'newest'
oxy.AmazonProduct(query=ASIN, domain="uk")  # E: 'uk'
oxy.AmazonProduct(query=ASIN, locale="en-US")  # E: 'en-US'
oxy.AmazonProduct(query=ASIN, currency="usd")  # E: 'usd'
oxy.AmazonProduct(query=ASIN, pages=2)  # E: Unexpected keyword argument `pages`
oxy.AmazonPricing(query=ASIN, currency="EUR")  # E: Unexpected keyword argument
oxy.AmazonSellers(query="A", currency="EUR")  # E: Unexpected keyword argument
oxy.AmazonBestsellers(query="1", user_agent_type="mobile")  # E: Unexpected keyword
oxy.Amazon(url=URL, domain="de")  # E: Unexpected keyword argument `domain`
oxy.Amazon(url=URL, query=ASIN)  # E: Unexpected keyword argument `query`
oxy.AmazonSearch(query="a", url=URL)  # E: Unexpected keyword argument `url`
oxy.AmazonSearch(query="a", limit=10)  # E: Unexpected keyword argument `limit`
oxy.AmazonSellers()  # E: Missing argument `query`
