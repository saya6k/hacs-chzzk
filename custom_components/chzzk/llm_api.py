"""Opt-in LLM API registration for Chzzk.

A single ``llm.API`` is registered so "Chzzk" appears as a user-selectable
tool source in a conversation agent's LLM API settings — Chzzk tools are
never contributed to the shared Assist API automatically.

This module must stay a thin shell and never import the ``.llm`` platform
module (or any tool code) at module level: `__init__.py`'s setup path
imports this file, and pulling `.llm` in here would defeat its lazy
loading (see `llm.py`). The one call that needs
`homeassistant.components.llm` — the platform aggregator — is deferred
into `async_get_api_instance`, which only ever runs once a conversation
agent has resolved this API instance, by which point HA's own `llm`
integration is already loaded and the import is a cache hit.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from .const import DOMAIN, LLM_API_ID


class ChzzkLLMAPI(llm.API):
    """The integration-level LLM API. Each conversation agent opts in to it."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass=hass,
            id=LLM_API_ID,
            name="Chzzk",
        )

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        from homeassistant.components.llm import (  # noqa: PLC0415
            async_get_tools as async_get_platform_tools,
        )

        llm_tools = await async_get_platform_tools(self.hass, llm_context, self.id)
        return llm.APIInstance(
            api=self,
            api_prompt=llm_tools.prompt or "",
            llm_context=llm_context,
            tools=llm_tools.tools,
        )


def async_register(hass: HomeAssistant) -> None:
    """Register the API once, idempotently."""
    if hass.data.get(f"{DOMAIN}_llm_registered"):
        return
    llm.async_register_api(hass, ChzzkLLMAPI(hass))
    hass.data[f"{DOMAIN}_llm_registered"] = True
