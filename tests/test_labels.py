from frigate_protect_events.labels import map_label, smart_detect_types


class TestMapLabel:
    def test_person(self):
        assert map_label("person") == "person"

    def test_car(self):
        assert map_label("car") == "vehicle"

    def test_motorcycle(self):
        assert map_label("motorcycle") == "vehicle"

    def test_bus(self):
        assert map_label("bus") == "vehicle"

    def test_truck(self):
        assert map_label("truck") == "vehicle"

    def test_dog(self):
        assert map_label("dog") == "animal"

    def test_cat(self):
        assert map_label("cat") == "animal"

    def test_bird(self):
        assert map_label("bird") == "animal"

    def test_package(self):
        assert map_label("package") == "package"

    def test_unknown_returns_none(self):
        assert map_label("bicycle") is None

    def test_empty_returns_none(self):
        assert map_label("") is None


class TestSmartDetectTypes:
    def test_person_returns_list(self):
        assert smart_detect_types("person") == ["person"]

    def test_car_returns_vehicle_list(self):
        assert smart_detect_types("car") == ["vehicle"]

    def test_unknown_returns_empty(self):
        assert smart_detect_types("bicycle") == []
