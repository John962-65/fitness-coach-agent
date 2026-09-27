"""姿态估计封装（设计书 15.3 线 B 第 1 步 / 15.6）

MediaPipe 本地推理（CPU、离线，视频不离开本机）。
输入视频文件 → 输出逐帧 33 关键点（归一化坐标 + visibility），
交给 vision_rules.py 的确定性规则引擎判断；LLM 只负责把故障码翻译成人话。

CLI（MVP：用户拍视频 → 本命令分析 → 故障码 + 建议话术）：
  python3 -m coach.vision <video.mp4> --exercise squat --view side
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "models" / "pose_landmarker_lite.task"


def _detect_legacy(video_path: str, sample_every: int) -> list[list[dict]]:
    """mediapipe <1.0 的 solutions API"""
    import cv2
    import mediapipe as mp

    pose = mp.solutions.pose.Pose(
        static_image_mode=False, model_complexity=1,
        enable_segmentation=False, min_detection_confidence=0.5)
    frames: list[list[dict]] = []
    cap = cv2.VideoCapture(video_path)
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % sample_every == 0:
            res = pose.process(frame)
            if res.pose_landmarks:
                frames.append([
                    {"x": lm.x, "y": lm.y, "visibility": lm.visibility}
                    for lm in res.pose_landmarks.landmark
                ])
        i += 1
    cap.release()
    return frames


def _detect_tasks(video_path: str, sample_every: int) -> list[list[dict]]:
    """mediapipe >=1.0 的 Tasks API（PoseLandmarker，需本地模型文件）"""
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    if not MODEL_PATH.exists():
        raise RuntimeError(
            f"缺少姿态模型文件 {MODEL_PATH}。下载："
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/1/pose_landmarker_lite.task")
    opts = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.VIDEO, num_poses=1,
        min_pose_detection_confidence=0.5)
    detector = vision.PoseLandmarker.create_from_options(opts)
    frames: list[list[dict]] = []
    cap = cv2.VideoCapture(video_path)
    i = 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % sample_every == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int(i / fps * 1000) + 1
            res = detector.detect_for_video(image, ts_ms)
            if res.pose_landmarks:
                lm0 = res.pose_landmarks[0]
                frames.append([{"x": lm.x, "y": lm.y,
                                "visibility": getattr(lm, "visibility", 1.0) or 1.0}
                               for lm in lm0])
        i += 1
    cap.release()
    return frames


def extract_keypoints(video_path: str, sample_every: int = 2) -> list[list[dict]]:
    """逐帧（按 sample_every 抽稀）提取 33 关键点。

    返回 [{index: {x, y, visibility}}, ...]；按 mediapipe 版本自动选 API。
    """
    try:
        import cv2
        import mediapipe as mp
    except ImportError as e:
        raise RuntimeError(
            "需要 mediapipe + opencv：pip3 install mediapipe opencv-python-headless"
        ) from e

    if hasattr(mp, "solutions"):
        return _detect_legacy(video_path, sample_every)
    return _detect_tasks(video_path, sample_every)


def analyze_video(video_path: str, exercise: str, view: str = "side") -> dict:
    from .vision_rules import analyze

    frames = extract_keypoints(video_path)
    if not frames:
        return {"exercise": exercise, "frames": 0, "faults": [],
                "note": "没有检测到人体关键点——检查拍摄规范（全身入镜/光线/固定机位）"}
    faults = analyze(exercise, frames, view)
    return {"exercise": exercise, "view": view, "frames": len(frames),
            "faults": faults}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("video")
    ap.add_argument("--exercise", required=True,
                    help="squat / deadlift / romanian_deadlift / bench")
    ap.add_argument("--view", default="side", choices=["side", "front", "back"])
    ap.add_argument("--json", action="store_true", help="只输出 JSON")
    args = ap.parse_args()

    try:
        result = analyze_video(args.video, args.exercise, args.view)
    except RuntimeError as e:
        print(str(e))
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return 0
    print(f"动作：{result['exercise']}（{result.get('view', 'side')}），"
          f"分析 {result['frames']} 帧")
    if not result["faults"]:
        print("未命中故障码：从规则引擎看没有明显问题（不构成医学/技术保证）。")
    for f in result["faults"]:
        print(f"  ⚠️ {f['code']}（{f.get('label', '')}）值={f.get('value')}"
              + (f"——{f['hint']}" if f.get("hint") else ""))
    print("\n（判断来自确定性规则引擎，只作提示；改善后可再拍一次对比。）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
