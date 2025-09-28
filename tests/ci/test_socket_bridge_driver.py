import json

import pytest

from browser_use.browser.driver import (
	BridgeHandshake,
	BridgeResponse,
	BridgeResponseStatus,
	BrowserDriverCapabilities,
	DriverActionCapability,
	DriverFeature,
)
from browser_use.browser.driver.socket_driver import SocketBridgeDriver
from websockets.asyncio.server import serve


class StubPage:
	def __init__(self, url: str, title: str):
		self.url = url
		self._title = title
		self.closed = False

	async def title(self) -> str:
		return self._title

	async def close(self) -> None:
		self.closed = True


class StubSession:
	def __init__(self) -> None:
		self.browser_context = object()
		self.tabs = [StubPage('https://example.com', 'Example Domain')]
		self.agent_current_page = self.tabs[0]
		self._driver_capabilities = None

	async def switch_to_tab(self, index: int) -> None:
		self.agent_current_page = self.tabs[index]

	async def create_new_tab(self, url: str | None = None):
		page = StubPage(url or 'about:blank', 'New Tab')
		self.tabs.append(page)
		self.agent_current_page = page
		return page

	async def get_current_page(self):
		return self.agent_current_page

	def set_driver_capabilities(self, capabilities):
		self._driver_capabilities = capabilities

	@property
	def driver_capabilities(self):
		return self._driver_capabilities


async def test_fallback_executes_without_transport():
	session = StubSession()
	driver = SocketBridgeDriver(endpoint='ws://localhost:9999', browser_session=session)
	result = await driver.execute('tabs.list')
	assert isinstance(result, dict)
	assert len(result['tabs']) == 1
	assert result['tabs'][0]['url'] == 'https://example.com'


async def test_start_updates_capabilities(monkeypatch):
	session = StubSession()
	driver = SocketBridgeDriver(endpoint='ws://localhost:9999', browser_session=session)

	capabilities = BrowserDriverCapabilities(driver_name='ext-driver')
	capabilities.add_action(DriverActionCapability(action='tabs.list', description='List tabs'))

	handshake = BridgeHandshake(driver_capabilities=capabilities.model_dump())

	async def fake_connect(self):
		return handshake

	async def fake_disconnect(self):
		return None

	monkeypatch.setattr(driver, '_transport', type('Dummy', (), {'connect': fake_connect, 'disconnect': fake_disconnect})())

	await driver.start()
	assert driver.is_running()
	assert driver.capabilities.driver_name == 'ext-driver'
	assert session.driver_capabilities is not None
	assert 'tabs.list' in session.driver_capabilities.actions


async def test_execute_uses_transport(monkeypatch):
	session = StubSession()
	driver = SocketBridgeDriver(endpoint='ws://localhost:9999', browser_session=session)
	driver._capabilities.add_action(DriverActionCapability(action='tabs.list', description='List tabs via bridge'))
	driver._running = True

	async def fake_emit(self, command):
		return BridgeResponse(
			request_id=command.request_id,
			action=command.action,
			status=BridgeResponseStatus.OK,
			result={'tabs': []},
		)

	monkeypatch.setattr(driver, '_transport', type('DummyTransport', (), {'emit_command': fake_emit})())
	result = await driver.execute('tabs.list')
	assert result == {'tabs': []}


async def test_driver_with_mock_websocket():
	async def handler(websocket):
		await websocket.send(
			json.dumps(
				{
					'type': 'handshake',
					'protocol_version': '1.0',
					'extension_version': '0.0.1',
					'driver_capabilities': {
						'driver_name': 'mock-extension',
						'driver_version': '0.0.1',
						'features': [DriverFeature.TAB_ORDER_QUERY.value],
						'actions': {
							'tabs.list': {
								'action': 'tabs.list',
								'description': 'List tabs via websocket'
							}
						}
					}
				}
			)
		)
		async for raw in websocket:
			message = json.loads(raw)
			if message.get('type') == 'command':
				await websocket.send(
					json.dumps(
						{
							'type': 'response',
							'request_id': message['request_id'],
							'action': message['action'],
							'status': 'ok',
							'result': {'echo': message.get('payload', {})}
						}
					)
				)

	async with serve(handler, '127.0.0.1', 0) as server:
		sockets = list(server.sockets or [])
		assert sockets, 'websocket server failed to bind any sockets'
		port = sockets[0].getsockname()[1]
		session = StubSession()
		driver = SocketBridgeDriver(endpoint=f'ws://127.0.0.1:{port}/bridge', browser_session=session)
		await driver.start()
		result = await driver.execute('tabs.list', {'sample': True})
		assert result == {'echo': {'sample': True}}
		await driver.stop()
