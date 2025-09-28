from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from browser_use.browser.driver.capabilities import (
	BrowserDriverCapabilities,
	DriverActionCapability,
	DriverFeature,
)
from browser_use.browser.driver.messages import BridgeCommand
from browser_use.browser.driver.protocol import BrowserDriver
from browser_use.browser.driver.transport import BridgeDisconnectedError, BridgeError, BridgeTimeoutError, SocketBridgeClient


FallbackHandler = Callable[[dict[str, Any] | None], Awaitable[Any]]


class SocketBridgeDriver(BrowserDriver):
	"""Browser driver that talks to a Chrome extension bridge via Socket.IO."""

	name = 'chrome-extension-bridge'

	def __init__(
		self,
		endpoint: str,
		*,
		browser_session: Any | None = None,
		default_capabilities: BrowserDriverCapabilities | None = None,
	):
		self._transport = SocketBridgeClient(endpoint=endpoint)
		self._running = False
		self._session = browser_session
		self._capabilities = default_capabilities or BrowserDriverCapabilities(driver_name=self.name)
		self._fallbacks: dict[str, FallbackHandler] = {}
		self._configure_default_fallbacks()

	@property
	def capabilities(self) -> BrowserDriverCapabilities:
		return self._capabilities

	def _configure_default_fallbacks(self) -> None:
		if not self._session:
			return

		session = self._session

		async def list_tabs(_: dict[str, Any] | None) -> dict[str, Any]:
			assert session.browser_context
			tabs = []
			for index, page in enumerate(session.tabs):
				tabs.append(
					{
						'id': getattr(page, 'target', None) or index,
						'index': index,
						'url': page.url,
						'title': await page.title(),
						'is_active': page == session.agent_current_page,
					}
				)
			return {'tabs': tabs}

		async def activate_tab(payload: dict[str, Any] | None) -> dict[str, Any]:
			assert payload is not None
			tab_index = payload.get('index')
			assert isinstance(tab_index, int)
			await session.switch_to_tab(tab_index)
			return {'result': 'ok'}

		async def open_tab(payload: dict[str, Any] | None) -> dict[str, Any]:
			url = payload.get('url') if payload else None
			page = await session.create_new_tab(url)
			return {'result': 'ok', 'url': page.url}

		async def close_tab(payload: dict[str, Any] | None) -> dict[str, Any]:
			index = payload.get('index') if payload else None
			assert isinstance(index, int)
			await session.switch_to_tab(index)
			page = await session.get_current_page()
			await page.close()
			return {'result': 'ok'}

		self._fallbacks = {
			'tabs.list': list_tabs,
			'tabs.activate': activate_tab,
			'tabs.open': open_tab,
			'tabs.close': close_tab,
		}

	async def start(self) -> None:
		if self._running:
			return

		handshake = await self._transport.connect()
		incoming_caps = handshake.driver_capabilities or {}
		if incoming_caps:
			self._capabilities = BrowserDriverCapabilities.model_validate(incoming_caps)
		else:
			self._capabilities.driver_name = self.name

		if not self._capabilities.actions:
			for action_name in self._fallbacks.keys():
				self._capabilities.add_action(DriverActionCapability(action=action_name, description='Fallback via BrowserSession'))
			self._capabilities.enable_feature(DriverFeature.TAB_FOREGROUND_DETECTION)

		if self._session and hasattr(self._session, 'set_driver_capabilities'):
			self._session.set_driver_capabilities(self._capabilities)

		self._running = True

	async def stop(self) -> None:
		if not self._running:
			return
		await self._transport.disconnect()
		self._running = False

	async def execute(self, action_name: str, payload: dict[str, Any] | None = None) -> Any:
		if not self._running:
			if action_name in self._fallbacks:
				return await self._fallbacks[action_name](payload)
			raise BridgeDisconnectedError('Driver not connected')

		if not self._capabilities.supports_action(action_name) and action_name in self._fallbacks:
			return await self._fallbacks[action_name](payload)

		command = BridgeCommand(action=action_name, payload=payload or {})
		try:
			response = await self._transport.emit_command(command)
		except (BridgeTimeoutError, BridgeDisconnectedError):
			if action_name in self._fallbacks:
				return await self._fallbacks[action_name](payload)
			raise
		if response.result is None:
			return {'status': response.status.value}
		return response.result

	def is_running(self) -> bool:
		return self._running
