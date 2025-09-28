from __future__ import annotations

import abc
from typing import Any, Protocol, runtime_checkable

from .capabilities import BrowserDriverCapabilities


@runtime_checkable
class BrowserDriver(Protocol):
	"""Protocol describing the runtime contract for browser drivers."""

	name: str

	@property
	@abc.abstractmethod
	def capabilities(self) -> BrowserDriverCapabilities:  # pragma: no cover - simple property signature
		"""Return the current capability manifest for the driver."""

	@abc.abstractmethod
	async def start(self) -> None:
		"""Start or connect to the underlying automation backend."""

	@abc.abstractmethod
	async def stop(self) -> None:
		"""Tear down any resources allocated by :meth:`start`."""

	@abc.abstractmethod
	async def execute(self, action_name: str, payload: dict[str, Any] | None = None) -> Any:
		"""Execute an action previously registered in :attr:`capabilities`."""

	@abc.abstractmethod
	def is_running(self) -> bool:
		"""Return True when the driver backend is considered ready for new work."""
