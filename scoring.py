"""YOLO pose inference and hit/miss scoring for shooting targets.

The model predicts a target class and a small set of stable registration
keypoints.  Those points register the camera target to its reference image.
The (potentially much denser) scoring-area polygon lives only in
``TARGET_TEMPLATES`` and is never predicted by YOLO.

All template coordinates are normalized to [0, 1].  Fill ``model_keypoints``
and ``area_keypoints`` when the real annotation data is available.
"""

from __future__ import annotations

import types

import cv2
import numpy as np

import config as cf


NUM_CLASSES = 4
CLASS_NAMES = {
    0: "Bia so 10",
    1: "Bia so 6",
    2: "Bia so 7B",
    3: "Bia so 8 phai",
}
SIGN_FILES = {
    0: "biaso10_X7.png",
    1: "biaso6_X7.png",
    2: "biaso7b_X7.png",
    3: "biaso8_phai_X7.png",
}

CONFIDENCE_THRESHOLD = cf.config_float(
    "scoring.confidence_threshold", 0.3, minimum=0.0, maximum=1.0
)
IOU_THRESHOLD = cf.config_float(
    "scoring.iou_threshold", 0.4, minimum=0.0, maximum=1.0
)
KEYPOINT_CONFIDENCE_THRESHOLD = cf.config_float(
    "scoring.keypoint_confidence_threshold", 0.25, minimum=0.0, maximum=1.0
)
RANSAC_REPROJECTION_RATIO = cf.config_float(
    "scoring.ransac_reprojection_ratio", 0.015, minimum=0.0001, maximum=0.25
)
RANSAC_MAX_ITERATIONS = cf.config_int(
    "scoring.ransac_max_iterations", 3000, minimum=100, maximum=100000
)
DEFAULT_TARGET_OFFSETS = {
    0: (0.0, -0.06),
    1: (0.0, 0.0),
    2: (0.0, -0.10),
    3: (-0.40, 0.0),
}


def _configured_target_offsets():
    configured = cf.get_setting("scoring.target_offsets_by_class", {})
    offsets = {}
    for class_id, default in DEFAULT_TARGET_OFFSETS.items():
        value = configured.get(str(class_id), default) if isinstance(configured, dict) else default
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            value = default
        try:
            x_offset, y_offset = float(value[0]), float(value[1])
        except (TypeError, ValueError):
            x_offset, y_offset = default
        if not np.isfinite(x_offset) or not np.isfinite(y_offset):
            x_offset, y_offset = default
        offsets[class_id] = (x_offset, y_offset)
    return offsets


TARGET_OFFSETS = _configured_target_offsets()

# Keep the rotation-aware implementation available for later field testing.
# While disabled, offsets stay aligned with the reference image axes.
TARGET_OFFSET_ROTATION_ENABLED = False

Q0_TARGET_CLASS_ID = cf.config_int(
    "calibration.target_class_id", 1, minimum=0, maximum=NUM_CLASSES - 1
)
_configured_q0_center = cf.get_setting(
    "calibration.reference_center", [0.48607595, 0.44050633]
)
try:
    Q0_REFERENCE_CENTER = (
        max(0.0, min(1.0, float(_configured_q0_center[0]))),
        max(0.0, min(1.0, float(_configured_q0_center[1]))),
    )
except (TypeError, ValueError, IndexError):
    Q0_REFERENCE_CENTER = (0.48607595, 0.44050633)

# TODO: Replace the empty lists with the real normalized coordinates.
# The point order in model_keypoints must exactly match the YOLO pose labels.
# area_keypoints is an ordered polygon describing the complete valid hit area.
TARGET_TEMPLATES = {
    class_id: {
        "name": CLASS_NAMES[class_id],
        "file": SIGN_FILES[class_id],
        "model_keypoints": [],  # [(x_norm, y_norm), ...], about 8-10 points
        "area_keypoints": [],   # [(x_norm, y_norm), ...], any polygon size
    }
    for class_id in range(NUM_CLASSES)
}

TARGET_TEMPLATES[1]["model_keypoints"] = [
    (0.40077071, 0.05009634),
    (0.73410405, 0.30828516),
    (0.96917148, 0.47976879),
    (0.89788054, 0.95953757),
    (0.49325626, 0.96531792),
    (0.02119461, 0.97109827),
    (0.02119461, 0.33333333),
    (0.28131021, 0.24084778)

]
TARGET_TEMPLATES[1]["area_keypoints"] = [
    (0.00192678, 0.29287091),
    (0.23314066, 0.26396917),
    (0.31984586, 0.00192678),
    (0.68786127, 0.00192678),
    (0.78998073, 0.30250482),
    (0.99614644, 0.35838150),
    (0.99421965, 0.99229287),
    (0.00385356, 0.99421965)
]

TARGET_TEMPLATES[2]["model_keypoints"] = [
    (0.45663647, 0.01926782),
    (0.74576308, 0.16570328),
    (0.93851416, 0.29865125),
    (0.75953102, 0.68786127),
    (0.51629752, 0.96724470),
    (0.14456331, 0.98265896),
    (0.05736639, 0.17341040),
    (0.31436782, 0.11175337),

]
TARGET_TEMPLATES[2]["area_keypoints"] = [
    (0.00301500, 0.16708861),
    (0.23215525, 0.12658228),
    (0.26230528, 0.04810127),
    (0.32260535, 0.00000000),
    (0.67234572, 0.00000000),
    (0.77485583, 0.06075949),
    (0.78088584, 0.18227848),
    (0.99796607, 0.23291139),
    (0.98440727, 0.99036609),
    (0.00301500, 0.99746835)
]


class OpenCVDnnSession:
    """Minimal ONNX Runtime-compatible adapter backed by OpenCV DNN."""

    def __init__(self, model_path):
        self.net = cv2.dnn.readNetFromONNX(model_path)
        self.input = types.SimpleNamespace(name="images")

    def get_inputs(self):
        return [self.input]

    def run(self, _output_names, feed_dict):
        self.net.setInput(next(iter(feed_dict.values())))
        return [self.net.forward()]


def create_session(model_path, intra_op_threads=1):
    """Create a CPU session, falling back to OpenCV if ORT is unavailable."""
    try:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = intra_op_threads
        options.inter_op_num_threads = 1
        return ort.InferenceSession(
            model_path,
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except (ImportError, OSError) as exc:
        print(f"[Scoring] ONNX Runtime khong dung duoc, fallback OpenCV DNN: {exc}")
        return OpenCVDnnSession(model_path)

TARGET_TEMPLATES[3]["model_keypoints"] = [
    (0.41033224, 0.10211946),
    (0.68196063, 0.00963391),
    (0.66462265, 0.19845857),
    (0.79754718, 0.41618497),
    (0.91313372, 0.73410405),
    (0.70507794, 0.87668593),
    (0.34675964, 0.66666667),
    (0.08091058, 0.41040462),
    (0.38721493, 0.14836224),
    (0.52591879, 0.86897881),

]
TARGET_TEMPLATES[3]["area_keypoints"] = [
    (0.32942166, 0.15028902),
    (0.27740771, 0.07321773),
    (0.34098031, 0.02312139),
    (0.42767022, 0.00000000),
    (0.71663659, 0.00385356),
    (0.82066449, 0.05009634),
    (0.82066449, 0.13102119),
    (0.71085727, 0.16570328),
    (0.69929861, 0.20038536),
    (0.89001641, 0.33140655),
    (0.73397457, 0.52601156),
    (0.99404431, 0.70520231),
    (0.68773996, 0.89595376),
    (0.74553323, 0.99807322),
    (0.32942166, 0.85356455),
    (0.38721493, 0.71868979),
    (0.08091058, 0.55298651),
    (0.15026251, 0.46242775),
    (0.00000000, 0.36801541),
    (0.16760049, 0.20809249),
]

TARGET_TEMPLATES[0]["model_keypoints"] = [
    (0.01600000, 0.72218182),
    (0.17600000, 0.53890909),
    (0.38080000, 0.49963636),
    (0.57600000, 0.25527273),
    (0.67040000, 0.03054545),
    (0.78400000, 0.04363636),
    (0.97600000, 0.48654545),
    (0.96320000, 0.88581818),
    (0.36480000, 0.98836364),
]
TARGET_TEMPLATES[0]["area_keypoints"] = [
    (0.00000000, 0.59563636),
    (0.11040000, 0.55418182),
    (0.12480000, 0.41672727),
    (0.16480000, 0.35127273),
    (0.36480000, 0.34909091),
    (0.44000000, 0.55200000),
    (0.52320000, 0.50836364),
    (0.56480000, 0.20072727),
    (0.62720000, 0.00000000),
    (0.82880000, 0.00436364),
    (0.88640000, 0.31418182),
    (0.99840000, 0.36218182),
    (0.99520000, 0.99272727),
    (0.00320000, 0.99054545),
]



def letterbox(image, new_shape=(640, 640), color=(0, 0, 0)):
    height, width = image.shape[:2]
    ratio = min(new_shape[0] / height, new_shape[1] / width)
    resized = (int(round(width * ratio)), int(round(height * ratio)))
    pad_w = (new_shape[1] - resized[0]) / 2
    pad_h = (new_shape[0] - resized[1]) / 2
    if (width, height) != resized:
        image = cv2.resize(image, resized, interpolation=cv2.INTER_LINEAR)
    top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
    left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))
    image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)
    return image, ratio, pad_w, pad_h


def preprocess(image, input_size=(640, 640)):
    boxed, ratio, pad_w, pad_h = letterbox(image, input_size)
    tensor = cv2.cvtColor(boxed, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    tensor = np.expand_dims(np.transpose(tensor, (2, 0, 1)), axis=0)
    return tensor, ratio, pad_w, pad_h, image.shape[:2]


def _scale_box(box, ratio, pad_w, pad_h, original_shape):
    height, width = original_shape
    x1, y1, x2, y2 = box
    return [
        int(round(np.clip((x1 - pad_w) / ratio, 0, width - 1))),
        int(round(np.clip((y1 - pad_h) / ratio, 0, height - 1))),
        int(round(np.clip((x2 - pad_w) / ratio, 0, width - 1))),
        int(round(np.clip((y2 - pad_h) / ratio, 0, height - 1))),
    ]


def _scale_keypoints(values, ratio, pad_w, pad_h):
    count = len(values) // 3
    return [
        (
            int(round((values[index * 3] - pad_w) / ratio)),
            int(round((values[index * 3 + 1] - pad_h) / ratio)),
            float(values[index * 3 + 2]),
        )
        for index in range(count)
    ]


def _nms(boxes, scores, iou_threshold):
    if not boxes:
        return []
    xywh = [[x1, y1, max(0, x2 - x1), max(0, y2 - y1)] for x1, y1, x2, y2 in boxes]
    indices = cv2.dnn.NMSBoxes(xywh, scores, 0.0, iou_threshold)
    return [int(item[0] if isinstance(item, (list, tuple, np.ndarray)) else item) for item in indices]


def _as_prediction_rows(output):
    predictions = np.asarray(output[0] if isinstance(output, (list, tuple)) else output)
    if predictions.ndim == 3:
        predictions = predictions[0]
    if predictions.ndim != 2:
        raise ValueError(f"YOLO output khong ho tro: shape={predictions.shape}")
    def valid_feature_width(value):
        return (
            (value >= 6 and (value - 6) % 3 == 0)
            or (value >= 8 and (value - 4 - NUM_CLASSES) % 3 == 0)
        )

    row_width_valid = valid_feature_width(predictions.shape[1])
    column_width_valid = valid_feature_width(predictions.shape[0])
    # Raw Ultralytics output is normally [channels, candidates].  Checking the
    # pose-width formula also keeps this correct for tiny synthetic/test output.
    if column_width_valid and not row_width_valid:
        predictions = predictions.T
    elif column_width_valid and row_width_valid and predictions.shape[0] < predictions.shape[1]:
        predictions = predictions.T
    return predictions


def postprocess(
    output,
    ratio,
    pad_w,
    pad_h,
    original_shape,
    conf_threshold=CONFIDENCE_THRESHOLD,
    iou_threshold=IOU_THRESHOLD,
):
    rows = _as_prediction_rows(output)
    width = rows.shape[1]
    is_end_to_end = width >= 6 and (width - 6) % 3 == 0
    is_raw = width >= 8 + 3 and (width - 4 - NUM_CLASSES) % 3 == 0
    if not is_end_to_end and not is_raw:
        raise ValueError(
            f"Khong suy ra duoc output pose (4 classes) tu shape={rows.shape}. "
            "Can kiem tra cach export model ONNX."
        )

    boxes, scores, class_ids, keypoints = [], [], [], []
    for row in rows:
        if is_end_to_end:
            confidence = float(row[4])
            class_id = int(round(float(row[5])))
            box = row[:4]
            kp_values = row[6:]
        else:
            class_scores = row[4:4 + NUM_CLASSES]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])
            x, y, w, h = row[:4]
            box = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            kp_values = row[4 + NUM_CLASSES:]
        if confidence < conf_threshold or class_id not in TARGET_TEMPLATES:
            continue
        boxes.append(_scale_box(box, ratio, pad_w, pad_h, original_shape))
        scores.append(confidence)
        class_ids.append(class_id)
        keypoints.append(_scale_keypoints(kp_values, ratio, pad_w, pad_h))

    return [
        {"bbox": boxes[i], "conf": scores[i], "class_id": class_ids[i], "keypoints": keypoints[i]}
        for i in _nms(boxes, scores, iou_threshold)
    ]


def inference(
    session,
    image,
    conf_thres=CONFIDENCE_THRESHOLD,
    iou_thres=IOU_THRESHOLD,
):
    tensor, ratio, pad_w, pad_h, shape = preprocess(image)
    input_name = session.get_inputs()[0].name
    output = session.run(None, {input_name: tensor})
    return postprocess(output, ratio, pad_w, pad_h, shape, conf_thres, iou_thres)


def bbox_signed_distance(bbox, point):
    x1, y1, x2, y2 = bbox
    x, y = point
    if x1 <= x <= x2 and y1 <= y <= y2:
        return float(min(x - x1, x2 - x, y - y1, y2 - y))
    return -float(np.hypot(max(x1 - x, 0, x - x2), max(y1 - y, 0, y - y2)))


def _bbox_selection_score(detection, bullet_point):
    """Return a size-normalized score for how well a box owns the shot point."""
    x1, y1, x2, y2 = detection["bbox"]
    width = max(1.0, float(x2 - x1))
    height = max(1.0, float(y2 - y1))
    signed_distance = bbox_signed_distance(detection["bbox"], bullet_point)
    inside = signed_distance >= 0
    if inside:
        proximity = signed_distance / min(width, height)
    else:
        proximity = signed_distance / float(np.hypot(width, height))
    area = width * height
    return int(inside), proximity, -area, float(detection.get("conf", 0.0))


def _mapped_selection_rank(detection, bullet_point, reference_images):
    """Prefer a detection whose affine projection places the shot on its template."""
    if not reference_images:
        return 0
    class_id = detection.get("class_id")
    reference = reference_images.get(class_id)
    if reference is None:
        return 0
    matrix, _matched = estimate_target_transform(detection, reference.shape)
    mapped = transform_point(matrix, bullet_point)
    if mapped is None:
        return 0
    height, width = reference.shape[:2]
    if not (0 <= mapped[0] < width and 0 <= mapped[1] < height):
        return 0
    hit = point_in_hit_area(class_id, reference.shape, mapped)
    return 2 if hit is True else 1


def select_target_result(results, bullet_point, reference_images=None):
    """Select the target that most plausibly owns the shot point.

    Absolute pixel depth biases the old implementation toward physically
    larger, overlapping boxes. Scores are now normalized by box size, and
    affine projection onto the corresponding reference target is used to
    disambiguate boxes that both contain the shot.
    """
    if not results:
        return None

    def selection_score(detection):
        inside, proximity, negative_area, confidence = _bbox_selection_score(
            detection, bullet_point
        )
        mapped_rank = _mapped_selection_rank(
            detection, bullet_point, reference_images
        )
        return inside, mapped_rank, proximity, negative_area, confidence

    return max(results, key=selection_score)


def estimate_target_transform(
    detection,
    reference_shape,
    keypoint_threshold=KEYPOINT_CONFIDENCE_THRESHOLD,
):
    """Return a full affine transform from camera to reference-image pixels.

    A partial affine transform forces equal X/Y scale and cannot represent
    shear.  That is noticeably inaccurate for the tall targets when the
    camera observes them at an angle, so use all six affine parameters here.
    """
    template = TARGET_TEMPLATES[detection["class_id"]]
    reference_points = template["model_keypoints"]
    predicted_points = detection["keypoints"]
    count = min(len(reference_points), len(predicted_points))
    height, width = reference_shape[:2]
    source, destination = [], []
    for index in range(count):
        x, y, confidence = predicted_points[index]
        if confidence >= keypoint_threshold:
            source.append((x, y))
            rx, ry = reference_points[index]
            destination.append((rx * width, ry * height))
    if len(source) < 3:
        return None, len(source)
    # Express the RANSAC tolerance relative to the reference resolution.  A
    # fixed 3 px threshold is unrealistically strict for 3K-5K target images.
    reprojection_threshold = max(
        3.0, max(height, width) * RANSAC_REPROJECTION_RATIO
    )
    matrix, inliers = cv2.estimateAffine2D(
        np.asarray(source, np.float32),
        np.asarray(destination, np.float32),
        method=cv2.RANSAC,
        ransacReprojThreshold=reprojection_threshold,
        maxIters=RANSAC_MAX_ITERATIONS,
        confidence=0.99,
        refineIters=20,
    )
    inlier_count = int(np.count_nonzero(inliers)) if inliers is not None else 0
    if matrix is None or inlier_count < 3:
        return None, inlier_count
    return matrix, inlier_count


def transform_point(matrix, point):
    if matrix is None:
        return None
    transformed = matrix @ np.asarray([point[0], point[1], 1.0], np.float32)
    return float(transformed[0]), float(transformed[1])


def affine_rotation_matrix(matrix):
    """Extract the closest proper rotation from a camera-to-reference affine."""
    if matrix is None:
        return np.eye(2, dtype=np.float64)
    linear = np.asarray(matrix, dtype=np.float64)[:2, :2]
    if linear.shape != (2, 2) or not np.all(np.isfinite(linear)):
        return np.eye(2, dtype=np.float64)
    try:
        left, _scale, right = np.linalg.svd(linear)
    except np.linalg.LinAlgError:
        return np.eye(2, dtype=np.float64)
    rotation = left @ right
    if np.linalg.det(rotation) < 0:
        left[:, -1] *= -1
        rotation = left @ right
    return rotation


def apply_target_offset(class_id, reference_shape, reference_point, matrix=None):
    """Apply the configured offset in reference-image pixels."""
    if reference_point is None:
        return None
    height, width = reference_shape[:2]
    x_offset, y_offset = TARGET_OFFSETS.get(class_id, (0.0, 0.0))
    raw_offset = np.asarray(
        [x_offset * width, y_offset * height], dtype=np.float64
    )
    if not TARGET_OFFSET_ROTATION_ENABLED:
        offset = raw_offset
        return (
            float(reference_point[0]) + float(offset[0]),
            float(reference_point[1]) + float(offset[1]),
        )

    rotation = affine_rotation_matrix(matrix)
    if class_id == 3:
        # Only Bia 8's horizontal offset uses the mirrored angle (theta -> -theta).
        # Its vertical offset keeps the same rotation as every other target.
        horizontal_offset = rotation.T @ np.asarray(
            [x_offset * width, 0.0], dtype=np.float64
        )
        vertical_offset = rotation @ np.asarray(
            [0.0, y_offset * height], dtype=np.float64
        )
        offset = horizontal_offset + vertical_offset
    else:
        offset = rotation @ raw_offset
    return (
        float(reference_point[0]) + float(offset[0]),
        float(reference_point[1]) + float(offset[1]),
    )


def calculate_q0(
    image,
    reference_image,
    session,
    conf_thres=CONFIDENCE_THRESHOLD,
    iou_thres=IOU_THRESHOLD,
):
    """Project the class-1 reference center back onto a camera image."""
    results = inference(session, image, conf_thres, iou_thres)
    candidates = [
        result
        for result in results
        if result["class_id"] == Q0_TARGET_CLASS_ID
    ]
    if not candidates:
        return {
            "ok": False,
            "status": f"Khong phat hien bia class {Q0_TARGET_CLASS_ID}",
        }
    detection = max(candidates, key=lambda result: result["conf"])
    matrix, matched = estimate_target_transform(detection, reference_image.shape)
    if matrix is None:
        return {
            "ok": False,
            "status": "Khong du keypoint class 1 de tinh affine",
            "matched_keypoints": matched,
        }

    ref_h, ref_w = reference_image.shape[:2]
    reference_center = (
        Q0_REFERENCE_CENTER[0] * ref_w,
        Q0_REFERENCE_CENTER[1] * ref_h,
    )
    camera_matrix = cv2.invertAffineTransform(matrix)
    camera_point = transform_point(camera_matrix, reference_center)
    image_h, image_w = image.shape[:2]
    normalized = (camera_point[0] / image_w, camera_point[1] / image_h)
    x1, y1, x2, y2 = detection["bbox"]
    return {
        "ok": True,
        "status": "Da xac dinh Q0",
        "q0": normalized,
        "camera_point": camera_point,
        "matched_keypoints": matched,
        "target_size": int(round(max(x2 - x1, y2 - y1))),
        "detection": detection,
    }


def point_in_hit_area(class_id, reference_shape, reference_point):
    area = TARGET_TEMPLATES[class_id]["area_keypoints"]
    if reference_point is None or len(area) < 3:
        return None
    height, width = reference_shape[:2]
    polygon = np.asarray([(x * width, y * height) for x, y in area], np.float32)
    return cv2.pointPolygonTest(polygon, reference_point, False) >= 0


def scoring(
    image,
    bullet_point,
    reference_images,
    session,
    conf_thres=CONFIDENCE_THRESHOLD,
    iou_thres=IOU_THRESHOLD,
):
    """Determine the target and hit state for a normalized shot coordinate."""
    height, width = image.shape[:2]
    shot = (int(round(bullet_point[0] * width)), int(round(bullet_point[1] * height)))
    detections = inference(session, image, conf_thres, iou_thres)
    selected = select_target_result(detections, shot, reference_images)
    metadata = {
        "class_id": None,
        "target_name": None,
        "hit": None,
        "status": "Khong phat hien bia",
        "transformed_point": None,
        "transformed_click_point": None,
        "target_offset": (0.0, 0.0),
        "matched_keypoints": 0,
        "detections": detections,
        "selected_detection": selected,
    }
    if selected is None:
        return image, metadata

    class_id = selected["class_id"]
    metadata.update(class_id=class_id, target_name=CLASS_NAMES[class_id])
    reference = reference_images.get(class_id)
    if reference is None:
        metadata["status"] = "Chua co anh bia mau"
        return image, metadata
    if not TARGET_TEMPLATES[class_id]["model_keypoints"]:
        metadata["status"] = "Chua co model_keypoints"
        return image, metadata

    matrix, matched = estimate_target_transform(selected, reference.shape)
    mapped_click = transform_point(matrix, shot)
    mapped = apply_target_offset(class_id, reference.shape, mapped_click, matrix)
    hit = point_in_hit_area(class_id, reference.shape, mapped)
    metadata.update(
        transformed_point=mapped,
        transformed_click_point=mapped_click,
        target_offset=TARGET_OFFSETS.get(class_id, (0.0, 0.0)),
        matched_keypoints=matched,
        hit=hit,
    )
    if matrix is None:
        metadata["status"] = "Khong du keypoint tin cay de tinh affine"
    elif hit is None:
        metadata["status"] = "Chua co area_keypoints"
    else:
        metadata["status"] = "TRUNG BIA" if hit else "TRUOT BIA"
    return image, metadata
