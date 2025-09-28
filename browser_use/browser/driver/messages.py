from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from uuid_extensions import uuid7str


class BridgeMessageType(str, Enum):
	COMMAND = 'command'
	RESPONSE = 'response'
	EVENT = 'event'
	HANDSHAKE = 'handshake'


class BridgeCommand(BaseModel):
	"""Command envelope sent from python client to the browser extension."""

	model_config = ConfigDict(extra='forbid', validate_assignment=True, validate_default=True)

	message_type: BridgeMessageType = Field(default=BridgeMessageType.COMMAND, alias='type')
	request_id: str = Field(default_factory=uuid7str, description='Correlates command and response messages')
	action: str = Field(description='Action identifier to execute')
	payload: dict[str, Any] = Field(default_factory=dict, description='JSON-serializable payload')
	timestamp_ms: int = Field(default_factory=lambda: int(time.time() * 1000))

	@field_validator('action')
	def _normalize_action(cls, value: str) -> str:
		assert value, 'action name must be non-empty'
		return value


class BridgeResponseStatus(str, Enum):
	OK = 'ok'
	ERROR = 'error'


class BridgeResponse(BaseModel):
	"""Response envelope delivered from the extension back to python."""

	model_config = ConfigDict(extra='forbid', validate_assignment=True, validate_default=True)

	message_type: BridgeMessageType = Field(default=BridgeMessageType.RESPONSE, alias='type')
	request_id: str = Field(description='Matches the originating command request_id')
	action: str = Field(description='Action identifier that was executed')
	status: BridgeResponseStatus = Field(default=BridgeResponseStatus.OK)
	result: dict[str, Any] | None = Field(default=None, description='Result payload when status == ok')
	error: str | None = Field(default=None, description='Error message when status == error')
	duration_ms: int | None = Field(default=None, description='Execution time reported by the extension')

	@field_validator('error')
	def _ensure_error_has_text(cls, value: str | None, info):
		if info.data.get('status') == BridgeResponseStatus.ERROR:
			assert value, 'error response must include error message'
		return value


class BridgeEvent(BaseModel):
	"""Push events broadcast from the extension."""

	model_config = ConfigDict(extra='forbid', validate_assignment=True, validate_default=True)

	message_type: BridgeMessageType = Field(default=BridgeMessageType.EVENT, alias='type')
	channel: str = Field(description='Event channel name, e.g. tab_state_updated')
	payload: dict[str, Any] = Field(default_factory=dict)
	request_id: str | None = Field(default=None, description='Optional correlation id back to triggering command')


class BridgeHandshake(BaseModel):
	"""Initial handshake metadata exchanged during connection setup."""

	model_config = ConfigDict(extra='forbid', validate_assignment=True, validate_default=True)

	message_type: BridgeMessageType = Field(default=BridgeMessageType.HANDSHAKE, alias='type')
	protocol_version: str = Field(default='1.0')
	extension_version: str | None = Field(default=None)
	driver_capabilities: dict[str, Any] = Field(default_factory=dict)
