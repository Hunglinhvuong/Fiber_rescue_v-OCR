from enum import IntEnum, auto


class IncidentState(IntEnum):
    SELECT_ROUTE = auto()
    SEARCH_ROUTE = auto()
    SELECT_INCIDENT_TYPE = auto()
    SELECT_CAUSE = auto()
    SELECT_SPAN = auto()
    SELECT_MATERIALS = auto()
    ADD_MATERIAL_QTY = auto()
    ENTER_DESCRIPTION = auto()
    SEND_LOCATION = auto()
    SEND_PHOTO_BEFORE = auto()
    SEND_PHOTO_AFTER = auto()
    CONFIRM = auto()
    EDIT_MENU = auto()
