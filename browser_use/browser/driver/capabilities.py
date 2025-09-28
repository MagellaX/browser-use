from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DriverFeature(str, Enum):
	"""Enumerates high level browser automation capabilities."""

	TAB_FOREGROUND_DETECTION = 'tab_foreground_detection'
	TAB_ORDER_QUERY = 'tab_order_query'
	TAB_GROUP_MANAGEMENT = 'tab_group_management'
	WINDOW_ENUMERATION = 'window_enumeration'
	WINDOW_FOCUS = 'window_focus'
	SCREENSHOT_WITHOUT_FOCUS = 'screenshot_without_focus'
	PRINT_TO_PDF = 'print_to_pdf'
	CHROME_STORAGE_ACCESS = 'chrome_storage_access'
	OPFS_ACCESS = 'opfs_access'
	SERVICE_WORKER_ACCESS = 'service_worker_access'
	CROSS_ORIGIN_IFRAME_ACCESS = 'cross_origin_iframe_access'
	UI_SURFACE_OVERLAY = 'ui_surface_overlay'


class DriverActionCapability(BaseModel):
	"""Describes how a driver implements a specific high level action."""

	model_config = ConfigDict(extra='forbid', frozen=True, validate_assignment=False, validate_default=True)

	action: str = Field(description='Fully qualified controller action name, e.g. controller.go_to_url')
	description: str | None = Field(default=None, description='Optional human readable description')
	provided_by: str = Field(default='native', description='Driver component providing the action (native, extension, fallback, etc.)')
	is_default_handler: bool = Field(default=True, description='Whether this handler should be preferred when multiple drivers offer it')

	@model_validator(mode='after')
	def _assert_normalized_action(self) -> 'DriverActionCapability':
		assert self.action, 'action name must be provided'
		assert self.action.lower() == self.action, 'action names must be lowercase'
		return self


class BrowserDriverCapabilities(BaseModel):
	"""Capability manifest advertised by a BrowserDriver implementation."""

	model_config = ConfigDict(extra='forbid', validate_assignment=True, frozen=False, arbitrary_types_allowed=True)

	driver_name: str = Field(description='Stable identifier for the driver implementation')
	driver_version: str | None = Field(default=None, description='Optional driver semantic version')
	features: set[DriverFeature] = Field(default_factory=set, description='Feature toggles supported by this driver')
	actions: dict[str, DriverActionCapability] = Field(default_factory=dict, description='Mapping of action name to capability metadata')
	metadata: dict[str, Any] = Field(default_factory=dict, description='Additional JSON-serializable metadata for diagnostics')

	@model_validator(mode='after')
	def _ensure_unique_actions(self) -> 'BrowserDriverCapabilities':
		assert len(self.actions) == len(set(self.actions.keys())), 'duplicate action capability names registered'
		return self

	def supports_action(self, action_name: str) -> bool:
		return action_name in self.actions

	def registered_actions(self) -> set[str]:
		return set(self.actions.keys())

	def require_action(self, action_name: str) -> DriverActionCapability:
		action = self.actions.get(action_name)
		assert action is not None, f"Driver '{self.driver_name}' does not advertise required action '{action_name}'"
		return action

	def add_action(self, capability: DriverActionCapability) -> None:
		assert capability.action not in self.actions, f'action {capability.action} already registered for driver {self.driver_name}'
		self.actions[capability.action] = capability

	def enable_feature(self, feature: DriverFeature) -> None:
		self.features.add(feature)

	def disable_feature(self, feature: DriverFeature) -> None:
		self.features.discard(feature)

	def supports_feature(self, feature: DriverFeature) -> bool:
		return feature in self.features
