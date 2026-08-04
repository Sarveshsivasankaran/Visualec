from app.services.tracking_service import TrackingService, iou


def test_iou_tracker_reuses_id_and_expires_tracks():
    tracker = TrackingService(max_age_seconds=1, match_iou=.2)
    first = tracker.update([{"bbox": [0, 0, 100, 100]}], now=1)[0]["tracking_id"]
    second = tracker.update([{"bbox": [5, 5, 105, 105]}], now=1.5)[0]["tracking_id"]
    third = tracker.update([{"bbox": [5, 5, 105, 105]}], now=3)[0]["tracking_id"]
    assert iou([0, 0, 10, 10], [5, 5, 15, 15]) > 0
    assert first == second
    assert third != first
