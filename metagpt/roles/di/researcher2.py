#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import re
from typing import Optional
from pydantic import BaseModel, Field

from metagpt.actions import CollectLinks, ConductResearch, WebBrowseAndSummarize
from metagpt.actions.research import get_research_system_text
from metagpt.const import RESEARCH_PATH
from metagpt.logs import logger
from metagpt.roles.di.role_zero import RoleZero
from metagpt.schema import Message


class Report(BaseModel):
    topic: str
    links: Optional[dict[str, list[str]]] = None
    summaries: Optional[list[tuple[str, str]]] = None
    content: str = ""


class Researcher2(RoleZero):
    name: str = "David"
    profile: str = "Researcher"
    goal: str = "Gather information and conduct research"
    constraints: str = "Ensure accuracy and relevance of information"
    language: str = "en-us"
    enable_concurrency: bool = True

    tools: list[str] = ["CollectLinks", "WebBrowseAndSummarize", "ConductResearch"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._init_tools()

    def _init_tools(self):
        self.tool_execution_map.update(
            {
                "CollectLinks": self._collect_links,
                "WebBrowseAndSummarize": self._web_browse_and_summarize,
                "ConductResearch": self._conduct_research,
            }
        )

    async def _collect_links(self, topic: str) -> dict[str, list[str]]:
        """Collect relevant links for a given topic."""
        action = CollectLinks(context=self.context)
        links = await action.run(topic, 4, 4)
        return links

    async def _web_browse_and_summarize(
        self, topic: str, links: dict[str, list[str]]
    ) -> list[tuple[str, str]]:
        """Browse web pages and summarize their content."""
        action = WebBrowseAndSummarize(context=self.context)
        system_text = get_research_system_text(topic, self.language)
        todos = (
            action.run(*url, query=query, system_text=system_text)
            for (query, url) in links.items()
            if url
        )
        if self.enable_concurrency:
            summaries = await asyncio.gather(*todos)
        else:
            summaries = [await i for i in todos]
        summaries = list(
            (url, summary) for i in summaries for (url, summary) in i.items() if summary
        )
        return summaries

    async def _conduct_research(
        self, topic: str, summaries: list[tuple[str, str]]
    ) -> str:
        """Conduct research and generate a report based on summaries."""
        action = ConductResearch(context=self.context)
        system_text = get_research_system_text(topic, self.language)
        summary_text = "\n---\n".join(
            f"url: {url}\nsummary: {summary}" for (url, summary) in summaries
        )
        content = await action.run(topic, summary_text, system_text=system_text)
        self._write_report(topic, content)
        return content

    def _write_report(self, topic: str, content: str):
        filename = re.sub(r'[\\/:"*?<>|]+', " ", topic)
        filename = filename.replace("\n", "")
        if not RESEARCH_PATH.exists():
            RESEARCH_PATH.mkdir(parents=True)
        filepath = RESEARCH_PATH / f"{filename}.md"
        filepath.write_text(content)
        logger.info(f"Report written to {filepath}")
        return str(filepath)
