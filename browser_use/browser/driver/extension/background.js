const WS_ENDPOINT = 'ws://localhost:8321/bridge';
const RETRY_DELAY_MS = 2_000;

let socket;
let reconnectTimer;

const driverCapabilities = {
	protocol_version: '1.0',
	driver_name: 'chrome-extension-bridge',
	actions: {
		'tabs.list': { description: 'List tabs in the current window' },
		'tabs.activate': { description: 'Activate tab by index' },
		'tabs.open': { description: 'Open URL in new tab' },
		'tabs.close': { description: 'Close tab by index' },
		'screenshots.captureVisibleTab': { description: 'Capture visible tab screenshot' }
	},
	features: ['tab_foreground_detection', 'tab_order_query', 'window_enumeration']
};

function sendJson(payload) {
	if (!socket || socket.readyState !== WebSocket.OPEN) {
		throw new Error('bridge not connected');
	}
	socket.send(JSON.stringify(payload));
}

async function handleCommand(command) {
	const started = performance.now();
	try {
		const handler = ACTION_HANDLERS[command.action];
		if (!handler) {
			throw new Error(`Unsupported action ${command.action}`);
		}
		const result = await handler(command.payload || {});
		sendJson({
			type: 'response',
			request_id: command.request_id,
			action: command.action,
			status: 'ok',
			result,
			duration_ms: Math.round(performance.now() - started)
		});
	} catch (error) {
		sendJson({
			type: 'response',
			request_id: command.request_id,
			action: command.action,
			status: 'error',
			error: error.message,
			duration_ms: Math.round(performance.now() - started)
		});
	}
}

async function listTabs() {
	const tabs = await chrome.tabs.query({});
	return {
		tabs: tabs.map((tab) => ({
			id: tab.id,
			index: tab.index,
			window_id: tab.windowId,
			url: tab.url,
			title: tab.title,
			active: tab.active
		}))
	};
}

async function activateTab(payload) {
	if (typeof payload.index !== 'number') {
		throw new Error('payload.index must be number');
	}
	const tabs = await chrome.tabs.query({ currentWindow: true });
	const tab = tabs.find((t) => t.index === payload.index);
	if (!tab || tab.id === undefined) {
		throw new Error(`Tab index ${payload.index} not found`);
	}
	await chrome.tabs.update(tab.id, { active: true });
	return { result: 'ok' };
}

async function openTab(payload) {
	const createOptions = {};
	if (payload.url) {
		createOptions.url = payload.url;
	}
	const tab = await chrome.tabs.create(createOptions);
	return { result: 'ok', tab_id: tab.id, url: tab.url };
}

async function closeTab(payload) {
	if (typeof payload.index !== 'number') {
		throw new Error('payload.index must be number');
	}
	const tabs = await chrome.tabs.query({ currentWindow: true });
	const tab = tabs.find((t) => t.index === payload.index);
	if (!tab || tab.id === undefined) {
		throw new Error(`Tab index ${payload.index} not found`);
	}
	await chrome.tabs.remove(tab.id);
	return { result: 'ok' };
}

async function captureVisibleTab() {
	const dataUrl = await chrome.tabs.captureVisibleTab();
	return { data_url: dataUrl };
}

const ACTION_HANDLERS = {
	'tabs.list': listTabs,
	'tabs.activate': activateTab,
	'tabs.open': openTab,
	'tabs.close': closeTab,
	'screenshots.captureVisibleTab': captureVisibleTab
};

function publishEvent(channel, payload) {
	try {
		sendJson({ type: 'event', channel, payload });
	} catch (error) {
		console.warn('Failed to publish event', error);
	}
}

function registerTabListeners() {
	chrome.tabs.onActivated.addListener((activeInfo) => {
		publishEvent('tabs.activated', activeInfo);
	});
	chrome.tabs.onCreated.addListener((tab) => {
		publishEvent('tabs.created', {
			id: tab.id,
			url: tab.url,
			index: tab.index,
			window_id: tab.windowId
		});
	});
	chrome.tabs.onRemoved.addListener((tabId, removeInfo) => {
		publishEvent('tabs.removed', { tab_id: tabId, window_id: removeInfo.windowId });
	});
}

function sendHandshake() {
	const manifest = chrome.runtime.getManifest();
	sendJson({
		type: 'handshake',
		protocol_version: '1.0',
		extension_version: manifest.version,
		driver_capabilities: driverCapabilities
	});
}

function scheduleReconnect() {
	if (reconnectTimer) {
		return;
	}
	reconnectTimer = setTimeout(() => {
		reconnectTimer = undefined;
		connect();
	}, RETRY_DELAY_MS);
}

function connect() {
	if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
		return;
	}
	try {
		socket = new WebSocket(WS_ENDPOINT);
		socket.addEventListener('open', sendHandshake);
		socket.addEventListener('message', (event) => {
			try {
				const message = JSON.parse(event.data);
				if (message.type === 'command') {
					handleCommand(message);
				}
			} catch (error) {
				console.error('Failed to process command', error);
			}
		});
		socket.addEventListener('close', scheduleReconnect);
		socket.addEventListener('error', scheduleReconnect);
	} catch (error) {
		scheduleReconnect();
	}
}

registerTabListeners();
connect();
