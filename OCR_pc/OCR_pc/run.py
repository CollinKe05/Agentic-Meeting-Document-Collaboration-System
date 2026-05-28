"""命令行测试脚本"""
import sys
from core.pipeline_onnx import process_image
from core.markdown import to_markdown_v2

if len(sys.argv) < 2:
    print("Usage: python run.py <image_path>")
    sys.exit(1)

img_path = sys.argv[1]

print(f"\nProcessing: {img_path}")
blocks = process_image(img_path)

md = to_markdown_v2(blocks)
print("\n" + "=" * 50)
print(md)
print("=" * 50)
print(f"\nBlocks: {len(blocks)}")
