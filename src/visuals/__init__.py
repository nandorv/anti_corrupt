"""Visual generation package — carousel renderer, diagrams, timelines, network graphs."""

from src.visuals.carousel import CarouselRenderer, render_carousel_from_draft
from src.visuals.diagrams import Flowchart, FlowStep, PREDEFINED_FLOWCHARTS, render_flowchart
from src.visuals.network import render_network
from src.visuals.profiles import render_profile_card
from src.visuals.renderer import institution_color, PALETTE, DIMS
from src.visuals.timelines import render_timeline

__all__ = [
    "CarouselRenderer",
    "render_carousel_from_draft",
    "Flowchart",
    "FlowStep",
    "PREDEFINED_FLOWCHARTS",
    "render_flowchart",
    "render_network",
    "render_profile_card",
    "render_timeline",
    "institution_color",
    "PALETTE",
    "DIMS",
]
