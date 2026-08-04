from app.services.zone_service import bottom_centre, point_in_polygon


def test_point_in_polygon_inside_outside_and_boundary():
    square = [(0, 0), (1, 0), (1, 1), (0, 1)]
    assert point_in_polygon((0.5, 0.5), square)
    assert point_in_polygon((1, 0.5), square)
    assert not point_in_polygon((1.1, 0.5), square)


def test_bottom_centre_is_normalized_floor_position():
    assert bottom_centre([100, 20, 300, 400], 800, 600) == (0.25, 2 / 3)
