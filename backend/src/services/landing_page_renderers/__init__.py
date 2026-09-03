"""
Landing Page Renderers

Section HTML renderers for the landing page publish pipeline.
Extracted from landing_page_publish_service.py to keep files under 500 lines.

Each render method converts a section's properties and layout into
standalone static HTML served directly from S3/CloudFront.

The implementation is split across concern mixins under
``services.landing_page_renderers``:

- :class:`~services.landing_page_renderers.dispatch.DispatchMixin`
- :class:`~services.landing_page_renderers.hero.HeroMixin`
- :class:`~services.landing_page_renderers.content.ContentMixin`
- :class:`~services.landing_page_renderers.cta_faq.CtaFaqMixin`
- :class:`~services.landing_page_renderers.testimonials.TestimonialsMixin`
- :class:`~services.landing_page_renderers.media.MediaMixin`
- :class:`~services.landing_page_renderers.pricing.PricingMixin`
"""

from services.landing_page_renderers.content import ContentMixin
from services.landing_page_renderers.cta_faq import CtaFaqMixin
from services.landing_page_renderers.dispatch import DispatchMixin
from services.landing_page_renderers.hero import HeroMixin
from services.landing_page_renderers.media import MediaMixin
from services.landing_page_renderers.pricing import PricingMixin
from services.landing_page_renderers.testimonials import TestimonialsMixin

__all__ = ["LandingPageRenderers"]


class LandingPageRenderers(
    DispatchMixin,
    HeroMixin,
    ContentMixin,
    CtaFaqMixin,
    TestimonialsMixin,
    MediaMixin,
    PricingMixin,
):
    """Section HTML renderers for the landing page publish pipeline."""

    def __init__(self, img_base: str, color_accent: str, color_primary: str):
        self.img_base = img_base
        self.color_accent = color_accent
        self.color_primary = color_primary
