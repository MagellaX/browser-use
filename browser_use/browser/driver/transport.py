from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from .messages import BridgeCommand, BridgeEvent, BridgeHandshake, BridgeResponse, BridgeResponseStatus


class BridgeError(RuntimeError):
	"""Base exception for bridge transport failures."""


class BridgeTimeoutError(BridgeError):
	"""Raised when a command response does not arrive within the allotted time."""


class BridgeDisconnectedError(BridgeError):
	"""Raised when attempting to use the transport while disconnected."""


class SocketBridgeClient:
	"""Lightweight WebSocket client for communicating with the browser extension bridge."""

	def __init__(
		self,
		endpoint: str,
		*,
		connect_timeout: float = 10.0,
		default_response_timeout: float = 30.0,
	):
		self.endpoint = endpoint
		self.connect_timeout = connect_timeout
		self.default_response_timeout = default_response_timeout

		self._connection: Any | None = None
		self._connected = False
		self._receive_task: asyncio.Task[None] | None = None
		self._pending: dict[str, asyncio.Future[BridgeResponse]] = {}
		self._pending_lock = asyncio.Lock()
		self._event_queue: asyncio.Queue[BridgeEvent] = asyncio.Queue()
		self._handshake: BridgeHandshake | None = None
		self._handshake_event = asyncio.Event()
		self._event_handlers: list[Callable[[BridgeEvent], Coroutine[Any, Any, None]]] = []

	async def connect(self) -> BridgeHandshake:
		if self._connected and self._handshake and self._connection is not None:
			return self._handshake

		self._handshake = None
		self._handshake_event.clear()
		self._connection = await connect(self.endpoint, open_timeout=self.connect_timeout)
		self._receive_task = asyncio.create_task(self._receive_loop())
		await asyncio.wait_for(self._handshake_event.wait(), timeout=self.connect_timeout)
		assert self._handshake is not None
		self._connected = True
		return self._handshake

	async def disconnect(self) -> None:
		if self._receive_task:
			self._receive_task.cancel()
			with contextlib.suppress(BaseException):
				await self._receive_task
			self._receive_task = None
		if self._connection is not None:
			await self._connection.close()
		self._connection = None
		self._connected = False
		self._handshake = None
		self._handshake_event.clear()

	@property
	def handshake(self) -> BridgeHandshake | None:
		return self._handshake

	def is_connected(self) -> bool:
		return self._connected

	async def emit_command(
		self,
		command: BridgeCommand,
		*,
		response_timeout: float | None = None,
	) -> BridgeResponse:
		if not self.is_connected():
			raise BridgeDisconnectedError('Socket bridge is not connected')

		loop = asyncio.get_running_loop()
		future: asyncio.Future[BridgeResponse] = loop.create_future()
		async with self._pending_lock:
			self._pending[command.request_id] = future

		payload = json.dumps(command.model_dump(by_alias=True))
		assert self._connection is not None
		await self._connection.send(payload)
		timeout = response_timeout or self.default_response_timeout
		try:
			response = await asyncio.wait_for(future, timeout=timeout)
		except asyncio.TimeoutError as exc:
			async with self._pending_lock:
				self._pending.pop(command.request_id, None)
			raise BridgeTimeoutError(f'Command {command.action} timed out after {timeout}s') from exc
		if response.status == BridgeResponseStatus.ERROR:
			raise BridgeError(response.error or f'Command {command.action} failed')
		return response

	async def execute_action(
		self,
		action: str,
		payload: dict[str, Any] | None = None,
		*,
		response_timeout: float | None = None,
	) -> BridgeResponse:
		command = BridgeCommand(action=action, payload=payload or {})
		return await self.emit_command(command, response_timeout=response_timeout)

	async def next_event(self, timeout: float | None = None) -> BridgeEvent:
		if timeout is None:
			return await self._event_queue.get()
		return await asyncio.wait_for(self._event_queue.get(), timeout=timeout)

	def register_event_handler(self, handler: Callable[[BridgeEvent], Coroutine[Any, Any, None]]) -> None:
		self._event_handlers.append(handler)

	async def _receive_loop(self) -> None:
		assert self._connection is not None
		try:
			async for raw in self._connection:
				try:
					message = json.loads(raw)
				except json.JSONDecodeError:
					continue
				type_name = message.get('type')
				if type_name == 'handshake':
					self._handshake = BridgeHandshake.model_validate(message)
					self._handshake_event.set()
				elif type_name == 'response':
					await self._handle_response(message)
				elif type_name == 'event':
					await self._handle_event(message)
		except (ConnectionClosed, WebSocketException):
			pass
		finally:
			self._connected = False
			await self._reject_all_pending()

	async def _handle_response(self, data: dict[str, Any]) -> None:
		response = BridgeResponse.model_validate(data)
		async with self._pending_lock:
			future = self._pending.pop(response.request_id, None)
		if future and not future.done():
			future.set_result(response)

	async def _handle_event(self, data: dict[str, Any]) -> None:
		event = BridgeEvent.model_validate(data)
		await self._event_queue.put(event)
		for handler in self._event_handlers:
			asyncio.create_task(self._dispatch_event(handler, event))

	async def _dispatch_event(
		self, handler: Callable[[BridgeEvent], Coroutine[Any, Any, None]], event: BridgeEvent
	) -> None:
		await handler(event)

	async def _reject_all_pending(self) -> None:
		async with self._pending_lock:
			for future in self._pending.values():
				if not future.done():
					future.set_exception(BridgeDisconnectedError('Socket bridge disconnected'))
			self._pending.clear()
