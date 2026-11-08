#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slice_image.py — 手机长截图自适应滑窗切片器 (Adaptive Tile Slicing)

【解决痛点】：
手机长截屏（长宽比通常达到 1:8 ~ 1:12）直接上传到大模型聊天窗口或视觉 API 时，
会被前端组件强行等比缩放为 max(w, h) = 1024 像素，导致横向宽度只剩下 ~100 像素，
中文字符被严重压缩至 3x3 像素黑块，诱发严重的偏旁混淆与幻觉拼合（如将融通与财通捏造为财通稳进）。

【核心机制】：
当高宽比 (height / width) > 2.0 时，自适应将其竖向切割为 2~5 张正常视口的分块图，
并保留 15% 垂直冗余重叠带（Overlap），防止基金明细行被恰好切成两半。
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List, Optional

try:
    from PIL import Image
except ImportError:
    Image = None


def slice_long_image(
    image_path: str,
    output_dir: Optional[str] = None,
    max_aspect_ratio: float = 2.0,
    overlap_pct: float = 0.15,
) -> List[str]:
    """
    检查图片长宽比，若超过 max_aspect_ratio 则进行垂直重叠滑窗切片。
    返回切片后的文件绝对路径列表。如果无需切片，则返回包含原图路径的列表。
    """
    if Image is None:
        raise RuntimeError("Pillow (PIL) 未安装，无法执行图片切片处理。")

    p = Path(image_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"待切片图片不存在: {p}")

    with Image.open(p) as img:
        w, h = img.size
        aspect_ratio = h / float(w)

        # 正常长宽比（非超长滚动图），直接返回原图
        if aspect_ratio <= max_aspect_ratio:
            return [str(p)]

        # 确定切片数量：目标让每个切片的长宽比处于 1:1.5 ~ 1:2.0 的正常黄金视口区间
        target_aspect = 1.6
        num_slices = max(2, int(math.ceil(aspect_ratio / target_aspect)))

        if output_dir:
            out_dir = Path(output_dir).resolve()
        else:
            out_dir = p.parent / f"{p.stem}_slices"
        out_dir.mkdir(parents=True, exist_ok=True)

        slice_paths = []
        # 计算有效高度与重叠高度
        # slice_height = (h + (num_slices - 1) * overlap) / num_slices
        # 简化计算：每个窗口的基础高度
        step = h / float(num_slices)
        overlap_px = int(step * overlap_pct)

        for i in range(num_slices):
            top = max(0, int(i * step - overlap_px if i > 0 else 0))
            bottom = min(h, int((i + 1) * step + (overlap_px if i < num_slices - 1 else 0)))

            # 裁剪区域
            box = (0, top, w, bottom)
            slice_img = img.crop(box)

            out_file = out_dir / f"slice_{i + 1:02d}_{p.stem}.jpg"
            # 保持最高质量保存
            slice_img.save(out_file, quality=95)
            slice_paths.append(str(out_file))

        return slice_paths


def main():
    parser = argparse.ArgumentParser(
        description="手机长截图自适应滑窗切片工具 (Adaptive Tile Slicing)"
    )
    parser.add_argument(
        "-i", "--input", required=True, help="待切片的手机长截图文件路径"
    )
    parser.add_argument(
        "-o", "--output-dir", default=None, help="切片图片输出目录（默认生成在图片同级 _slices/ 文件夹）"
    )
    parser.add_argument(
        "--max-aspect", type=float, default=2.0, help="触发切片的长宽比阈值 (默认: 2.0)"
    )
    parser.add_argument(
        "--overlap", type=float, default=0.15, help="切片之间的重叠高度比例 (默认: 0.15 即 15%%)"
    )
    parser.add_argument(
        "--json", action="store_true", help="以 JSON 格式向 stdout 输出切片结果路径"
    )

    args = parser.parse_args()

    try:
        slices = slice_long_image(
            image_path=args.input,
            output_dir=args.output_dir,
            max_aspect_ratio=args.max_aspect,
            overlap_pct=args.overlap,
        )

        if args.json:
            print(json.dumps({"input": args.input, "is_sliced": len(slices) > 1, "slices": slices}, ensure_ascii=False, indent=2))
        else:
            if len(slices) == 1:
                print(f"ℹ️ 图片长宽比正常，无需切片: {slices[0]}")
            else:
                print(f"✅ 长图自适应切片完成！共生成 {len(slices)} 张高清晰度分块图片:")
                for s in slices:
                    print(f"  ● {s}")
    except Exception as e:
        print(f"❌ 切片失败: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
