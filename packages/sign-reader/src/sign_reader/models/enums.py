from enum import Enum


class Activity(str, Enum):
    """The activity that is forbidden or permitted by this regulation"""

    # COMMENTED ACTIVITIES ARE WELL-KNOWN CDS VALUES
    # BUT NOT CURRENTLY USED IN BOSTON IMPLMENTATION
    parking = "parking"
    no_parking = "no parking"
    loading = "loading"
    no_loading = "no loading"
    # unloading = "unloading"
    # no_unloading = "no unloading"
    stopping = "stopping"
    no_stopping = "no stopping"
    # travel = "travel"
    # no_travel = "no travel"

    unusable_image = "unusable image"


class UserClass(str, Enum):
    """A user class represents any class of vehicles that is regulated by a city.
    They can be defined by:
      - the vehicle's physical characteristics (e.g., trucks, vans, EVs),
      - the presence/absence of a particular permit (e.g., residential parking permits),
      - the intent or destination of the driver, for things like hotel or
        school unloading zones.
    """

    # COMMENTED USER CLASSES ARE WELL-KNOWN CDS VALUES
    # BUT NOT CURRENTLY USED IN BOSTON IMPLMENTATION

    # Vehicle types
    bicycle = "bicycle"
    bus = "bus"
    # cargo_bicycle = "cargo_bicycle"
    car = "car"
    # moped = "moped"
    motorcycle = "motorcycle"
    # scooter = "scooter"
    truck = "truck"
    # van = "van"

    # Vehicle properties
    accessible = "accessible"
    # autonomous = "autonomous"
    # combustion = "combustion"
    electric = "electric"
    # electric_assist = "electric_assist"
    # human = "human"

    # THE FOLLOWING USER CLASSES ARE NOT WELL-KNOWN CDS VALUES
    # BUT ARE USEFUL FOR BOSTON IMPLEMENTATION
    commercial_vehicle = "commercial_vehicle"
    resident_permit = "resident_permit"
    rideshare = "rideshare"
    valet = "valet"


class Purposes(str, Enum):
    "A purpose represents the kinds of activities taking place."

    # COMMENTED PURPOSES ARE WELL-KNOWN CDS VALUES
    # BUT NOT CURRENTLY USED IN BOSTON IMPLMENTATION

    # construction = "construction"
    # delivery = "delivery"
    # disabled_parking_permit = "disabled_parking_permit"
    emergency_use = "emergency_use"
    # freight = "freight"
    # parking = "parking"
    # permit = "permit"
    # rideshare = "rideshare"
    # school = "school"
    # service_vehicles = "service_vehicles"
    # special_events = "special_events"
    # taxi = "taxi"
    # utilities = "utilities"
    # vending = "vending"
    # waste_management = "waste_management"

    # THE FOLLOWING PURPOSES ARE NOT WELL-KNOWN CDS VALUES
    # BUT ARE USEFUL FOR BOSTON IMPLEMENTATION
    pickup_dropoff = "pickup_dropoff"
