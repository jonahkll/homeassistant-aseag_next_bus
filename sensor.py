"""Representation of ASEAG Next Bus Sensors."""

import json
import logging

import requests
import voluptuous as vol

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import ATTR_ATTRIBUTION, CONF_NAME, DEVICE_CLASS_TIMESTAMP
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util.dt import utc_from_timestamp, utcnow

_LOGGER = logging.getLogger(__name__)

CONF_STOP_ID = "stop_id"
CONF_DIRECTION_ID = "direction_id"

ATTR_STOP = "stop"
ATTR_LINE = "line"
ATTR_DESTINATION = "destination"

DEFAULT_NAME = "ASEAG Next Bus"

ICON = "mdi:bus"
ATTRIBUTION = "Data provided by ASEAG"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_STOP_ID): cv.string,
        vol.Required(CONF_DIRECTION_ID): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform."""

    stop_id = config[CONF_STOP_ID]
    direction_id = config[CONF_DIRECTION_ID]
    name = config.get(CONF_NAME)

    api = AseagApi()
    add_entities([AseagNextBusSensor(api, name, stop_id, direction_id)])


class AseagApi:
    """Representation of the ASEAG API."""

    @staticmethod
    def get_predictions(stop_id, direction_id):
        """Get predictions matching a stop and direction from the ASEAG API."""
        resource = (
            f"http://ivu.aseag.de/interfaces/ura/instant_V2"
            f"?StopId={stop_id}"
            f"&DirectionID={direction_id}"
            f"&ReturnList=stoppointname,linename,destinationtext,tripid,estimatedtime,expiretime"
        )
        try:
            response = requests.get(resource, verify=True, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as ex:
            _LOGGER.error("Error fetching data: %s failed with %s", resource, ex)
            return None


class AseagNextBusSensor(Entity):
    """Representation of a ASEAG Next Bus Sensor."""

    def __init__(self, api, name, stop_id, direction_id):
        """Initialize the ASEAG Next Bus Sensor."""
        self._api = api
        self._name = name
        self._stop_id = stop_id
        self._direction_id = direction_id
        self._predictions = []
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the ASEAG Next Bus Sensor."""
        return f"{self._name} {self._stop_id} {self._direction_id}"

    @property
    def device_class(self):
        """Return the device class of the ASEAG Next Bus Sensor."""
        return DEVICE_CLASS_TIMESTAMP

    @property
    def icon(self):
        """Icon to use in the frontend of the ASEAG Next Bus Sensor."""
        return ICON

    @property
    def state(self):
        """Return the state of the ASEAG Next Bus Sensor."""
        return self._state

    @property
    def device_state_attributes(self):
        """Return the state attributes of the ASEAG Next Bus Sensor."""
        return self._attributes

    def update(self):
        """Fetch new state data for the ASEAG Next Bus Sensor."""
        self._state = None
        self._attributes = {}

        result = self._api.get_predictions(self._stop_id, self._direction_id)
        predictions = []

        if result:
            try:
                for line in result.splitlines():
                    line_list = json.loads(line)
                    if line_list[0] == 1:
                        predictions.append(
                            [
                                line_list[4],  # trip_id
                                utc_from_timestamp(
                                    int(line_list[5] / 1000)
                                ),  # estimated_time
                                utc_from_timestamp(
                                    int(line_list[6] / 1000)
                                ),  # expire_time
                                line_list[1],  # stoppoint_name
                                line_list[2],  # line_name
                                line_list[3],  # destination_text
                            ]
                        )
            except (IndexError, ValueError) as ex:
                _LOGGER.error(
                    "Erroneous result found when expecting list of predictions: %s", ex
                )
        else:
            _LOGGER.error("Empty result found when expecting list of predictions")

        for prediction in self._predictions:
            if not any(prediction[0] in subl for subl in predictions):
                predictions.append(prediction)

        for prediction in predictions:
            if prediction[1] < utcnow() or prediction[2] < utcnow():
                predictions.remove(prediction)

        if predictions:
            self._predictions = sorted(
                predictions, key=lambda prediction: prediction[1]
            )
            self._state = self._predictions[0][1].isoformat()
            self._attributes[ATTR_STOP] = self._predictions[0][3]
            self._attributes[ATTR_LINE] = self._predictions[0][4]
            self._attributes[ATTR_DESTINATION] = self._predictions[0][5]
            self._attributes[ATTR_ATTRIBUTION] = ATTRIBUTION
