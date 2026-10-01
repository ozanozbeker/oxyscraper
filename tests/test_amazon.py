from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

import oxyscraper as oxy

Model = Callable[..., oxy.Payload]
ASIN = "1492056359"
URL = "https://www.amazon.com/dp/1492056359"
INPUTS: dict[Model, dict[str, str]] = {
    oxy.Amazon: {"url": URL},
    oxy.AmazonBestsellers: {"query": "172541"},
    oxy.AmazonPricing: {"query": ASIN},
    oxy.AmazonProduct: {"query": ASIN},
    oxy.AmazonSearch: {"query": "usb c cable"},
    oxy.AmazonSellers: {"query": "A2OL0VKAHK1LYK"},
}
OTHER_SOURCES = {
    "product_id": "1",
    "prompt": "a",
    "video_id": "a",
    "channel_handle": "@a",
    "limit": 10,
}
LEFT_OUT = [
    *((model, key, value) for model in INPUTS for key, value in OTHER_SOURCES.items()),
    *((model, "url", URL) for model in INPUTS if model is not oxy.Amazon),
    *(
        (model, "category_id", "16391693031")
        for model in INPUTS
        if model is not oxy.AmazonSearch
    ),
    *(
        (model, key, 2)
        for model in (oxy.Amazon, oxy.AmazonProduct, oxy.AmazonSellers)
        for key in ("start_page", "pages")
    ),
    (oxy.Amazon, "query", ASIN),
    (oxy.Amazon, "domain", "de"),
    (oxy.AmazonPricing, "currency", "EUR"),
    (oxy.AmazonSellers, "currency", "EUR"),
    (oxy.AmazonBestsellers, "user_agent_type", "mobile"),
    *(
        (model, "sort_by", "featured")
        for model in INPUTS
        if model is not oxy.AmazonSearch
    ),
]


def test_context_fields() -> None:
    """A model fixes `source` and moves its typed `context` keys into the `context` list, before the other items."""
    payload = oxy.AmazonProduct(
        query=ASIN,
        autoselect_variant=True,
        currency="EUR",
        domain="de",
        context=[{"key": "session_id", "value": "abc"}],
        extra={"context": [{"key": "force_headers", "value": True}]},
    )
    assert payload.model_dump() == {
        "source": "amazon_product",
        "query": ASIN,
        "domain": "de",
        "context": [
            {"key": "autoselect_variant", "value": True},
            {"key": "currency", "value": "EUR"},
            {"key": "session_id", "value": "abc"},
            {"key": "force_headers", "value": True},
        ],
    }


@pytest.mark.parametrize(("model", "key", "value"), LEFT_OUT)
def test_left_out(model: Model, key: str, value: object) -> None:
    """A parameter that the source does not take, or that bills with no effect, raises as an unknown keyword."""
    with pytest.raises(
        ValidationError, match=rf"{key}\n  Extra inputs are not permitted"
    ):
        model(**INPUTS[model], **{key: value})


def test_sources() -> None:
    """`SOURCES` lists the six Amazon models."""
    assert set(oxy.SOURCES) >= set(INPUTS)


@pytest.mark.parametrize(
    ("model", "source"),
    [
        (oxy.Amazon, "amazon"),
        (oxy.AmazonBestsellers, "amazon_bestsellers"),
        (oxy.AmazonPricing, "amazon_pricing"),
        (oxy.AmazonProduct, "amazon_product"),
        (oxy.AmazonSearch, "amazon_search"),
        (oxy.AmazonSellers, "amazon_sellers"),
    ],
)
def test_source(model: Model, source: str) -> None:
    """Each model fixes its `source`, and its body holds the input alone by default."""
    assert model(**INPUTS[model]).model_dump() == {"source": source, **INPUTS[model]}
    with pytest.raises(ValidationError, match="source"):
        model(**INPUTS[model], source="universal")


@pytest.mark.parametrize(
    ("model", "fields", "message"),
    [
        (oxy.AmazonProduct, {"query": "14920563599"}, "at most 10 characters"),
        (oxy.AmazonPricing, {"query": "14920563599"}, "at most 10 characters"),
        (oxy.AmazonBestsellers, {"query": "abc"}, "should match pattern"),
        (oxy.AmazonBestsellers, {"query": ""}, "should match pattern"),
        (oxy.AmazonBestsellers, {"query": "172541 "}, "should match pattern"),
        (oxy.AmazonSearch, {"query": "a", "min_price": 0}, "greater than 0"),
        (oxy.AmazonSearch, {"query": "a", "max_price": 0}, "greater than 0"),
    ],
)
def test_input_rules(model: Model, fields: dict[str, Any], message: str) -> None:
    """An 11-character ASIN, a node ID that is not a number, and a price of 0 raise, because the API bills each."""
    with pytest.raises(ValidationError, match=message):
        model(**fields)


RENDERED = [model for model in INPUTS if model is not oxy.AmazonBestsellers]


@pytest.mark.parametrize("model", RENDERED)
@pytest.mark.parametrize(
    "fields",
    [
        {"render": "html", "user_agent_type": "mobile"},
        {"render": "png", "user_agent_type": "desktop"},
        {"user_agent_type": "mobile", "extra": {"render": "html"}},
    ],
)
def test_user_agent_type_with_render(model: Model, fields: dict[str, Any]) -> None:
    """`user_agent_type` with `render` raises, because a rendered job ignores it."""
    with pytest.raises(ValidationError, match="user_agent_type"):
        model(**INPUTS[model], **fields)


@pytest.mark.parametrize("model", RENDERED)
@pytest.mark.parametrize(
    "fields", [{"render": "html"}, {"user_agent_type": "mobile", "render": ""}]
)
def test_user_agent_type_or_render(model: Model, fields: dict[str, Any]) -> None:
    """`render` alone, or `user_agent_type` with forced rendering turned off, passes."""
    assert model(**INPUTS[model], **fields).model_dump().items() >= fields.items()


CURRENCY_MODELS = [oxy.AmazonBestsellers, oxy.AmazonProduct, oxy.AmazonSearch]


@pytest.mark.parametrize("model", CURRENCY_MODELS)
@pytest.mark.parametrize(
    "fields",
    [
        {"currency": "EUR"},
        {"currency": "EUR", "domain": "com"},
        {"currency": "EUR", "geo_location": "10001"},
        {"currency": "EUR", "geo_location": "de"},
        {"extra": {"context": [{"key": "currency", "value": "EUR"}]}},
    ],
)
def test_currency_on_com(model: Model, fields: dict[str, Any]) -> None:
    """A currency other than USD on `com` raises without a 2-letter `geo_location`, because the API bills prices in USD."""
    with pytest.raises(ValidationError, match="geo_location"):
        model(**INPUTS[model], **fields)


@pytest.mark.parametrize("model", CURRENCY_MODELS)
@pytest.mark.parametrize(
    "fields",
    [
        {"currency": "USD"},
        {"currency": "EUR", "geo_location": "DE"},
        {"currency": "EUR", "domain": "de"},
        {"domain": "ie", "extra": {"context": [{"key": "currency", "value": "XYZ"}]}},
    ],
)
def test_currency(model: Model, fields: dict[str, Any]) -> None:
    """USD on `com`, another currency with a country code on `com`, and any currency on another domain pass."""
    model(**INPUTS[model], **fields)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.amazon.com/dp/1492056359",
        "https://amazon.com/s?k=usb",
        "https://smile.amazon.com/dp/1492056359",
    ],
)
def test_currency_on_amazon_com(url: str) -> None:
    """On `amazon`, the currency check reads the domain from the URL's host."""
    with pytest.raises(ValidationError, match="geo_location"):
        oxy.Amazon(url=url, currency="EUR")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.amazon.de/dp/1492056359",
        "https://www.amazon.com.au/dp/1492056359",
        "https://www.amazon.co.uk/dp/1492056359",
        "https://example.com",
    ],
)
def test_currency_on_amazon_elsewhere(url: str) -> None:
    """On `amazon`, a URL outside `amazon.com` takes any currency."""
    assert oxy.Amazon(url=url, currency="EUR").model_dump()["context"] == [
        {"key": "currency", "value": "EUR"}
    ]


# The values that the API's 400s listed in the run of `docs/research/live-amazon.md`.
LOCALES = {
    "ae": ["en_AE", "ar_AE"],
    "ca": ["fr_CA", "en_CA"],
    "cn": ["zh_CN"],
    "co.jp": ["ja_JP", "en_US", "zh_CN"],
    "co.uk": ["en_GB"],
    "com": [
        "en_US",
        "es_US",
        "ar_AE",
        "de_US",
        "he_IL",
        "ko_KR",
        "pt_BR",
        "zh_CN",
        "zh_TW",
    ],
    "com.au": ["en_AU"],
    "com.be": ["fr_BE", "nl_BE", "en_GB"],
    "com.br": ["pt_BR"],
    "com.mx": ["es_MX"],
    "com.tr": ["tr_TR"],
    "de": ["de_DE", "en_GB", "cs_CZ", "nl_NL", "pl_PL", "tr_TR", "da_DK"],
    "eg": ["ar_AE", "en_AE"],
    "es": ["es_ES", "pt_PT", "en_GB"],
    "fr": ["fr_FR", "en_GB"],
    "ie": ["en_IE"],
    "in": ["en_IN", "hi_IN", "ta_IN", "te_IN", "kn_IN", "ml_IN", "bn_IN", "mr_IN"],
    "it": ["it_IT", "en_GB"],
    "nl": ["nl_NL", "en_GB"],
    "pl": ["pl_PL"],
    "sa": ["ar_AE", "en_AE"],
    "se": ["sv_SE", "en_GB"],
    "sg": ["en_SG"],
    "co.za": ["en_ZA"],
}
CURRENCIES = [
    "AED", "AMD", "ARS", "AUD", "AWG", "AZN", "BBD", "BGN", "BHD", "BMD", "BND", "BOB", "BRL",
    "BSD", "BZD", "CAD", "CHF", "CLP", "CNY", "COP", "CRC", "CZK", "DKK", "DOP", "EGP", "EUR",
    "GBP", "GHS", "GTQ", "HKD", "HNL", "HUF", "IDR", "ILS", "INR", "JMD", "JOD", "JPY", "KES",
    "KHR", "KRW", "KWD", "KYD", "KZT", "LBP", "LKR", "MAD", "MNT", "MOP", "MUR", "MXN", "MYR",
    "NAD", "NGN", "NOK", "NZD", "OMR", "PAB", "PEN", "PHP", "PKR", "PLN", "PYG", "QAR", "RON",
    "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TTD", "TWD", "TZS", "USD", "UYU", "VND", "XCD",
    "ZAR",
]  # fmt: skip
QUERY_MODELS = [model for model in INPUTS if model is not oxy.Amazon]


@pytest.mark.parametrize("model", QUERY_MODELS)
@pytest.mark.parametrize(
    ("domain", "locale"),
    [(domain, locale) for domain, locales in LOCALES.items() for locale in locales],
)
def test_locales(model: Model, domain: str, locale: str) -> None:
    """Each model takes the 24 domains and each of their locales."""
    body = model(**INPUTS[model], domain=domain, locale=locale).model_dump()
    assert (body["domain"], body["locale"]) == (domain, locale)


@pytest.mark.parametrize(
    "locale", sorted({locale for locales in LOCALES.values() for locale in locales})
)
def test_locales_on_amazon(locale: str) -> None:
    """`amazon` takes each of the 40 locales."""
    assert oxy.Amazon.model_validate({"url": URL, "locale": locale}).locale == locale


@pytest.mark.parametrize("model", [*CURRENCY_MODELS, oxy.Amazon])
@pytest.mark.parametrize("currency", CURRENCIES)
def test_currencies(model: Model, currency: str) -> None:
    """Each model with `currency` takes the 79 codes that the API allows on some domain."""
    model(**INPUTS[model], currency=currency, geo_location="DE")


@pytest.mark.parametrize(
    "sort_by",
    [
        "most_recent",
        "price_low_to_high",
        "price_high_to_low",
        "featured",
        "average_review",
        "bestsellers",
    ],
)
def test_sort_by(sort_by: str) -> None:
    """`amazon_search` takes the six `sort_by` values."""
    payload = oxy.AmazonSearch.model_validate({"query": "a", "sort_by": sort_by})
    assert payload.model_dump()["context"] == [{"key": "sort_by", "value": sort_by}]


@pytest.mark.parametrize(
    ("model", "field", "value"),
    [
        *(
            (model, "domain", value)
            for model in QUERY_MODELS
            for value in ["uk", "COM", "amazon.com", ""]
        ),
        *(
            (model, "locale", value)
            for model in INPUTS
            for value in ["en-US", "en_us", "xx_XX"]
        ),
        *(
            (model, "currency", value)
            for model in [*CURRENCY_MODELS, oxy.Amazon]
            for value in ["usd", "XYZ"]
        ),
        (oxy.AmazonSearch, "sort_by", "Featured"),
        (oxy.AmazonSearch, "sort_by", ""),
    ],
)
def test_values_raise(model: Model, field: str, value: str) -> None:
    """A value outside a value set raises."""
    with pytest.raises(ValidationError, match=field):
        model(**INPUTS[model], **{field: value})
